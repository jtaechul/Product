"""첨부 영상 나레이션 — 오케스트레이션 E2E(실제 ffmpeg 체인, TTS만 모의)."""
import subprocess
from pathlib import Path
import pytest
from src.core import narrate_attached as N


def test_jp_chunks_fallback():
    """LLM 없이 제목·설명을 자막 청크로 분절(날조 없이 준 텍스트만)."""
    ch = N._jp_chunks_from_notes("深海の沈没船", "潜水艦の残骸です。水深およそ100メートル。", 18)
    assert ch and all(len(c) <= 24 for c in ch)
    assert N._jp_chunks_from_notes("", "") == []


def _fake_tts(work):
    Path(work).mkdir(parents=True, exist_ok=True)
    mp3 = str(Path(work) / "narration.mp3")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=mono", "-t", "5", "-q:a", "9", mp3], check=True)
    disp = [("深海の", 0.2, 1.4), ("沈没船です。", 1.6, 3.2), ("水深百m。", 3.4, 4.8)]
    return {"mp3": mp3, "words": [("x", 0.2, 4.6)], "disp": disp, "duration": 4.8}


@pytest.mark.parametrize("mode,w,h", [("shorts", 720, 1280), ("longform", 1920, 1080)])
def test_narrate_attached_e2e(tmp_path, monkeypatch, mode, w, h):
    # 합성 가로 소스 영상(8s)
    vid = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=1280x720:rate=30:duration=8", "-pix_fmt", "yuv420p", str(vid)], check=True)
    from src.core import narration_sync, llm
    monkeypatch.setattr(narration_sync, "synthesize", lambda chunks, work, **k: _fake_tts(work))
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: None)   # 결정론 폴백 강제
    monkeypatch.setattr(N, "_clean_watermark", lambda v, w: v)   # delogo는 별도 테스트로
    # 비전 미가용(키 없음) → 소싱 출처 설명(source_topic)을 대본 근거로 사용
    res = N.narrate_video(str(vid), mode=mode, base_dir=str(tmp_path),
                          source_topic="潜水艦の残骸です。水深百m。")
    out = Path(res["path"])
    assert out.exists() and out.stat().st_size > 20_000
    ww = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=width,height", "-of", "csv=p=0:s=x", str(out)],
                        capture_output=True, text=True).stdout.strip()
    assert ww == f"{w}x{h}"
    # 오디오 트랙 존재(나레이션 mux)
    a = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=codec_type", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout
    assert "audio" in a
    # 메타데이터(제목·설명·해시태그·훅, 일/한) 자동 생성 — 폴백이라도 채워짐
    meta = res["meta"]
    assert meta["title_jp"] and meta["desc_jp"] and meta["tags_jp"] and meta["hook_jp"]
    assert Path(res["meta_path"]).exists()
    # 오프닝 훅 + 썸네일: 폰트가 있으면 훅이 붙고 썸네일(jpg)이 나온다
    from src.core import hook_intro as hi
    if hi.fonts_available():
        assert res["hooked"] is True
        assert res["thumb"] and Path(res["thumb"]).exists()
        tw = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                             "stream=width,height", "-of", "csv=p=0:s=x", res["thumb"]],
                            capture_output=True, text=True).stdout.strip()
        assert tw == f"{w}x{h}"


def test_gen_metadata_fallback_and_llm(monkeypatch):
    """대본 → 훅·제목·설명·해시태그(일/한). LLM JSON 우선, 실패 시 결정론 폴백."""
    from src.core import llm
    chunks = ["深海に潜む生き物です。", "静かに漂います。", "神秘的な姿です。"]
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: None)     # 폴백
    fb = N._gen_metadata(chunks, "shorts")
    assert fb["title_jp"] and fb["desc_jp"] and fb["tags_jp"] and fb["tags_ko"] and fb["hook_jp"]
    good = ('{"hook_jp":"深海に潜むもの","title_jp":"深海の神秘","title_ko":"심해의 신비",'
            '"desc_jp":"静かな海の記録です。","desc_ko":"고요한 바다의 기록입니다.",'
            '"tags_jp":["#深海","#海"],"tags_ko":["#심해","#바다"]}')
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: good)
    d = N._gen_metadata(chunks, "shorts")
    assert d["title_ko"] == "심해의 신비" and d["tags_jp"][0] == "#深海"
    assert d["hook_jp"] == "深海に潜むもの"


def test_gen_metadata_uses_title_candidate_when_final_blank(monkeypatch):
    """A안: 최종 title_jp가 비어도 후보(title_candidates)에서 유효안을 채택한다."""
    from src.core import llm
    payload = ('{"subject":"ソコダラ","key_point":"水深千mの記録","title_candidates":'
               '["","【深海】ソコダラの素顔","候補3"],"title_jp":"",'
               '"hook_jp":"深海の主","desc_jp":"記録です。","desc_ko":"기록입니다.",'
               '"tags_jp":["#深海"],"tags_ko":["#심해"]}')
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: payload)
    d = N._gen_metadata(["深海の生き物です。"], "longform", source_topic="")
    assert d["title_jp"] == "【深海】ソコダラの素顔"


