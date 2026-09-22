"""AI 숏폼 동화 스튜디오 — 주제 하나로 9:16 전래동화 쇼츠를 반자동 제작.

흐름: 주제 입력 → 대본·영상프롬프트 생성 → (외부 툴로 만든) 씬 영상 업로드
      → 나레이션·가라오케 자막 자동 생성 → 최종 MP4 렌더링·다운로드
"""
from __future__ import annotations

import shutil
import tempfile
import traceback
from pathlib import Path

import streamlit as st

from core import llm, subtitle, tts, video

st.set_page_config(page_title="AI 숏폼 동화 스튜디오", layout="centered")

# 모바일에서 손가락으로 누르기 쉬운 크기 + 세로 화면 가독성
st.markdown("""
<style>
  .block-container {padding: 1rem 0.9rem 5rem;}
  .stButton > button, .stDownloadButton > button {
      min-height: 3rem; font-size: 1.02rem; font-weight: 600; border-radius: 12px;
  }
  .stTextArea textarea, .stTextInput input {font-size: 1rem;}
  [data-testid="stFileUploaderDropzone"] {padding: 1rem 0.8rem;}
  [data-testid="stMetricValue"] {font-size: 1.15rem;}
  h1 {font-size: 1.5rem !important;} h2 {font-size: 1.2rem !important;}
  @media (max-width: 640px) {
      [data-testid="stFileUploaderDropzoneInstructions"] > div > span {display: none;}
  }
</style>
""", unsafe_allow_html=True)

S = st.session_state
S.setdefault("board", None)
S.setdefault("result", None)
S.setdefault("workdir", None)


def secret(name: str) -> str:
    """secrets.toml이 없는 환경(로컬 첫 실행)에서도 죽지 않게 감싼다."""
    try:
        return st.secrets.get(name, "")
    except Exception:  # noqa: BLE001
        return ""


def workdir() -> Path:
    if not S.workdir or not Path(S.workdir).is_dir():
        S.workdir = tempfile.mkdtemp(prefix="shorts_studio_")
    return Path(S.workdir)


# ── 사이드바: 설정 ─────────────────────────────────────────────
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Gemini API Key", type="password",
                            value=secret("GEMINI_API_KEY"),
                            help="저장되지 않고 이 세션에서만 쓰입니다.")
    model = st.selectbox("대본 생성 모델", llm.MODELS, index=0)

    st.divider()
    st.subheader("음성")
    engine = st.radio("성우 엔진", ["gemini", "edge"], horizontal=True,
                      format_func=lambda e: "Gemini (감정 연기)" if e == "gemini" else "Edge (무료·빠름)")
    _voices = tts.GEMINI_VOICES if engine == "gemini" else tts.EDGE_VOICES
    voice = st.selectbox("성우", list(_voices), format_func=lambda v: _voices[v])
    speed = st.slider("말하기 속도", -30, 30, -5, 5, format="%d%%",
                      help="동화 낭독은 조금 느린 편(-10% 안팎)이 잘 어울립니다.")

    st.divider()
    st.subheader("자막·화질")
    highlight = st.selectbox("하이라이트 색", list(subtitle.HIGHLIGHTS))
    preset = st.selectbox("출력 해상도", list(video.PRESETS), index=0)
    tail_pad = st.slider("씬 끝 여백(초)", 0.0, 1.5, 0.4, 0.1,
                         help="대사가 끝나고 화면이 잠깐 머무는 시간입니다.")

WIDTH, HEIGHT = video.PRESETS[preset]

st.title("AI 숏폼 동화 스튜디오")
st.caption("한국 전래동화 쇼츠(9:16)를 반자동으로 만듭니다.")

step1, step2, step3 = st.tabs(["① 대본·프롬프트", "② 영상 업로드", "③ 렌더링"])

# ── ① 기획 ────────────────────────────────────────────────────
with step1:
    topic = st.text_area("동화 주제", height=90,
                         placeholder="예) 욕심 많은 형과 착한 아우가 나눠 가진 신기한 박씨")
    c1, c2 = st.columns(2)
    n_scenes = c1.number_input("컷 수", 3, 6, 4)
    tool = c2.selectbox("영상 생성 툴", list(llm.TOOLS))
    st.caption(llm.TOOLS[tool]["ui_note"])

    if st.button("대본 + 영상 프롬프트 생성", type="primary", width="stretch"):
        if not api_key:
            st.error("사이드바에 Gemini API Key를 먼저 입력하세요.")
        elif not topic.strip():
            st.error("동화 주제를 입력하세요.")
        else:
            with st.spinner("이야기를 짓는 중입니다…"):
                try:
                    S.board = llm.generate_storyboard(api_key, topic.strip(),
                                                      int(n_scenes), tool, model)
                    S.result = None
                except Exception as e:  # noqa: BLE001
                    st.error(f"생성에 실패했습니다: {e}")

    if S.board:
        b = S.board
        st.success(f"제목: {b.title}")
        for i, sc in enumerate(b.scenes):
            with st.expander(f"{i + 1}번 씬 — {sc.visual or '화면'}", expanded=(i == 0)):
                sc.narration = st.text_area("나레이션 (수정 가능)", sc.narration,
                                            key=f"nar{i}", height=90)
                st.text_area("영상 생성 프롬프트 (복사해서 사용)", sc.prompt,
                             key=f"pr{i}", height=120)
                if sc.negative:
                    st.text_area("네거티브 프롬프트", sc.negative, key=f"ng{i}", height=68)
        if b.hashtags:
            st.text_input("해시태그", " ".join(b.hashtags))
        st.info("프롬프트를 복사해 영상 생성 툴에서 씬별 영상을 만든 뒤, ② 탭에서 업로드하세요.")

