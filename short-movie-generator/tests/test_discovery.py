"""discovery(자동 발굴) 오프라인 단위 테스트 — 네트워크 없이 순수 로직만 검증.

핵심: ① 라이선스 정규화(CC-BY-SA 오픈) ② 해양생물 필터(조류·사체 클립 배제)
③ discovered.json 저장/로드 라운드트립 ④ discovered 종이 SPECIES/_SEED에 병합.
"""
from src.core import discovery


def test_norm_license_opens_cc_by_sa():
    assert discovery._norm_license("CC BY-SA 4.0") == "cc-by-sa"
    assert discovery._norm_license("CC0 1.0") == "cc0"
    assert discovery._norm_license("Public domain") == "public-domain"
    assert discovery._norm_license("CC BY 3.0") == "cc-by"
    assert discovery._norm_license("CC BY-NC 4.0") is None   # 비상업은 여전히 차단


def test_marine_filter_accepts_sea_creatures():
    assert discovery._MARINE.search("深海にすむ甲殻類のエビ")
    assert discovery._MARINE.search("a deep-sea hydrothermal vent shrimp")


def test_marine_filter_rejects_birds_and_bad_clips():
    # 바닷새(조류)는 배제 — 해양 단어가 섞여도 _EXCLUDE가 우선
    assert discovery._EXCLUDE.search("コアホウドリは海鳥で、鳥類に分類される")
    assert discovery._EXCLUDE.search("Laysan albatross, a seabird")
    # ★파충류(도마뱀붙이) 배제 — 일본어 분류군어까지(회귀: gekko japonicus가 후보로 새던 사고)
    assert discovery._EXCLUDE.search("ニホンヤモリ（Gekko japonicus）は、爬虫綱有鱗目ヤモリ科のトカゲ")
    assert discovery._EXCLUDE.search("a gecko / lizard")
    # 연구·사체·해부·양식 클립은 별도 배제
    assert discovery._BADCLIP.search("Pig Carcasses decomposition on the seafloor")
    assert discovery._BADCLIP.search("解剖 標本 の魚")


def test_marine_filter_keeps_real_sea_creatures():
    """실제 해양생물은 _EXCLUDE에 안 걸린다(아메프라시=바다토끼 오배제 회귀 방지)."""
    assert not discovery._EXCLUDE.search("Aplysia kurodai is a species of sea hare (gastropod)")
    assert not discovery._EXCLUDE.search("ウミグモ綱は鋏角類に属する節足動物")
    assert not discovery._EXCLUDE.search("ニセクロナマコはナマコの一種")


def test_land_spider_excluded_but_sea_spider_kept():
    """육상 거미(검은과부거미)는 배제, 바다거미(Pycnogonida)는 유지 — 실제 오소싱 회귀 방지."""
    land = "Latrodectus tredecimguttatus, the Mediterranean black widow, is one of the widow spiders."
    sea = "Sea spiders are marine arthropods of the class Pycnogonida, also called pycnogonids."
    assert discovery._EXCLUDE.search(land)          # 육상 거미 배제
    assert not discovery._EXCLUDE.search(sea)        # 바다거미는 남긴다


def test_category_catalog_has_distinct_terms():
    """카테고리마다 고유 검색어를 갖는다(과거엔 전부 심해 검색어를 공유 → 엉뚱한 종·중복)."""
    cat = discovery._CATALOG
    assert "marine_algae" in cat and "marine_life" in cat and "deep_sea" in cat
    algae, deep = set(cat["marine_algae"]["terms"]), set(cat["deep_sea"]["terms"])
    assert algae != deep and not (algae & deep)      # 미세조류 검색어는 심해와 완전 분리
    assert any("diatom" in t or "algae" in t or "plankton" in t for t in cat["marine_algae"]["terms"])


def test_algae_gate_positive_and_animal_exclude():
    """미세조류: 조류 양성 확인 + 동물 배제(거미·물고기가 미세조류로 새지 않게)."""
    assert discovery._ALGAE.search("a diatom is a single-celled microalgae (phytoplankton)")
    assert not discovery._ALGAE.search("a widow spider, a venomous arachnid")   # 거미는 조류 아님
    assert discovery._ANIMAL.search("this reef fish and octopus")               # 동물 배제 단서
    # marine_algae 설정은 동물 배제 + 조류 양성 요구
    assert discovery._CATALOG["marine_algae"]["require"] is discovery._ALGAE
    assert discovery._CATALOG["marine_algae"]["exclude"] is discovery._ANIMAL


def test_wreck_name_extraction_loose():
    """침몰선 이름 추출: 강한 접두사 없이도 실제 제목에서 이름을 뽑는다(0건 회귀 방지)."""
    f = discovery._wreck_name_from_title
    assert f("File:Best Wreck dive in Portugal - Madeirense Porto Santo.webm") == "Madeirense"
    assert f("File:Wreck Diving - Black sea Jacques Fraissinet 1-4.webm") == "Jacques Fraissinet"
    assert f("File:Wreck of the SS Thistlegorm.webm").startswith("SS")
    assert f("File:random underwater footage.webm") == ""   # 이름 단서 없으면 빈 문자열


