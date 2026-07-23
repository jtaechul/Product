"""hook_intro_stage — 본문 영상을 '오프닝 훅 + 엔드카드 + 전환 + 임팩트 사운드' 시스템으로
   감싸는 파이프라인 연결 단계.

파이프라인에서의 위치: 본문 영상(합성·자막·오디오 완료) → apply() → 완성본.
설계 원칙: **절대 발행을 막지 않는다.** edge-tts/폰트/네트워크 등 어떤 전제라도 없으면
경고만 남기고 원본 본문 영상을 그대로 반환한다(안전 폴백).

구성(모두 hook_intro 모듈의 확정 디자인 사용):
  오프닝 훅(명조 대형 그라데이션 타이틀·어절 팝·셰이크·홀드)
  → 플래시 전환 → 본문 → 플래시 전환
  → 엔드카드(타자기 텍스트·타자음·피사체 중간밴드)
오디오: 강렬 훅 나레이션 + 딥 붐(어절) + 본문 오디오 + 엔드카드 타자음 (+선택 BGM).
"""
from __future__ import annotations

import logging
import math
import re
import ssl
import subprocess
from pathlib import Path

from src.core import hook_intro as hi

log = logging.getLogger(__name__)

# 오프닝/엔드카드 배경 프레임의 최소 구조점수(빈 물 배제). 아래면 '피사체 없음'으로 보고 폴백.
# footage._frame_macro_std 실측: 빈 어두운 물 1~4, 피사체·질감 있는 프레임 12~85.
_MIN_FRAME_STRUCT = 8.0
_PROXY_CA = "/root/.ccr/ca-bundle.crt"
_PUNCT = re.compile(r"[、。，．・「」『』（）\s]")
# ★오프닝 홀드(운영자 확정): 마지막 어절 이펙트가 끝난 뒤 본문으로 넘어가기 전 최소 대기(초).
#   0.5~1.0초 범위 중 0.7초 채택 — 3줄 훅의 마지막 줄이 끝나자마자 넘어가던 어색함 방지.
_OPEN_HOLD_S = 0.7
# 오프닝 최소 길이(초) — 나레이션이 아주 짧아도 이 밑으로는 내려가지 않게 하한만 보장.
_OPEN_MIN_S = 2.4


def _install_ca() -> None:
    # Path.exists()도 try 안: CI 러너(비 root)에선 /root/.ccr 접근 불가라
    # Python 3.11 exists()가 PermissionError를 되던진다 → 전부 감싸 삼킨다.
    try:
        if Path(_PROXY_CA).exists():
            import edge_tts.communicate as ec
            ec._SSL_CTX = ssl.create_default_context(cafile=_PROXY_CA)
    except Exception:  # noqa: BLE001
        pass


