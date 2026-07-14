"""회귀: 침몰선은 아마추어 다이빙 '영상'을 소스로 절대 쓰지 않는다(Batelo 사고 재발방지).

wreck 키에 media_kind가 없는(=구 방식 video) 시드가 있어도, 사진·다큐가 없으면 raw 영상으로
폴백하지 않고 None을 반환해야 한다(→ auto 후보 순회가 다음 대상으로). 네트워크 없이 검증하기 위해
사진·다큐 확보 함수를 None으로 모킹한다."""
from src.core import footage as F


def test_wreck_video_seed_never_falls_back_to_raw_video(monkeypatch, tmp_path):
    key = "wreck someobscurewreck"
    # 구 방식(video) 시드 주입 — media_kind 없음(=예전 아마추어 영상 후보 형태)
    monkeypatch.setitem(F._SEED, key, {
        "url": "https://commons.example/Some_Obscure_Wreck_dive.webm",
        "license": "cc-by", "credit": "x", "source": "x"})
    # 사진·다큐 확보 실패 상황 모킹(무명 난파선 → 둘 다 없음)
    monkeypatch.setattr(F, "_wreck_photo_footage", lambda *a, **k: None)
    monkeypatch.setattr(F, "_wreck_doc_footage", lambda *a, **k: None)

    fv = F.fetch_footage("Wreck SomeObscureWreck", "Wreck SomeObscureWreck", str(tmp_path))
    assert fv is None            # raw 영상 폴백 금지 → None(다음 후보로 넘어감)


def test_wreck_prefers_photo_kenburns_when_available(monkeypatch, tmp_path):
    key = "wreck haswreckphoto"
    monkeypatch.setitem(F._SEED, key, {
        "url": "https://commons.example/x.webm", "license": "cc-by", "credit": "x", "source": "x"})
    sentinel = {"path": "/tmp/kb.mp4", "license": "cc-by", "credit": "photo",
                "source": "s", "logo_box": None}
    monkeypatch.setattr(F, "_wreck_photo_footage", lambda *a, **k: sentinel)
    # 사진이 있으면 다큐를 부르기 전에 사진 켄번즈를 쓴다
    monkeypatch.setattr(F, "_wreck_doc_footage", lambda *a, **k: {"doc": True})
    fv = F.fetch_footage("Wreck HasWreckPhoto", "Wreck HasWreckPhoto", str(tmp_path))
    assert fv is sentinel