def test_wreck_name_rejects_title_junk():
    """제목 상투어(정크)를 배 이름으로 오인하지 않는다(운영자 검토 부담·오제작 방지)."""
    f = discovery._wreck_name_from_title
    assert f("File:U S Navy EOD Removes Ordnance from WWII Shipwreck.webm") == ""
    assert f("File:First Look at World War II Shipwrecks Off NC Coast.webm") == ""
    assert not discovery._plausible_wreck_name("shipwreck")
    assert not discovery._plausible_wreck_name("u s")
    assert discovery._plausible_wreck_name("Madeirense")


def test_photo_wreck_promote_carries_media_kind(tmp_path, monkeypatch):
    """사진 후보 승격 시 media_kind=photo·image_url이 discovered.json에 실려야
    fetch_footage가 켄번즈로 영상화할 수 있다(무한 엔진 연결부)."""
    monkeypatch.setattr(discovery, "_DISCOVERED_DIR", tmp_path)
    (tmp_path / "shipwreck").mkdir()
    cand = {"kind": "wreck", "key": "wreck carnatic", "needs_confirm": True, "media_kind": "photo",
            "title": "File:Carnatic.jpg", "url": "https://x/Carnatic.jpg", "image_url": "https://x/Carnatic.jpg",
            "license": "cc-by-sa", "credit": "X · CC BY-SA", "source": "File:Carnatic.jpg",
            "name": "Carnatic", "name_ja": "", "ship_type": "", "depth": "", "facts": [], "fact_src": ""}
    discovery.save_candidates("shipwreck", [cand])
    assert discovery.promote_candidate("shipwreck", "wreck carnatic")
    disc = discovery.load_discovered("shipwreck")
    fp = disc[0]["footage"]
    assert fp["media_kind"] == "photo" and fp["image_url"].endswith("Carnatic.jpg")


def test_kenburns_clip_produces_motion_video(tmp_path):
    """★사진→켄번즈: 정지 이미지가 모션 있는 16:9 영상이 되어 정지-게이트를 통과한다(무한 엔진 핵심)."""
    import os
    from PIL import Image
    from src.core import footage
    img = tmp_path / "test.jpg"
    # 합성 테스트 이미지(랜덤 노이즈 — 텍스처가 풍부해 실제 사진처럼 확대 시 프레임 간 변화 발생).
    Image.frombytes("RGB", (2000, 1500), os.urandom(2000 * 1500 * 3)).save(str(img), quality=92)
    out = tmp_path / "kb.mp4"
    assert footage._kenburns_clip(str(img), str(out), seconds=14)   # 제작 기본 길이
    dim = footage._probe_dim(str(out))
    assert dim and 1.55 <= dim[0] / dim[1] <= 1.95     # 16:9
    from src.core import watermark_qc as wq
    assert not wq.is_static_source(str(out))            # 정지 아님 → 게이트 통과


def _noise_jpg(path, w=2000, h=1500):
    import os
    from PIL import Image
    Image.frombytes("RGB", (w, h), os.urandom(w * h * 3)).save(str(path), quality=92)


def test_kenburns_motions_and_vertical(tmp_path):
    """켄번즈 4방향(in/out/pan_l/pan_r) + 9:16 세로 출력 모두 non-static·정확 규격."""
    from src.core import footage, watermark_qc as wq
    img = tmp_path / "p.jpg"; _noise_jpg(img)
    for m in footage._KENBURNS_MOTIONS:
        out = tmp_path / f"{m}.mp4"
        assert footage._kenburns_clip(str(img), str(out), seconds=14, motion=m)  # 16:9
        assert not wq.is_static_source(str(out))
    v = tmp_path / "v.mp4"                               # 9:16(본문 컷어웨이용)
    assert footage._kenburns_clip(str(img), str(v), seconds=14, motion="in", W=720, H=1280)
    assert footage._probe_dim(str(v)) == (720, 1280)
    # 대상 키별로 무브가 갈린다(반복 피로 완화)
    picks = {footage._kenburns_motion_for(k) for k in ("a", "b", "c", "d", "wreck aries", "diatom")}
    assert len(picks) >= 2