def _synth_hook(text: str, out_mp3: str, cfg: hi.HookIntroConfig) -> dict | None:
    """훅 문장 → edge-tts(강조 파라미터)로 합성. 단어 온셋(頭/目/骨 등 어절 첫 글자) 반환.
    실패(키/네트워크/모듈 없음) 시 None → 상위에서 폴백."""
    try:
        import asyncio
        import edge_tts
        _install_ca()

        async def _run():
            c = edge_tts.Communicate(text, "ja-JP-KeitaNeural", rate=cfg.hook_tts_rate,
                                     pitch=cfg.hook_tts_pitch, volume=cfg.hook_tts_volume,
                                     boundary="WordBoundary")
            audio = bytearray(); words = []
            async for ch in c.stream():
                if ch["type"] == "audio":
                    audio += ch["data"]
                elif ch["type"] == "WordBoundary":
                    words.append((ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
            return bytes(audio), words

        audio, words = asyncio.run(_run())
        if not audio:   # 오디오만 있으면 채택(단어경계 없어도 균등 온셋으로 처리 → 오프닝 유지)
            return None
        Path(out_mp3).write_bytes(audio)
        return {"mp3": out_mp3, "words": words or []}
    except Exception as e:  # noqa: BLE001
        log.warning("[hook_intro] 훅 나레이션 합성 실패 → 오프닝 생략: %s", e)
        return None


def _even_onsets(pop_words: list[str], cfg) -> dict:
    """단어 온셋을 못 구할 때(나레이션 실패/단어경계 없음) 팝 어절을 오프닝 구간에 균등 배치."""
    pops = [_PUNCT.sub("", w) for w in (pop_words or [])]
    pops = [p for p in pops if p]
    span = max(0.4, cfg.opening_seg_s - cfg.narr_start_s - 0.3)
    if not pops:
        return {"": round(span * 0.5, 2)}
    return {p[0]: round((i + 1) * span / (len(pops) + 1), 2) for i, p in enumerate(pops)}


def _onsets_for_words(pop_words: list[str], words: list[tuple]) -> dict:
    """팝 어절 각각의 첫 글자를 실제 단어 온셋에 매핑(정합)."""
    onsets = {}
    wi = 0
    for w in pop_words:
        core = _PUNCT.sub("", w)
        if not core:
            continue
        first = core[0]
        # 남은 words에서 first를 포함하는 첫 단어의 시작
        found = None
        for j in range(wi, len(words)):
            if first in words[j][2]:
                found = words[j][0]; wi = j + 1; break
        onsets[first] = found if found is not None else (words[wi][0] if wi < len(words) else 0.0)
    return onsets


def _probe(path: str, entry: str) -> str:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", f"stream={entry}", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return r.stdout.strip()


def _cover_crop(img: str, out_png: str, W: int, H: int) -> bool:
    """고화소 사진을 캔버스(W×H, 9:16)에 꽉 채워(cover) 크롭한 PNG로 저장. 오프닝/엔드카드 배경용."""
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", img, "-vf", vf,
                        "-frames:v", "1", out_png], capture_output=True, text=True)
    return r.returncode == 0 and Path(out_png).exists()


def _grab_frame(video: str, t: float, out_png: str, vf: str | None = None) -> bool:
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", video]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-frames:v", "1", out_png]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and Path(out_png).exists()


