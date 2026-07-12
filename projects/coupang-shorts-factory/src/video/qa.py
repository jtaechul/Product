"""M6.5 렌더 QA 게이트 — '이상한 영상은 발행 자체를 차단' (수정 후 검증 원칙의 자동화).

렌더 결과(subtitle_plan + 실제 video.mp4 프레임)를 기계 검사한다:
  ① 자막=대본 일치 — 라인별 자막 칸을 이어 붙이면 대본 text와 띄어쓰기까지 완전 일치
  ② 자막 길이 규격(1~16자) — 통문장·파편 방지
  ③ 위치 고정 — 일반 자막 y가 단 1곳(널뛰기 방지), 밈 카드 ≤1개, react ≤6개
  ④ 타이밍 — 시작 시각 단조 증가 + 발화 커버리지(자막 없는 긴 공백 방지)
  ⑤ 프레임 번인 — 실제 영상 프레임 3장에서 자막색 픽셀이 자막 밴드에 실존하는지
  ⑥ 규격 — 프레임 해상도 1080x1920

파이프라인은 실패 시 비정상 종료 → 워크플로우 실패 → 릴리스/업로드가 차단된다.
결과는 job_dir/qa_report.json 으로 남긴다.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

SUB_LEN_MAX = 16          # 자막 칸 최대 글자수(공백 포함) — 초과분은 화면 통문장 신호
COVERAGE_MIN = 0.55       # 영상 길이 대비 자막 표시 시간 최소 비율
MEME_MAX, REACT_MAX = 1, 6
YELLOW_MIN_PIXELS = 150   # 자막 밴드에서 자막색으로 인정할 최소 픽셀 수


def run_qa(video_path: Path, stats: dict, lines: list, job_dir: Path, settings: dict) -> dict:
    problems, checks = [], {}
    plan = stats.get("subtitle_plan") or []
    subs = [p for p in plan if p.get("kind") == "sub"]
    memes = [p for p in plan if p.get("kind") == "meme"]
    reacts = [p for p in plan if p.get("kind") == "react"]

    # ① 자막=대본 일치 (punch 라인은 밈 카드로 검사)
    by_line: dict = {}
    for p in subs:
        by_line.setdefault(int(p.get("line_i", -1)), []).append(str(p["text"]))
    for li, ln in enumerate(lines or []):
        text = str(ln.get("text", "")).strip()
        if not text:
            continue
        if ln.get("punch"):
            if not any(m["text"] == text for m in memes):
                problems.append(f"라인{li + 1}(punch) 밈 카드 누락")
            continue
        got = " ".join(by_line.get(li, []))
        if not got:
            problems.append(f"라인{li + 1} 자막 누락: '{text[:24]}'")
        elif got != text:
            problems.append(f"라인{li + 1} 자막≠대본(띄어쓰기 포함): '{got[:24]}' vs '{text[:24]}'")
    checks["script_match"] = "자막=대본 일치"

    # ② 길이 규격
    for p in subs:
        t = str(p["text"])
        if not (1 <= len(t) <= SUB_LEN_MAX):
            problems.append(f"자막 길이 위반({len(t)}자): '{t[:20]}'")
    checks["length"] = f"칸당 1~{SUB_LEN_MAX}자"

    # ③ 위치 고정 + 오버레이 개수
    ys = sorted({int(p["y"]) for p in subs})
    if len(ys) > 1:
        problems.append(f"일반 자막 y 위치가 {len(ys)}곳({ys}) — 1곳 고정이어야 함")
    if len(memes) > MEME_MAX:
        problems.append(f"밈 카드 {len(memes)}개 (최대 {MEME_MAX})")
    if len(reacts) > REACT_MAX:
        problems.append(f"react 오버레이 {len(reacts)}개 (최대 {REACT_MAX})")
    checks["layout"] = f"자막 y {ys or '없음'}, 밈 {len(memes)}, react {len(reacts)}"

    # ④ 타이밍
    if not subs:
        problems.append("자막 플랜이 비어 있음")
    else:
        starts = [float(p["start"]) for p in subs]
        if any(b < a - 0.01 for a, b in zip(starts, starts[1:])):
            problems.append("자막 시작 시각이 역행함")
        dur = float(stats.get("video_duration_seconds") or 0)
        if dur > 0:
            cover = sum(max(0.0, min(float(p["end"]), dur) - float(p["start"])) for p in subs)
            checks["coverage"] = f"{cover / dur:.0%}"
            if cover / dur < COVERAGE_MIN:
                problems.append(f"자막 커버리지 {cover / dur:.0%} (< {COVERAGE_MIN:.0%})")

    # ⑤+⑥ 실제 프레임 검사 (자막색 픽셀 실존 + 해상도)
    try:
        problems += _check_frames(Path(video_path), subs, settings, Path(job_dir), checks)
    except Exception as e:  # 프레임 검사 자체가 죽으면 그것도 실패로 간주(눈 감고 통과 금지)
        problems.append(f"프레임 검사 실행 실패: {type(e).__name__}: {e}")

    report = {"passed": not problems, "problems": problems, "checks": checks,
              "counts": {"subs": len(subs), "memes": len(memes), "reacts": len(reacts)}}
    (Path(job_dir) / "qa_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    status = "통과" if report["passed"] else f"실패 {len(problems)}건"
    print(f"[qa] 게이트 {status}" + (f" — {problems[:3]}" if problems else ""))
    return report


def _check_frames(video_path: Path, subs: list, settings: dict, job_dir: Path,
                  checks: dict) -> list:
    """자막 표시 중점 3곳의 프레임을 뽑아 (a)해상도 (b)자막 밴드에 자막색 픽셀 실존을 확인."""
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image

    problems = []
    if not subs:
        return problems
    s = settings.get("subtitle", {})
    y = int(s.get("y", 1250))
    target = _hex_rgb(s.get("color", "#FFE400"))
    W = int(settings.get("render", {}).get("width", 1080))
    H = int(settings.get("render", {}).get("height", 1920))

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    frames_dir = job_dir / "qa_frames"
    frames_dir.mkdir(exist_ok=True)
    picks = sorted({max(0, len(subs) // 6), len(subs) // 2, max(0, len(subs) * 5 // 6)})
    found_any_fail = 0
    for idx in picks:
        p = subs[idx]
        t = (float(p["start"]) + min(float(p["end"]), float(p["start"]) + 1.2)) / 2
        fp = frames_dir / f"qa_{idx}.png"
        subprocess.run([ff, "-y", "-ss", f"{t:.2f}", "-i", str(video_path),
                        "-frames:v", "1", str(fp)], capture_output=True, check=True)
        im = Image.open(fp).convert("RGB")
        if im.size != (W, H):
            problems.append(f"해상도 {im.size} (기대 {(W, H)})")
            break
        band = np.asarray(im.crop((0, max(0, y - 70), W, min(H, y + 190))), dtype=int)
        dist = np.abs(band - np.array(target)).sum(axis=2)
        n_pix = int((dist < 210).sum())
        if n_pix < YELLOW_MIN_PIXELS:
            found_any_fail += 1
            problems.append(f"{t:.1f}s 프레임 자막 밴드에 자막색 픽셀 {n_pix}개(<{YELLOW_MIN_PIXELS}) "
                            f"— '{p['text'][:14]}' 미표시 의심")
    checks["frames"] = f"{len(picks)}장 검사, 실패 {found_any_fail}장"
    return problems


def _hex_rgb(hx: str) -> tuple:
    hx = hx.lstrip("#")
    return tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))