def test_insert_cutaways_preserves_timeline(tmp_path):
    """★본문 컷어웨이: 사진 오버레이 후에도 길이·9:16이 보존된다(자막·오디오 연속성 근거)."""
    import subprocess
    from src.core import footage
    body = tmp_path / "body.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=s=720x1280:d=24:r=30", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(body)], check=True)
    photos = []
    for i in range(2):
        p = tmp_path / f"cut{i}.jpg"; _noise_jpg(p)
        photos.append({"path": str(p), "credit": f"Author{i} · CC BY"})
    before = footage._probe_dur(str(body))
    out = tmp_path / "body_cut.mp4"
    res = footage.insert_photo_cutaways(str(body), photos, str(out), before, key="Test species")
    assert res == str(out)                               # 삽입됨(원본과 다른 경로)
    assert abs(footage._probe_dur(res) - before) < 0.5   # 길이 보존
    assert footage._probe_dim(res) == (720, 1280)        # 9:16 유지


def test_subject_visibility_rejects_empty_water(tmp_path):
    """★피사체 가시성(Step1): 빈 물/균일 화면은 낮게, 구조가 있는 화면은 높게 → 빈 물 배제 근거."""
    import subprocess
    from src.core import footage
    empty = tmp_path / "empty.mp4"      # 균일한 어두운 물(약한 노이즈만) = '아무것도 안 보임'
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=0x0a1a2a:s=1280x720:d=4:r=30", "-vf", "noise=alls=4:allf=t",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(empty)], check=True)
    content = tmp_path / "content.mp4"  # 큰 구조가 있는 화면(피사체 있음 상당)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=s=1280x720:d=4:r=30", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(content)], check=True)
    ve = footage.subject_visibility(str(empty))
    vc = footage.subject_visibility(str(content))
    assert ve < footage._MIN_VISIBILITY <= vc, f"빈물={ve:.1f} 콘텐츠={vc:.1f} 임계={footage._MIN_VISIBILITY}"


def test_vision_subject_score_parsing_and_nokey(monkeypatch):
    """비전 주제 점수: 키 없으면 None(게이트 스킵), 있으면 JSON 배열 파싱."""
    from src.core import llm
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert llm.score_frames_subject(["/x.jpg"], "shrimp") is None      # 키 없음 → None
    monkeypatch.setattr(llm, "_vision_claude", lambda *a, **k: "判定: [1.0, 0.0, 0.5, 0.0]")
    assert llm.score_frames_subject(["a", "b", "c", "d"], "shrimp") == [1.0, 0.0, 0.5, 0.0]


def test_footage_shows_subject_verdict(tmp_path, monkeypatch):
    """★Step2 의미검증 판정: 주제 뚜렷 프레임이 충분하면 True, 거의 없으면 False, 검증불가면 None."""
    import subprocess
    from src.core import footage, llm
    v = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=s=640x360:d=3:r=10", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(v)], check=True)
    monkeypatch.setattr(llm, "score_frames_subject", lambda f, s, **k: [1.0, 1.0, 0, 0, 0, 0])
    assert footage.footage_shows_subject(str(v), "crab") is True       # 2/6 강함 → 충분
    monkeypatch.setattr(llm, "score_frames_subject", lambda f, s, **k: [0, 0.5, 0, 0, 0, 0])
    assert footage.footage_shows_subject(str(v), "crab") is False      # 강한 프레임 없음 → 폐기
    monkeypatch.setattr(llm, "score_frames_subject", lambda f, s, **k: None)
    assert footage.footage_shows_subject(str(v), "crab") is None       # 검증불가 → 게이트 스킵


def test_insert_cutaways_skips_when_short_body(tmp_path):
    """짧은 본문(<12s)·사진 없음이면 컷어웨이를 넣지 않는다(남발·촙핑 방지 · 발행 불정지)."""
    from src.core import footage
    body = tmp_path / "b.mp4"; body.write_bytes(b"x")
    assert footage.insert_photo_cutaways(str(body), [], str(tmp_path / "o.mp4"), 30, key="k") == str(body)
    p = tmp_path / "c.jpg"; _noise_jpg(p)
    assert footage.insert_photo_cutaways(str(body), [{"path": str(p), "credit": "A"}],
                                         str(tmp_path / "o2.mp4"), 8, key="k") == str(body)


def test_discovered_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "_DISCOVERED_DIR", tmp_path)
    (tmp_path / "deep_sea").mkdir()
    items = [{"key": "rimicaris exoculata",
              "footage": {"url": "https://x/y.webm", "license": "cc-by",
                          "credit": "Ifremer · CC BY", "source": "File:y.webm"},
              "species": {"scientific_name": "Rimicaris exoculata",
                          "common_name_ko": "열수분출공새우", "common_name_en": "vent shrimp",
                          "depth_range_m": "", "distribution": "", "habitat": "",
                          "diet": [], "fun_facts": ["blind vent shrimp"], "sources": ["Wikipedia (en)"]}}]
    discovery.save_discovered("deep_sea", items)
    got = discovery.load_discovered("deep_sea")
    assert got and got[0]["key"] == "rimicaris exoculata"
    assert discovery.load_discovered("marine_life") == []   # 없으면 빈 리스트