def test_hashtags_are_content_based_and_plentiful(monkeypatch):
    """해시태그: LLM은 8~12개 살아남고, 폴백도 대본 내용(대상어·주제)에서 다수 도출(고정 3개 탈피)."""
    from src.core import llm
    chunks = ["水深980mの海底に、ソコダラの仲間が姿を見せます。", "長い尾を引きずるように泳ぎます。"]
    # 폴백(LLM 미가용): 내용 기반 태그 + 종명(ソコダラ) 포함, 고정 3개(#海/#自然/#癒し)만은 아님
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: None)
    fb = N._gen_metadata(chunks, "longform", source_topic="Macrouridae deep-sea fish")
    assert "#深海" in fb["tags_jp"] and "#ソコダラ" in fb["tags_jp"]
    assert fb["tags_jp"] != ["#海", "#自然", "#癒し"]
    # LLM 정상: 8개 태그가 상한(12) 안에서 모두 유지
    many = ('{"subject":"ソコダラ","title_candidates":["a"],"title_jp":"【深海】ソコダラの記録",'
            '"title_ko":"기록","hook_jp":"深海の主","desc_jp":"記録です。","desc_ko":"기록.",'
            '"tags_jp":["#深海","#ソコダラ","#深海魚","#海洋生物","#生き物","#自然","#水中映像","#ドキュメンタリー"],'
            '"tags_ko":["#심해","#해양생물"]}')
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: many)
    d = N._gen_metadata(chunks, "longform")
    assert len(d["tags_jp"]) == 8 and "#ドキュメンタリー" in d["tags_jp"]


def test_fallback_title_prefers_facts_over_first_sentence():
    """A안 폴백: 밋밋한 1인칭 상황 서술보다 수심 사실 템플릿/구체 절을 제목으로."""
    # ① 대본에 수심이 실제로 있으면 【深海】…水深○mの記録 템플릿
    chunks = ["私たちはちょうど、ある海域のマッピングを終えたところです。",
              "水深1200mでソコダラが現れます。"]
    t = N._fallback_title_jp(chunks)
    assert "水深1200m" in t and len(t) <= 30
    # ② 수심이 없으면 최소한 1인칭 상황 서술 그대로를 제목으로 쓰지 않는다(구체 절 우선)
    chunks2 = ["私たちはちょうど、ある海域のマッピングを終えたところです。",
               "3匹のダイオウイカが確認されました。"]
    t2 = N._fallback_title_jp(chunks2)
    assert "マッピング" not in t2 and len(t2) <= 30


def test_hook_and_thumb_render(tmp_path):
    """훅/썸네일 렌더 — 배경 프레임 위에 훅 문구를 얹어 카드+썸네일(jpg) 생성."""
    from src.core import hook_intro as hi
    if not hi.fonts_available():
        import pytest as _pt
        _pt.skip("CJK 폰트 없음")
    from PIL import Image
    bg = tmp_path / "bg.jpg"
    Image.new("RGB", (1280, 720), (20, 40, 60)).save(bg)
    card = tmp_path / "card.png"; thumb = tmp_path / "thumb.jpg"
    ok = N._render_hook_and_thumb(str(bg), "深海の未知の光景", "深海生物ドキュメント",
                                  1920, 1080, str(card), str(thumb))
    assert ok and card.exists() and thumb.exists()
    assert Image.open(str(thumb)).size == (1920, 1080)


def test_longform_keeps_full_length_and_chapters(tmp_path, monkeypatch):
    """★롱폼: 원본을 나레이션 길이로 자르지 않고 전체 길이를 유지하며, 나레이션을 분산 배치하고
    설명란에 타임스탬프(챕터)를 넣는다."""
    vid = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=1280x720:rate=24:duration=24", "-pix_fmt", "yuv420p", str(vid)], check=True)
    from src.core import narration_sync, llm

    def fake_tts(chunks, work, **k):
        Path(work).mkdir(parents=True, exist_ok=True)
        mp3 = str(Path(work) / "narration.mp3")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                        "-i", "sine=frequency=280:duration=4", "-q:a", "9", mp3], check=True)
        disp = [("深海の", 0.2, 2.0), ("記録です。", 2.1, 3.8)]
        return {"mp3": mp3, "words": [("x", 0.2, 3.7)], "disp": disp, "duration": 3.8}

    monkeypatch.setattr(narration_sync, "synthesize", fake_tts)
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: None)      # 결정론 폴백
    monkeypatch.setattr(N, "_clean_watermark", lambda v, w: v)
    monkeypatch.setattr(N, "_render_hook_and_thumb", lambda *a, **k: False)   # 훅 생략 → 길이 판정 단순화
    res = N.narrate_video(str(vid), mode="longform", base_dir=str(tmp_path),
                          source_topic="潜水艦の残骸を捉えた映像です。水深はおよそ百メートル。周囲は暗く静かです。")
    out = Path(res["path"])

    def _dur(p):
        return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                     "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout.strip())
    orig = _dur(vid)
    got = _dur(out)
    # ★핵심: 나레이션(짧음)이 아니라 원본 전체 길이(24s)를 유지 — 예전엔 ~4s로 잘렸다
    assert got >= orig - 1.5, f"output {got:.1f}s must keep full source {orig:.1f}s (not narration length)"
    # 챕터 + 타임스탬프가 설명란에 삽입되고, 첫 챕터는 00:00
    assert res["chapters"], "chapters must be generated for longform"
    assert "チャプター" in res["meta"]["desc_jp"] and "00:00" in res["meta"]["desc_jp"]
    assert "챕터" in res["meta"]["desc_ko"]


