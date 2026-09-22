"""② 업로드된 씬 영상 + 대본 → 나레이션·가라오케 자막 → 최종 MP4 → Release 업로드.

GitHub Actions에서 실행된다(관리자 페이지가 호출).
씬 영상은 관리자 페이지가 릴리스 `moviegen-<id>` 에 `scene01.mp4` 형태로 올려 둔 것을 쓴다.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

from core import seal, subtitle, tts, video

ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
WORK = ROOT / "work"
API = "https://api.github.com"


def gh(path: str, token: str, method: str = "GET", data: bytes | None = None,
       content_type: str | None = None, base: str = API, allow404: bool = False):
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        if allow404 and e.code == 404:
            return None
        raise
    return json.loads(body) if body else None


def download_asset(url: str, token: str, dest: Path) -> Path:
    """릴리스 자산 내려받기. octet-stream 을 요청해야 파일 본문이 온다."""
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/octet-stream")
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    if dest.stat().st_size == 0:
        raise RuntimeError(f"내려받은 영상이 비었습니다: {url}")
    return dest


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    cid = os.environ.get("CONTENT_ID", "").strip()
    if not (token and repo and cid):
        print("::error::GITHUB_TOKEN / GITHUB_REPOSITORY / CONTENT_ID 가 필요합니다.")
        return 1

    record_path = CONTENT_DIR / f"{cid}.json"
    if not record_path.exists():
        print(f"::error::대본 파일이 없습니다: {record_path}")
        return 1
    record = json.loads(record_path.read_text(encoding="utf-8"))
    scenes = record["scenes"]

    tag = f"moviegen-{cid}"
    rel = gh(f"/repos/{repo}/releases/tags/{tag}", token, allow404=True)
    assets = {a["name"]: a for a in (rel or {}).get("assets", [])}
    missing = [i for i in range(1, len(scenes) + 1) if f"scene{i:02d}.mp4" not in assets]
    if missing:
        print(f"::error::{', '.join(map(str, missing))}번 씬 영상이 아직 올라오지 않았습니다. "
              "관리자 페이지에서 모두 올렸는지 확인하세요.")
        return 1

    video.ensure_ffmpeg()
    WORK.mkdir(parents=True, exist_ok=True)
    width, height = (1080, 1920) if os.environ.get("HQ") == "true" else (720, 1280)
    engine = os.environ.get("TTS_ENGINE", "gemini").strip().lower()
    voice = os.environ.get("VOICE", "Sulafat")
    rate = os.environ.get("RATE", "-5%")
    highlight = os.environ.get("HIGHLIGHT", "노란색")
    tail_pad = float(os.environ.get("TAIL_PAD", "0.5"))
    # 전환은 씬 끝 여백 안에서 일어나게 한다. 여백보다 길면 대사 위로 화면이 섞인다.
    xdur = min(float(os.environ.get("XFADE", "0.4")), tail_pad)
    # 자막 한 줄 길이 = Gemini 성우의 합성 단위. 늘리면 호출 수가 줄어 빠르고 할당량을
    # 덜 쓰지만, 줄 안에서의 어절 하이라이트가 그만큼 어림값이 된다.
    max_chars = int(os.environ.get("SUB_MAX_CHARS", "13"))
    # 관리자 페이지가 봉해 보낸 사용자 개인 키를 먼저 쓰고, 없으면 저장소 기본 키.
    try:
        gemini_key = seal.gemini_key()
    except seal.SealError as e:
        print(f"::error::{e}")
        return 1
    if engine == "gemini" and not gemini_key:
        print("::error::Gemini 성우를 쓰려면 API 키가 필요합니다. 관리자 페이지 설정에서 "
              "내 API 키를 넣거나, 성우 엔진을 edge 로 바꾸세요.")
        return 1

    # 1. 씬별 나레이션 합성.
    #    Gemini 성우는 타임스탬프를 안 주므로 자막 한 줄씩 따로 합성해 실제 길이를 잰다
    #    (core/tts.py 설명 참고). 그래서 줄이 뜨고 사라지는 시각이 오디오와 정확히 맞는다.
    audios = []
    for i, sc in enumerate(scenes):
        print(f"[{i + 1}/{len(scenes)}] 음성 합성")
        audios.append(tts.synthesize_scene(
            i, sc["narration"], str(WORK),
            engine=engine, api_key=gemini_key, voice=voice, rate=rate,
            direction=sc.get("voice_direction", ""), max_chars=max_chars,
        ))
    durs = [a.speech_duration + tail_pad for a in audios]

    # 2. 릴리스에서 씬 영상 받아 9:16 규격·길이 맞춤
    clips = []
    for i, dur in enumerate(durs):
        print(f"[{i + 1}/{len(scenes)}] 영상 내려받아 규격 변환")
        raw = download_asset(assets[f"scene{i + 1:02d}.mp4"]["url"], token,
                             WORK / f"raw_{i + 1:02d}.mp4")
        # 전환이 먹을 여분(xdur)을 붙여 둔다. concat_with_transitions 가 정확히 그만큼 쓴다.
        clips.append(video.normalize_scene(str(raw), dur + xdur,
                                           str(WORK / f"scene_{i + 1:02d}.mp4"),
                                           width=width, height=height))

    # 3. 전역 타임라인으로 가라오케 자막
    print("가라오케 자막 생성")
    lines, offset = [], 0.0
    for a, dur in zip(audios, durs):
        for ln in a.lines:
            lines.append({
                "start": ln["start"] + offset,
                "end": ln["end"] + offset,
                "words": [(s + offset, d, w) for s, d, w in ln["words"]],
            })
        offset += dur
    font_name, fonts_dir = video.pick_font()
    ass = subtitle.build_karaoke_ass(lines, str(WORK / "sub.ass"), font=font_name,
                                     highlight=highlight, video_w=width, video_h=height)

    # 4. 합성 → 최종 렌더
    print("합성 및 최종 렌더링")
    narration = video.build_narration_track([a.audio for a in audios], durs, str(WORK))
    joined = video.concat_with_transitions(clips, durs, str(WORK), xdur=xdur)
    final = video.finalize(joined, narration, ass, str(WORK / "final.mp4"),
                           width=width, fonts_dir=fonts_dir)

    # 5. Release 업로드(없으면 만들고, 같은 이름이 있으면 먼저 지운다)
    # 태그 접두어를 프로젝트로 나눈다. 이 저장소엔 coupang 쪽 `shorts-cand` 등
    # 다른 프로젝트의 릴리스가 같이 살아서, 접두어가 겹치면 목록이 뒤섞인다.
    tag = f"moviegen-{cid}"
    rel = gh(f"/repos/{repo}/releases/tags/{tag}", token, allow404=True)
    if rel is None:
        rel = gh(f"/repos/{repo}/releases", token, method="POST",
                 data=json.dumps({
                     "tag_name": tag, "name": f"숏폼 동화 {cid}",
                     "body": "완성된 쇼츠 영상입니다.", "make_latest": "false",
                 }).encode(), content_type="application/json")
    name = "final.mp4"
    old = next((a for a in rel.get("assets", []) if a["name"] == name), None)
    if old:
        gh(f"/repos/{repo}/releases/assets/{old['id']}", token, method="DELETE")
    data = Path(final).read_bytes()
    up = gh(f"/repos/{repo}/releases/{rel['id']}/assets?name={name}", token,
            method="POST", data=data, content_type="video/mp4",
            base="https://uploads.github.com")

    # 다음에 다시 만들 때는 추정치가 아니라 실제로 잰 길이를 보여 준다.
    for sc, a in zip(record["scenes"], audios):
        sc["actual_seconds"] = round(a.speech_duration + tail_pad, 1)

    record["status"] = "rendered"
    record["video"] = up["browser_download_url"]
    record["duration"] = round(offset, 1)
    record["resolution"] = f"{width}x{height}"
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"완료: {up['browser_download_url']} ({offset:.1f}초, {width}x{height})")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"## 렌더링 완료\n\n{record['title']} — {offset:.1f}초 · {width}x{height}\n\n"
                    f"{up['browser_download_url']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
