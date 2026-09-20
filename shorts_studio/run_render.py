"""② 업로드된 씬 영상 + 대본 → 나레이션·가라오케 자막 → 최종 MP4 → Release 업로드.

GitHub Actions에서 실행된다(관리자 페이지가 호출).
씬 영상은 관리자 페이지가 **클라우드플레어 보관함(KV)** 에 올려 둔 것을 받아 온다
(BLOBS 입력에 주소 목록이 들어온다). 깃허브로 직접 올리지 않으므로 브라우저 CORS
문제도, 관리자 토큰의 쓰기 권한도 필요 없다 — verdict-theater 에서 검증된 방식.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

from core import subtitle, tts, video

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


def download_blob(url: str, password: str, dest: Path) -> Path:
    """보관함(KV)에서 씬 영상 내려받기. 워커는 쿠키 대신 비밀번호 헤더로 확인한다."""
    req = urllib.request.Request(url)
    req.add_header("x-ss-pass", password)
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
    password = os.environ.get("ADMIN_PASSWORD", "").strip()
    if not (token and repo and cid):
        print("::error::GITHUB_TOKEN / GITHUB_REPOSITORY / CONTENT_ID 가 필요합니다.")
        return 1

    record_path = CONTENT_DIR / f"{cid}.json"
    if not record_path.exists():
        print(f"::error::대본 파일이 없습니다: {record_path}")
        return 1
    record = json.loads(record_path.read_text(encoding="utf-8"))
    scenes = record["scenes"]

    blobs = json.loads(os.environ.get("BLOBS", "[]"))
    if len(blobs) != len(scenes):
        print(f"::error::씬은 {len(scenes)}개인데 영상 주소는 {len(blobs)}개입니다. "
              "관리자 페이지에서 모든 씬 영상을 올렸는지 확인하세요.")
        return 1

    video.ensure_ffmpeg()
    WORK.mkdir(parents=True, exist_ok=True)
    width, height = (1080, 1920) if os.environ.get("HQ") == "true" else (720, 1280)
    voice = os.environ.get("VOICE", "ko-KR-SunHiNeural")
    rate = os.environ.get("RATE", "-5%")
    highlight = os.environ.get("HIGHLIGHT", "노란색")
    tail_pad = float(os.environ.get("TAIL_PAD", "0.4"))

    # 1. 씬별 나레이션 합성 (단어 타임스탬프 포함)
    audios = []
    for i, sc in enumerate(scenes):
        print(f"[{i + 1}/{len(scenes)}] 음성 합성")
        audios.append(tts.synthesize_scene(i, sc["narration"], str(WORK),
                                           voice=voice, rate=rate))
    durs = [a.speech_duration + tail_pad for a in audios]

    # 2. 보관함에서 씬 영상 받아 9:16 규격·길이 맞춤
    clips = []
    for i, dur in enumerate(durs):
        print(f"[{i + 1}/{len(scenes)}] 영상 내려받아 규격 변환")
        raw = download_blob(blobs[i], password, WORK / f"raw_{i + 1:02d}.mp4")
        clips.append(video.normalize_scene(str(raw), dur, str(WORK / f"scene_{i + 1:02d}.mp4"),
                                           width=width, height=height))

    # 3. 전역 타임라인으로 가라오케 자막
    print("가라오케 자막 생성")
    lines, offset = [], 0.0
    for a, dur in zip(audios, durs):
        for ln in tts.group_words_into_lines(a.words, a.text):
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
    narration = video.build_narration_track([a.mp3 for a in audios], durs, str(WORK))
    joined = video.concat_videos(clips, str(WORK))
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
