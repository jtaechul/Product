"""② 업로드된 씬 영상 + 대본 → 나레이션·가라오케 자막 → 최종 MP4 → Release 업로드.

GitHub Actions에서 실행된다(관리자 페이지가 호출).
씬 영상은 관리자 페이지가 릴리스 `moviegen-<id>` 에 `scene01.mp4` 형태로 올려 둔 것을 쓴다.
"""
from __future__ import annotations

import json
import os
import sys
import time
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
    rate = os.environ.get("RATE", "-5%")

    # ⭐ 성우·자막색 자동 맞춤. 대본이 태담용이면 따뜻한 여성 목소리에 노란 자막,
    # 어른용이면 낮은 남성 목소리에 핏빛 자막이 기본이다. 운영자가 화면에서 직접
    # 고르면 그 선택이 언제나 이긴다("자동"이 아닐 때).
    mode = str(record.get("mode") or "태담용")
    auto_voice = str(record.get("voice") or "") or ("Charon" if mode == "어른용" else "Sulafat")
    auto_hi = str(record.get("highlight") or "") or ("붉은색" if mode == "어른용" else "노란색")

    def picked(env_name: str, auto_value: str) -> str:
        v = os.environ.get(env_name, "").strip()
        return auto_value if (not v or v == "자동") else v

    voice = picked("VOICE", auto_voice)
    highlight = picked("HIGHLIGHT", auto_hi)
    print(f"대본 결: {mode} · 성우 {voice} · 자막 {highlight}")
    tail_pad = float(os.environ.get("TAIL_PAD", "0.5"))
    # 전환은 씬 끝 여백 안에서 일어나게 한다. 여백보다 길면 대사 위로 화면이 섞인다.
    xdur = min(float(os.environ.get("XFADE", "0.4")), tail_pad)
    # 자막 한 줄 길이 = Gemini 성우의 합성 단위. 늘리면 호출 수가 줄어 빠르고 할당량을
    # 덜 쓰지만, 줄 안에서의 어절 하이라이트가 그만큼 어림값이 된다.
    max_chars = int(os.environ.get("SUB_MAX_CHARS", "20"))
    # Gemini 성우는 자막 한 줄이 곧 호출 한 번이라 할당량을 빨리 태운다.
    # 호출 사이에 조금씩 쉬어 분당 제한을 덜 건드린다.
    gap = float(os.environ.get("TTS_GAP", "1.0"))
    # 영상 생성 AI가 화면 구석에 박는 워터마크를 검은 띠로 덮는다(화면 높이 비율).
    # 아래가 더 두껍다 — 워터마크는 오른쪽 아래에만 박히고, 실측해 보니 8%로는
    # 워터마크 바로 아래까지만 덮여 하나도 안 가려졌다.
    band_top = float(os.environ.get("BAND_TOP", os.environ.get("BAND", "0.08")))
    band_bottom = float(os.environ.get("BAND_BOTTOM", "0.16"))
    cover_sec = float(os.environ.get("COVER_SEC", "1.8"))
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
    want_cover = cover_sec > 0 and "cover.png" in assets
    title = " ".join(str(record.get("title", "")).split())

    def synth_all(eng: str, v: str):
        # 표지에서 제목도 읽어 준다. 씬과 **같은 성우·같은 페르소나**로 뽑아야
        # 표지에서 본문으로 넘어갈 때 목소리가 바뀌지 않는다.
        head = None
        if want_cover and title:
            print(f"[표지] 제목 읽기 ({eng})")
            head = tts.synthesize_scene(
                -1, title, str(WORK), engine=eng, api_key=gemini_key, voice=v,
                rate=rate, direction=tts.TITLE_DIRECTION, max_chars=40, gap=gap)
        out = []
        for i, sc in enumerate(scenes):
            print(f"[{i + 1}/{len(scenes)}] 음성 합성 ({eng})")
            out.append(tts.synthesize_scene(
                i, sc["narration"], str(WORK),
                engine=eng, api_key=gemini_key, voice=v, rate=rate,
                direction=sc.get("voice_direction", ""), max_chars=max_chars,
                gap=gap,
            ))
        return head, out

    try:
        head, audios = synth_all(engine, voice)
    except tts.FallbackError as e:
        # 할당량이 바닥났거나(QuotaError) 구글이 그 TTS 모델을 닫았다고(ModelError)
        # 영상까지 못 만들 이유는 없다. 무료 성우로 갈아타 끝까지 뽑는다.
        # 목소리는 밋밋해지지만 빈손으로 끝나지는 않는다.
        # (목소리가 섞이지 않게 처음부터 다시 합성한다)
        print(f"::warning::{e} 무료 성우(Edge)로 바꿔 끝까지 만듭니다. "
              "감정 연기를 쓰려면 관리자 페이지 설정에서 결제된 개인 API 키를 넣으세요.")
        engine = "edge"
        voice = tts.FALLBACK_VOICE.get(voice, "ko-KR-SunHiNeural")
        head, audios = synth_all(engine, voice)
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

    # 2-1. 표지를 맨 앞에 붙인다(올려 뒀을 때만). 제목을 읽어 주고, 그 길이에 맞춰
    #      표지가 머무는 시간을 정한다 — 고정 시간으로 두면 말이 잘리거나 남는다.
    #      뒤따르는 모든 자막이 표지 길이만큼 밀린다 — 이 계산이 틀어지면 말과 글자가 어긋난다.
    parts = [a.audio for a in audios]
    cover_dur = 0.0
    if want_cover:
        print("표지 붙이기")
        img = download_asset(assets["cover.png"]["url"], token, WORK / "cover.png")
        lead, tail = 0.35, 0.65          # 제목 읽기 전후의 한 박자
        if head:
            cover_dur = max(cover_sec, lead + head.speech_duration + tail)
            narr0 = video.pad_lead(head.audio, lead, str(WORK / "narr_00.wav"))
        else:
            cover_dur = cover_sec
            narr0 = video.make_silence(cover_dur, str(WORK / "narr_00.wav"))
        clips.insert(0, video.make_cover(str(img), cover_dur + xdur,
                                         str(WORK / "scene_00.mp4"),
                                         width=width, height=height))
        durs.insert(0, cover_dur)
        parts.insert(0, narr0)           # 남는 뒤쪽은 build_narration_track 이 무음으로 채운다
        print(f"  표지 {cover_dur:.2f}초 (제목 낭독 {head.speech_duration:.2f}초)"
              if head else f"  표지 {cover_dur:.2f}초 (무음)")
    else:
        print("표지 없음 — 건너뜁니다.")

    # 3. 전역 타임라인으로 가라오케 자막
    print("가라오케 자막 생성")
    lines, offset = [], cover_dur
    for a, dur in zip(audios, durs[1:] if cover_dur else durs):
        for ln in a.lines:
            lines.append({
                "start": ln["start"] + offset,
                "end": ln["end"] + offset,
                "words": [(s + offset, d, w) for s, d, w in ln["words"]],
            })
        offset += dur
    font_name, fonts_dir = video.pick_font()
    ass = subtitle.build_karaoke_ass(lines, str(WORK / "sub.ass"), font=font_name,
                                     highlight=highlight, video_w=width, video_h=height,
                                     cover_title=record.get("title", "") if cover_dur else "",
                                     cover_end=max(0.0, cover_dur - 0.15),
                                     bottom_px=video.band_px(height, band_bottom))

    # 4. 합성 → 최종 렌더
    print("합성 및 최종 렌더링")
    narration = video.build_narration_track(parts, durs, str(WORK))
    joined = video.concat_with_transitions(clips, durs, str(WORK), xdur=xdur)
    final = video.finalize(joined, narration, ass, str(WORK / "final.mp4"),
                           width=width, height=height, fonts_dir=fonts_dir,
                           band_top=band_top, band_bottom=band_bottom)

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
    # 주소가 같아도 내용은 바뀌었으니, 화면이 옛 영상을 캐시해 보여 주지 않게 표시를 남긴다.
    record["video"] = up["browser_download_url"]
    record["rendered_at"] = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    record["duration"] = round(offset, 1)
    record["resolution"] = f"{width}x{height}"
    record["voice_used"] = f"{engine}:{voice}"    # 할당량 때문에 바뀌었을 수 있다
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