def test_audio_mix_and_active_regions(tmp_path):
    """★#1·#2: 원본 오디오 보존+덕킹 믹스 + 원본 발화(소리) 구간 검출.
    무음 소스는 나레이션만, 오디오 소스는 믹스 파일 + active 구간 검출."""
    mp3 = tmp_path / "n.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=300:duration=2", "-q:a", "9", str(mp3)], check=True)
    # (a) 무음 영상 → _has_audio False, 믹스는 나레이션 그대로
    v0 = tmp_path / "noaud.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=black:s=320x240:r=10:d=3", "-pix_fmt", "yuv420p", str(v0)], check=True)
    assert N._has_audio(str(v0)) is False
    assert N._mix_bg_narration(str(v0), str(mp3), 3.0, tmp_path) == str(mp3)
    assert N._audio_active_regions(str(v0), 3.0) == []
    # (b) 앞 2s 무음 + 뒤 2s 톤 → 뒤쪽에 active 구간, 믹스는 새 파일
    v1 = tmp_path / "aud.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=black:s=320x240:r=10:d=4",
                    "-f", "lavfi", "-i", "sine=frequency=400:duration=4",
                    "-filter_complex", "[1:a]volume=volume='if(gt(t,2),0.9,0)':eval=frame[a]",
                    "-map", "0:v", "-map", "[a]", "-t", "4", "-pix_fmt", "yuv420p", "-c:a", "aac", str(v1)], check=True)
    assert N._has_audio(str(v1)) is True
    regs = N._audio_active_regions(str(v1), 4.0)
    assert any(b > 2.0 for a, b in regs), f"뒤쪽(발화) 구간 검출 실패: {regs}"
    out = N._mix_bg_narration(str(v1), str(mp3), 4.0, tmp_path)
    assert out != str(mp3) and Path(out).exists() and Path(out).stat().st_size > 2000


def test_clean_watermark_graceful(tmp_path):
    """로고 없는 영상 → 검출 박스 없음 → 원본 그대로 반환(정리 생략, 발행 불정지)."""
    vid = tmp_path / "plain.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=blue:s=320x240:rate=10:duration=2", "-pix_fmt", "yuv420p", str(vid)], check=True)
    out = N._clean_watermark(str(vid), tmp_path / "wm")
    assert out == str(vid)
    assert N._probe_wh(str(vid)) == (320, 240)


def test_clean_watermark_applies_delogo(tmp_path, monkeypatch):
    """검출 박스가 있으면 그 영역을 delogo로 지운다(OCR 우회 결정론 · 길이 기준 검증)."""
    vid = tmp_path / "noaa.mp4"
    vf = "drawtext=text='OCEANEXPLORER.NOAA.GOV':x=(w-tw)/2:y=h-52:fontsize=34:fontcolor=white"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=0x0a1a2a:s=640x360:rate=12:duration=3", "-vf", vf,
                    "-pix_fmt", "yuv420p", str(vid)], check=True)
    monkeypatch.setattr(N, "_watermark_boxes", lambda video, dur: [(0.18, 0.86, 0.64, 0.10)])
    out = N._clean_watermark(str(vid), tmp_path / "wm")
    from pathlib import Path as _P
    assert out != str(vid) and _P(out).exists()
    assert N._probe_wh(out) == (640, 360)
    assert N._probe_dur(out) >= 2.4


def test_narrate_requires_content(tmp_path, monkeypatch):
    """비전 불가 + 출처 설명 없음 → 날조 대신 명확히 실패."""
    vid = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=320x240:rate=15:duration=2", "-pix_fmt", "yuv420p", str(vid)], check=True)
    monkeypatch.setattr(N, "_describe_video", lambda *a, **k: "")       # 비전 미가용
    with pytest.raises(ValueError):
        N.narrate_video(str(vid), mode="shorts", base_dir=str(tmp_path), source_topic="")