# ── ② 업로드 ──────────────────────────────────────────────────
with step2:
    if not S.board:
        st.info("먼저 ① 탭에서 대본을 생성하세요.")
    else:
        st.write(f"**{len(S.board.scenes)}개 씬**의 영상을 순서대로 올려 주세요. (mp4 · mov)")
        uploads = []
        for i, sc in enumerate(S.board.scenes):
            f = st.file_uploader(f"{i + 1}번 씬 — {sc.visual or ''}",
                                 type=["mp4", "mov", "m4v"], key=f"up{i}")
            uploads.append(f)
            if f:
                st.video(f)
        S.uploads_ready = all(u is not None for u in uploads)
        S.uploads = uploads
        if S.uploads_ready:
            st.success("모든 씬이 준비됐습니다. ③ 탭에서 렌더링하세요.")

# ── ③ 렌더링 ──────────────────────────────────────────────────
with step3:
    if not S.board:
        st.info("먼저 ① 탭에서 대본을 생성하세요.")
    elif not S.get("uploads_ready"):
        st.info("② 탭에서 모든 씬 영상을 업로드하세요.")
    else:
        st.write(f"출력 규격: **{WIDTH}×{HEIGHT}** · 성우 **{(tts.GEMINI_VOICES | tts.EDGE_VOICES)[voice].split(' (')[0]}**")
        if st.button("최종 영상 만들기", type="primary", width="stretch"):
            prog = st.progress(0.0, "준비 중…")
            try:
                video.ensure_ffmpeg()
                work = workdir()
                for old in work.glob("*"):
                    old.unlink(missing_ok=True) if old.is_file() else shutil.rmtree(old, True)

                scenes = S.board.scenes
                n = len(scenes)

                # 1. 씬별 나레이션 합성 + 단어 타임스탬프
                audios = []
                for i, sc in enumerate(scenes):
                    prog.progress(0.05 + 0.25 * i / n, f"{i + 1}번 씬 음성 합성 중…")
                    audios.append(tts.synthesize_scene(
                        i, sc.narration, str(work), engine=engine, api_key=api_key,
                        voice=voice, rate=f"{speed:+d}%",
                        direction=getattr(sc, "voice_direction", "")))

                scene_durs = [a.speech_duration + tail_pad for a in audios]

                # 2. 씬 영상 업로드본 저장 → 9:16 정규화 + 길이 맞춤
                clips = []
                for i, (up, dur) in enumerate(zip(S.uploads, scene_durs)):
                    prog.progress(0.30 + 0.40 * i / n, f"{i + 1}번 씬 영상 규격 변환 중…")
                    raw = work / f"raw_{i + 1:02d}{Path(up.name).suffix.lower()}"
                    raw.write_bytes(up.getbuffer())
                    clips.append(video.normalize_scene(
                        str(raw), dur, str(work / f"scene_{i + 1:02d}.mp4"),
                        width=WIDTH, height=HEIGHT))

                # 3. 전역 타임라인 기준으로 가라오케 자막 줄 구성
                prog.progress(0.72, "가라오케 자막 만드는 중…")
                lines, offset = [], 0.0
                for a, dur in zip(audios, scene_durs):
                    for ln in a.lines:
                        lines.append({
                            "start": ln["start"] + offset,
                            "end": ln["end"] + offset,
                            "words": [(s + offset, d, w) for s, d, w in ln["words"]],
                        })
                    offset += dur
                font_name, fonts_dir = video.pick_font()
                ass = subtitle.build_karaoke_ass(
                    lines, str(work / "sub.ass"), font=font_name,
                    highlight=highlight, video_w=WIDTH, video_h=HEIGHT)

                # 4. 합성 → 최종 렌더
                prog.progress(0.78, "영상·오디오 이어붙이는 중…")
                narration = video.build_narration_track(
                    [a.audio for a in audios], scene_durs, str(work))
                joined = video.concat_videos(clips, str(work))

                prog.progress(0.85, "자막을 입혀 최종 렌더링 중… (가장 오래 걸립니다)")
                out = video.finalize(joined, narration, ass, str(work / "final.mp4"),
                                     width=WIDTH, height=HEIGHT, fonts_dir=fonts_dir,
                                     band_top=0.08, band_bottom=0.16)

                prog.progress(1.0, "완성!")
                S.result = {"path": out, "duration": offset}
            except Exception as e:  # noqa: BLE001
                prog.empty()
                st.error(f"렌더링에 실패했습니다: {e}")
                with st.expander("자세한 오류"):
                    st.code(traceback.format_exc())

    if S.result:
        st.success(f"완성! 총 길이 약 {S.result['duration']:.1f}초")
        data = Path(S.result["path"]).read_bytes()
        st.video(data)
        st.download_button("영상 내려받기 (MP4)", data,
                           file_name=f"{(S.board.title if S.board else 'shorts')}.mp4",
                           mime="video/mp4", type="primary", width="stretch")