def _duration_of(path: str) -> float:
    """영상 실제 길이(초) = duration − start_time.

    왜(실제 결함): NOAA/Commons webm은 타임스탬프가 0에서 시작하지 않는 파일이 있어
    (start_time≈141,024s) ffprobe duration이 '끝 타임스탬프'(141,113s)를 돌려준다.
    이 값을 길이로 쓰면 프레임 추출 시각이 영상 밖(수십 시간 뒤)을 가리켜 엔드카드
    피사체 프레임 추출이 전부 실패했다. start_time을 빼서 실제 구간 길이를 쓴다."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=start_time,duration",
                        "-of", "json", path], capture_output=True, text=True)
    try:
        import json as _json
        fmt = _json.loads(r.stdout or "{}").get("format", {})
        dur = float(fmt.get("duration") or 0)
        start = float(fmt.get("start_time") or 0)
        if dur > 0:
            return max(0.0, dur - max(0.0, start))
    except Exception:  # noqa: BLE001
        pass
    try:
        return float(_probe(path, "duration") or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _temporal_foreground_scores(frame_paths: list[str]) -> list[float]:
    """각 프레임의 '시간축 전경(움직이는 피사체)' 점수. 정적 빈 물=낮음, 움직이는 생물=높음.

    왜(재발방지 실사고 #046 민태과): 회색 저대비 물고기(구조·적색 신호가 약함)는 struct·subject_score
    로는 빈 물과 구분이 안 돼, 오히려 조명 그라디언트·마린스노우가 낀 '빈 물'이 더 높은 점수를 받았다.
    → 피사체는 **움직인다**. 프레임들의 시간 평균 대비 '국소(상위 10%) 차이'가 크면 그 프레임에
    움직이는 피사체가 있다는 뜻(정적 빈 물은 프레임끼리 거의 같아 차이 ≈ 0). 색·대비 무관.
    """
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return [0.0] * len(frame_paths)
    gw, gh = 64, 36
    grids: list[list[int] | None] = []
    for p in frame_paths:
        try:
            grids.append(list(Image.open(p).convert("L").resize((gw, gh)).tobytes()))
        except Exception:  # noqa: BLE001
            grids.append(None)
    valid = [g for g in grids if g]
    if len(valid) < 2:
        return [0.0] * len(frame_paths)
    n = gw * gh
    mean = [sum(g[i] for g in valid) / len(valid) for i in range(n)]
    k = max(1, n // 10)                          # 상위 10% 픽셀만(국소 피사체 신호, 전역 희석 방지)
    out: list[float] = []
    for g in grids:
        if not g:
            out.append(0.0); continue
        diffs = sorted((abs(g[i] - mean[i]) for i in range(n)), reverse=True)
        out.append(sum(diffs[:k]) / k)
    return out


def _score_best_frame(video: str, wd: Path, logo_box: tuple | None = None,
                      hint: str = "", n_samples: int = 20) -> tuple[str | None, float]:
    """피사체가 가장 뚜렷한 프레임 후보 경로 + 점수를 돌려준다(임계 판정은 호출부에서).

    ★#046 소코다라(빈 바다 반복) 최종 대책: **Gemini가 후보 프레임 중 피사체가 또렷한 것을 직접 고른다**
    (`vision_subject.pick_subject_frame` · 후보 전부 1회 배치 · 저비용). 비전 키 없거나 실패 시에만
    휴리스틱으로 폴백.
    ★재발방지 보강(2차): ① 샘플을 촘촘히(기본 20개, 5~95% 균등) 떠서 '피사체가 잠깐 나오는' 순간을
    Gemini 후보에 반드시 포함시킨다(예전 14개로는 짧게 등장하는 물고기를 놓쳐 Gemini도 못 골랐다).
    ② 폴백 점수는 **움직임(temporal foreground)을 주신호**로 삼는다 — 예전엔 구조도(struct=매크로 표준편차)를
    가중 없이 그대로 더해 '질감 많은 빈 모래 바닥'이 어두운 물고기보다 높은 점수를 받았다(빈 바다 선택의 근본
    원인). struct는 미세 타이브레이커로만(0.1배) 두고, 움직이는 피사체(fg)와 색·구조 saliency(subject_score)로
    고른다. logo_box가 오면 delogo로 메운다.
    """
    from src.core import reframe
    from src.core.footage import _frame_macro_std
    from PIL import Image
    dur = _duration_of(video)
    if dur <= 0:
        return None, -1.0
    vf = None
    if logo_box:
        sw = _probe(video, "width") or 1920
        sh = _probe(video, "height") or 1080
        try:
            vf = reframe.delogo_vf(float(sw), float(sh), logo_box)
        except Exception:  # noqa: BLE001
            vf = None
    N = max(6, int(n_samples))
    grabbed: list[str] = []
    for i in range(N):
        t = dur * (0.05 + 0.90 * i / (N - 1))            # 5~95% 균등(촘촘히 → 짧게 나오는 피사체 포착)
        cand = str(wd / f"ecs_{i}.png")
        if _grab_frame(video, t, cand, vf=vf):
            grabbed.append(cand)
    if not grabbed:
        return None, -1.0
    # ★Gemini 우선: 후보 중 피사체가 가장 또렷한 프레임을 직접 선택(빈 바다 회피). 키 없으면 None → 휴리스틱.
    try:
        from src.core import vision_subject
        idx = vision_subject.pick_subject_frame(grabbed, hint)
        if idx is not None and 0 <= idx < len(grabbed):
            log.info("[hook_intro] 배경 프레임 = Gemini 선택(index %d/%d)", idx, len(grabbed))
            return grabbed[idx], 999.0        # 비전 확정 → 임계 통과로 취급
    except Exception:  # noqa: BLE001
        pass
    # 폴백(비전 미가동): 움직이는 피사체(fg) 주신호 + saliency, struct는 미세 타이브레이커(빈 모래 편애 제거)
    fgs = _temporal_foreground_scores(grabbed)              # ★움직이는 피사체 가려내기(빈 물 배제 핵심)
    best, best_score = None, -1.0
    for cand, fg in zip(grabbed, fgs):
        try:
            struct = _frame_macro_std(Image.open(cand))
        except Exception:  # noqa: BLE001
            struct = 0.0
        s = 30.0 * reframe.subject_score(cand) + 3.0 * fg + 0.10 * struct
        if reframe.text_score(cand) >= 0.012:              # 번인 텍스트 프레임 강한 감점
            s *= 0.02
        if s > best_score:
            best, best_score = cand, s
    return best, best_score


def _best_subject_frame(video: str, out_png: str, wd: Path,
                        logo_box: tuple | None = None) -> bool:
    """피사체가 뚜렷한 프레임을 골라 out_png로 저장(구조 임계 통과 시 True). 미달이면 False."""
    best, best_score = _score_best_frame(video, wd, logo_box)
    if not best or best_score < _MIN_FRAME_STRUCT:
        log.info("[hook_intro] 피사체 프레임 구조 부족(%.1f<%.1f) → 배경 프레임 선택 실패", best_score, _MIN_FRAME_STRUCT)
        return False
    Path(out_png).write_bytes(Path(best).read_bytes())
    return True


def _best_effort_frame(video: str, out_png: str, wd: Path, logo_box: tuple | None = None) -> bool:
    """★#046 재발방지: 임계 미달이어도 '가장 덜 빈(피사체 신호 최고)' 후보 프레임을 쓴다.
    고정 시각(0.5초·55%) 블라인드 grab은 대개 빈 물이라, 후보가 하나라도 있으면 그중 최고점을 쓰는 게 항상 낫다.
    후보 자체가 없을 때만 False(그때만 상위가 고정 시각 폴백)."""
    best, _ = _score_best_frame(video, wd, logo_box)
    if best and Path(best).exists():
        Path(out_png).write_bytes(Path(best).read_bytes())
        return True
    return False


def apply(body_video: str, spec: hi.SpeciesSpec, hook_text: str, work_dir: str,
          cfg: hi.HookIntroConfig | None = None, bgm: str | None = None,
          open_bg_video: str | None = None, subject_video: str | None = None,
          logo_box: tuple | None = None, hero_image: str | None = None,
          thumb_out: str | None = None) -> str:
    """본문 영상을 오프닝/엔드카드/전환/사운드로 감싼 완성본 경로 반환.
    전제 미충족 시 원본 body_video를 그대로 반환(발행 불정지).

    배경 소스 규칙(재발 방지 — 실제 결함 2건의 근본 원인):
    - open_bg_video: 오프닝 배경 프레임 소스. **자막 번인 전 클린 영상**을 넘겨야
      본문 자막이 오프닝 뒤에 미리 노출되지 않는다(미지정 시 body_video 폴백).
    - subject_video: 엔드카드 피사체 프레임 소스. **크롭·줌 전 원본 광각 영상**을 넘겨야
      과확대로 생물을 식별 못 하는 문제가 없다(미지정 시 open_bg_video 폴백).
    - hero_image: ★있으면 오프닝·엔드카드 배경을 이 **고화소 원본 사진**으로 만든다(정지 화면이라
      영상 프레임보다 훨씬 선명·고급). 미지정/실패 시 기존 영상 프레임으로 자동 폴백(발행 불정지).
    """
    cfg = cfg or hi.HookIntroConfig()
    wd = Path(work_dir); wd.mkdir(parents=True, exist_ok=True)
    try:
        if not hi.fonts_available():
            log.warning("[hook_intro] 폰트 없음 → 오프닝/엔드카드 생략(본문 그대로)")
            return body_video
        dur = _duration_of(body_video)
        if dur <= 0:
            return body_video

        # 1) 훅 나레이션 + 온셋. ★기획서 규칙: 모든 영상에 오프닝 훅 + 엔드카드 필수.
        #    나레이션(edge-tts)이 실패해도 오프닝/엔드카드는 반드시 낸다(무음 훅으로 대체).
        hook = _synth_hook(hook_text, str(wd / "hook.mp3"), cfg)
        if hook and hook.get("words"):
            onsets = _onsets_for_words(spec.hook_pop_words, hook["words"])
            narr_failed = False
        else:
            onsets = _even_onsets(spec.hook_pop_words, cfg)
            narr_failed = not hook

        # ★오프닝 홀드 보장(운영자 확정 · 실측 기반): 훅 나레이션이 **완전히 끝난 뒤** 최소 0.7초
        #   여유를 두고 본문으로 넘어가야 한다. 기준은 '마지막 어절의 시작'이 아니라 '나레이션 실제 종료'다.
        #   (실제 결함: 어절 시작만 보면 마지막 단어를 말하는 ~1초가 누락돼, 3줄 훅에서 훅 음성이
        #    본문에 겹쳐 재생됐다. → mp3 실제 길이 + 단어경계 끝을 함께 보고 나레이션 종료를 잡는다.)
        try:
            narr_end = 0.0
            if hook and hook.get("mp3") and Path(hook["mp3"]).exists():
                narr_end = cfg.narr_start_s + _duration_of(hook["mp3"])   # mp3 실측(트레일링 포함)
            if hook and hook.get("words"):
                last = hook["words"][-1]                                  # (offset_s, dur_s, text)
                narr_end = max(narr_end, cfg.narr_start_s + float(last[0]) + float(last[1]))
            last_on = max(onsets.values()) if onsets else 0.0
            pop_end = cfg.narr_start_s + float(last_on) + cfg.pop_grow_s + cfg.pop_fade_s
            need = max(narr_end, pop_end) + _OPEN_HOLD_S
            # ★오프닝 길이 = '나레이션(문구 날아옴) 실제 종료 + 홀드'로 정확히 맞춘다(항상 재계산).
            #   예전엔 need가 기본값(4.6)보다 클 때만 늘렸다 → 나레이션을 빠르게 해도 총 길이는 4.6로
            #   고정돼 '죽은 홀드'만 늘었다. 이제 need로 정확히 축소·확대해 홀드(0.7초)만 유지한 채
            #   문구 날아오는 시간이 줄면 오프닝 전체도 그만큼 짧아진다. (너무 짧아지지 않게 최소값만 보장)
            cfg.opening_seg_s = max(_OPEN_MIN_S, math.ceil(need * 100) / 100.0)
        except Exception:  # noqa: BLE001
            pass

        if narr_failed:   # 나레이션 완전 실패 → 무음 훅 오디오로 대체(오프닝/엔드카드는 유지)
            log.warning("[hook_intro] 훅 나레이션 실패 → 무음 훅으로 오프닝/엔드카드 유지")
            silent = str(wd / "hook_silent.mp3")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                            "-i", "anullsrc=r=44100:cl=mono", "-t", f"{cfg.opening_seg_s:.2f}",
                            "-q:a", "9", silent], check=True)
            hook = {"mp3": silent, "words": []}

        # 2) 배경 프레임 — ★고화소 히어로 사진이 있으면 오프닝·엔드카드 배경을 그 사진으로(정지 화면이라
        #    영상 프레임보다 훨씬 선명). 없으면 기존대로 영상 프레임 사용(폴백, 발행 불정지).
        hero = hero_image if hero_image and Path(hero_image).exists() else None
        src_open = open_bg_video if open_bg_video and Path(open_bg_video).exists() else body_video
        src_subj = subject_video if subject_video and Path(subject_video).exists() else src_open
        subj_hint = (getattr(spec, "sci_name", "") or getattr(spec, "jp_name", "") or "").strip()
        open_bg = str(wd / "open_bg.png"); ec_frame = str(wd / "ec_frame.png")
        # ★#046 최종대책(운영자 확정): 피사체 프레임은 **원본 클립(subject_video)에서** 고른다(리프레임된
        #   body는 이미 피사체를 놓쳤을 수 있음 → 원본엔 피사체가 반드시 나오는 순간이 있다). Gemini가 후보 중
        #   피사체가 또렷한 프레임을 직접 선택(_score_best_frame). 이 한 프레임을 오프닝·엔드카드가 공유(비전 1회).
        subj_logo = logo_box if (subject_video and src_subj == subject_video) else None
        subj_frame = None
        if not hero:
            sf, _ = _score_best_frame(src_subj, wd, logo_box=subj_logo, hint=subj_hint)
            subj_frame = sf if sf and Path(sf).exists() else None
        # 오프닝 배경(9:16 커버 크롭): 히어로 사진 > 원본 피사체 프레임 > 앞부분 폴백
        if hero and _cover_crop(hero, open_bg, cfg.W, cfg.H):
            log.info("[hook_intro] 오프닝 배경 = 고화소 히어로 사진")
        elif subj_frame and _cover_crop(subj_frame, open_bg, cfg.W, cfg.H):
            log.info("[hook_intro] 오프닝 배경 = 원본 피사체 프레임(비전 선택)")
        else:
            odur = _duration_of(src_open) or dur
            if not _grab_frame(src_open, min(0.5, odur * 0.1), open_bg):
                return body_video
        # 엔드카드 배경: 히어로 사진 > 원본 피사체 프레임 > 고정 시각 폴백
        if hero and _cover_crop(hero, ec_frame, cfg.W, cfg.H):
            log.info("[hook_intro] 엔드카드 배경 = 고화소 히어로 사진")
        elif subj_frame:
            Path(ec_frame).write_bytes(Path(subj_frame).read_bytes())
        else:
            _grab_frame(src_subj, (_duration_of(src_subj) or dur) * 0.55, ec_frame)
        ec_bg = str(wd / "ec_bg.png")
        hi.build_specimen_bg(ec_frame if Path(ec_frame).exists() else open_bg, ec_bg, cfg)

        # 3) 오프닝/엔드카드 렌더 → mp4
        of_dir = str(wd / "of"); ec_dir = str(wd / "ecf")
        of_frames = hi.render_opening_frames(open_bg, onsets, spec, of_dir, cfg)
        # ★유튜브 썸네일(운영자 요청): '전체 타이틀이 다 드러난' 오프닝 마지막 홀드 프레임을 저장.
        #   (기본 커버는 t=2s의 애니 도중 프레임이라 제목이 덜 노출됨 → 완전 노출 프레임을 별도 제공.)
        if thumb_out and of_frames:
            try:
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", of_frames[-1],
                                "-q:v", "3", thumb_out], check=False, timeout=30)
            except Exception as e:  # noqa: BLE001
                log.warning("[hook_intro] 유튜브 썸네일 저장 실패: %s", e)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(cfg.FPS),
                        "-i", f"{of_dir}/of_%03d.png", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-crf", "18", str(wd / "opening.mp4")], check=True)
        _, clicks = hi.render_endcard_frames(ec_bg, spec, ec_dir, cfg)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(cfg.FPS),
                        "-i", f"{ec_dir}/ec_%03d.png", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-crf", "18", str(wd / "endcard.mp4")], check=True)

        # 4) SFX/플래시
        boom = hi.generate_boom(str(wd / "boom.wav"), cfg)
        # 엔드카드 사운드 = 붐(쾅). 타자기 폐지 → 엔드카드 등장 순간에 딥 붐을 입힌다.
        tick = boom
        flash = hi.build_flash_png(str(wd / "flash.png"), cfg)

        OPEN = cfg.opening_seg_s; END = cfg.endcard_dur_s
        BODY_END = OPEN + dur; TOTAL = OPEN + dur + END
        W, H = cfg.W, cfg.H

        # 5) 영상 concat + 전환 2곳(본문 해상도 정규화)
        # ★SAR 정규화(setsar=1) 필수: reframe '전신핏'(블러 배경) 컷은 스케일 반올림으로
        #   SAR 5120:5121 같은 비1:1 값이 붙는데, 오프닝/엔드카드 mp4는 SAR 0:1(=1:1)이라
        #   concat이 'SAR 불일치'로 실패했다(오프닝/엔드카드 통째 누락의 실제 근본원인).
        #   세 입력 모두 setsar=1로 맞춰 concat이 항상 성공하게 한다.
        vf = (
            f"[0:v]scale={W}:{H},setsar=1,setpts=PTS-STARTPTS[o];"
            f"[1:v]scale={W}:{H},setsar=1,setpts=PTS-STARTPTS[b];"
            f"[2:v]scale={W}:{H},setsar=1,setpts=PTS-STARTPTS[e];[o][b][e]concat=n=3:v=1:a=0[cat];"
            f"[3:v]format=yuva420p,colorchannelmixer=aa=0.55,fade=t=in:st={OPEN-0.25}:d=0.22:alpha=1,"
            f"fade=t=out:st={OPEN}:d=0.28:alpha=1[fl1];"
            f"[4:v]format=yuva420p,colorchannelmixer=aa=0.6,fade=t=in:st={BODY_END-0.25}:d=0.22:alpha=1,"
            f"fade=t=out:st={BODY_END}:d=0.30:alpha=1[fl2];"
            f"[cat][fl1]overlay=0:0[o1];[o1][fl2]overlay=0:0[v]"
        )
        vout = str(wd / "wrapped_video.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-i", str(wd / "opening.mp4"), "-i", body_video, "-i", str(wd / "endcard.mp4"),
                        "-loop", "1", "-t", str(TOTAL), "-i", flash,
                        "-loop", "1", "-t", str(TOTAL), "-i", flash,
                        "-filter_complex", vf, "-map", "[v]", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-crf", "19", "-r", str(cfg.FPS), vout], check=True)

        # 6) 오디오: 훅@0.30 + 붐@온셋 + 본문오디오@OPEN + 엔드카드 타자@BODY_END + (BGM)
        NARR = cfg.narr_start_s
        inputs = ["-i", hook["mp3"], "-i", body_video, "-i", boom, "-i", tick]
        af = (f"[0:a]adelay={int(NARR*1000)}|{int(NARR*1000)},volume={cfg.mix_hook}[hk];"
              f"[1:a]adelay={int(OPEN*1000)}|{int(OPEN*1000)},volume={cfg.mix_body}[bd];")
        labels = ["[hk]", "[bd]"]
        for i, (first, on) in enumerate(onsets.items()):
            at = int((NARR + on) * 1000)
            af += f"[2:a]adelay={at}|{at},volume={cfg.mix_boom}[bm{i}];"
            labels.append(f"[bm{i}]")
        for i, ct in enumerate(clicks):
            at = int((BODY_END + ct) * 1000)
            af += f"[3:a]adelay={at}|{at},volume=0.5[tk{i}];"
            labels.append(f"[tk{i}]")
        ninp = len(labels)
        if bgm and Path(bgm).exists():
            inputs += ["-i", bgm]
            af += (f"[4:a]atrim=0:{TOTAL},volume={cfg.mix_bgm},afade=t=in:st=0:d=1.5,"
                   f"afade=t=out:st={TOTAL-2}:d=2.0[bed];")
            labels.append("[bed]"); ninp += 1
        af += (f"{''.join(labels)}amix=inputs={ninp}:duration=longest:normalize=0,"
               f"alimiter=limit={cfg.limiter},atrim=0:{TOTAL},aresample=44100[a]")
        aout = str(wd / "wrapped_audio.m4a")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + inputs +
                       ["-filter_complex", af, "-map", "[a]", "-c:a", "aac", "-b:a", "192k", aout],
                       check=True)

        final = str(wd / "final_wrapped.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", vout, "-i", aout,
                        "-c:v", "copy", "-c:a", "copy", "-shortest", final], check=True)
        log.info("[hook_intro] 오프닝/엔드카드 적용 완료: %s (%.1fs)", final, TOTAL)
        return final
    except Exception as e:  # noqa: BLE001
        log.warning("[hook_intro] 적용 실패 → 본문 그대로 발행: %s", e)
        return body_video
