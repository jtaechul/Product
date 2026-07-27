"""CLI 진입점.

사용:
  .venv/bin/python -m src.run_pipeline "dumbo octopus"
  .venv/bin/python -m src.run_pipeline "dumbo octopus" --visualizer veo_img2video
"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from src.core.contracts import PipelineError
from src.core.pipeline import run


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="쇼츠/릴스 자동 생성 파이프라인")
    parser.add_argument("query", help="대상 질의 (예: 'dumbo octopus')")
    parser.add_argument("--category", default="deep_sea", help="카테고리 ID (기본: deep_sea)")
    parser.add_argument(
        "--visualizer", default="panzoom",
        choices=["panzoom", "veo_img2video", "veo_text2video"],
        help="시각화 구현체 (기본: panzoom, Veo 계열은 GEMINI_API_KEY 필요)",
    )
    parser.add_argument("--episode", type=int, default=None,
                        help="시리즈 회차 번호 (생략 시 도감 원장 기준 자동)")
    parser.add_argument("--scope", default="all",
                        choices=["all", "caption", "images", "video"],
                        help="재생성 범위(기본 all). 관리자 부분 재생성 시 레코드 병합 갱신 표시")
    parser.add_argument("--mode", default="reels", choices=["reels", "narrated", "hud"],
                        help="제작 모드(기본 reels: 실사영상+일본어 오프닝훅/엔드카드 / narrated: 구 나레이션 / hud: 구 ROV)")
    # ★운영자 수동 지정(관리자 페이지 '고급 설정' → 워크플로 → 여기). 비우면 전부 자동.
    parser.add_argument("--src-start", default="", help="소스에서 쓸 구간 시작(초). 비우면 자동")
    parser.add_argument("--src-end", default="", help="소스에서 쓸 구간 끝(초). 비우면 자동")
    parser.add_argument("--crop-x", default="",
                        help="9:16 크롭 가로 중심 0.0~1.0 (0=왼쪽·0.5=가운데·1=오른쪽). 비우면 피사체 자동추적")
    parser.add_argument("--cuts", default="", help="컷 전환 수(3~8). 비우면 기본 4")
    parser.add_argument("--zoom", default="",
                        help="줌 배율 1.0~2.5 (1.0=원본 넓게·1.5~2.0=피사체 당김). 비우면 자동")
    # ★화면 구성(운영자 확정): cover=9:16 꽉 채움(기본) / square=정방형 / full=원본 좌우 전체
    parser.add_argument("--fit", default="",
                        help="화면 구성 cover(꽉 채움·기본) / square(정방형) / full(원본 좌우 전체)")
    parser.add_argument("--cut-specs", default="",
                        help='컷별 구간 직접 지정(운영자 확정 방식). 자동 컷 선택을 대체한다. '
                             '형식 ① 간단표기 "0-6, 20-27, 41-48, 62-70" '
                             '② JSON [{"start":0,"end":6,"crop_x":0.5,"mode":"closeup"}, ...]')
    # ★운영자가 '영상 찾기'에서 고른 영상으로 바로 제작(운영자 확정).
    #   요구사항: 이 경로로 만들 때는 **종명·학명을 추가로 검색·확보**해야 한다(대본·엔드카드·도감 성립).
    parser.add_argument("--video-url", default="", help="이 영상으로 제작(관리자 '영상 찾기' 결과 URL)")
    parser.add_argument("--video-title", default="", help="영상 제목(종 식별 단서)")
    parser.add_argument("--video-license", default="", help="영상 라이선스(게이트 통과값)")
    parser.add_argument("--video-credit", default="", help="영상 크레딧(저작자 표기)")
    args = parser.parse_args()

    manual = {k: v for k, v in (("start", args.src_start), ("end", args.src_end),
                                ("crop_x", args.crop_x), ("cuts", args.cuts),
                                ("zoom", args.zoom), ("cut_specs", args.cut_specs),
                                ("fit", args.fit))
              if str(v).strip()} or None
    if manual:
        logging.info("운영자 수동 지정: %s", manual)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # ★'찾은 영상으로 제작' 경로: 영상만으로는 대본·엔드카드·도감이 성립하지 않으므로
    #   **종명·학명을 먼저 확보**하고(위키미디어 구조화데이터 → Wikidata), 그 종을 제작 대상으로 삼는다.
    #   확보 실패 시 학명을 지어내지 않고 즉시 중단한다(날조 금지 하드룰).
    query = args.query
    if str(args.video_url).strip():
        from src.core import discovery, footage
        rec = discovery.resolve_from_video(args.video_url.strip(), args.video_title, "")
        wreck = None
        if not rec:
            # ★침몰선 경로(운영자 확정 "직접 소싱한 영상이 침몰선이면 침몰선 형태로 제작해도 된다"):
            #   종이 안 잡히면 배 이름·그 배 자료를 찾아본다. 화면은 이 영상, 대본은 그 배 자료.
            wreck = discovery.resolve_wreck_from_video(args.video_url.strip(), args.video_title, "")
        if not rec and not wreck:
            logging.error("파이프라인 중단: 이 영상의 종명·학명(또는 배 이름·자료)을 확보하지 "
                          "못했습니다. 제목에 학명(예: Bathynomus giganteus)이나 배 이름을 "
                          "넣어 다시 시도하세요. (일반 나레이션형으로는 제작 가능합니다)")
            return 1
        if wreck:
            args.category = "shipwreck"
        sp = rec["species"] if rec else wreck["subject"]
        rec = rec or wreck
        # ★라이선스: 대시보드는 사람이 읽는 라벨("Public Domain / CC0", "CC BY-SA" 등)을 넘긴다.
        #   게이트가 쓰는 식별자로 정규화한다(NC는 _norm_license가 먼저 차단 — 하드룰 #1).
        #   정규화 실패(=허용 라이선스 아님)면 게이트가 뒤에서 막지만, 여기서 먼저 명확히 끊는다.
        lic_raw = (args.video_license or "").strip()
        lic = footage._norm_license(lic_raw) if lic_raw else None
        if lic_raw and not lic:
            logging.error("파이프라인 중단: 사용할 수 없는 라이선스입니다 — %r "
                          "(허용: 퍼블릭도메인·CC0·CC BY·CC BY-SA·KOGL1 / 비상업(NC)·ND 불가)", lic_raw)
            return 1
        rec["footage"]["license"] = lic or rec["footage"]["license"]
        rec["footage"]["credit"] = (args.video_credit or "").strip() or rec["footage"]["credit"]
        # ①영상 URL을 종 키로 캐시 → footage.fetch_footage가 그대로 이 영상을 쓴다(다운로드·게이트 재사용)
        footage._video_cache_put(rec["key"], rec["footage"])
        # ②종 정보를 발굴 목록에 **병합** 등록 → 카테고리 SUBJECTS에 편입되어 parse_input/get_info가 인식
        #   ⚠ save_discovered는 통째 덮어쓰기라 기존 목록을 반드시 합쳐서 넘긴다(기존 종 유실 방지).
        cur = discovery.load_discovered(args.category)
        cur = [x for x in cur if (x.get("key") or "").strip().lower() != rec["key"]]
        discovery.save_discovered(args.category, cur + [rec])
        query = sp["scientific_name"]
        logging.info("영상→대상 확보: %s (%s / %s) · 이 영상으로 제작합니다",
                     sp["scientific_name"], sp["common_name_ko"], sp["common_name_en"])
        if wreck:
            # 침몰선은 카테고리가 이미 확정(shipwreck) — 생물용 재분류 로직을 태우지 않는다.
            logging.info("침몰선 형태로 제작합니다(화면=이 영상 · 대본·캡션=그 배 자료)")
            return _run(args, query, manual)
        # ★카테고리 자동 라우팅(운영자 확정 "영상이 있으면 제작은 된다"): 고른 종이 그 카테고리에
        #   맞지 않으면(예: 얕은 바다 종을 심해 도감에) **거절하지 말고 맞는 카테고리로 옮겨** 만든다.
        #   심해가 아닌 종을 '심해'로 발행하면 가짜 수심이 되므로 거절도 정답이 아니다 → 재분류가 정답.
        try:
            from src.core.contracts import PipelineError as _PE
            from src.registry import get_category as _gc
            _cat = _gc(args.category)
            _vs = getattr(_cat, "verify_subject", None)
            if callable(_vs):
                from src.core.contracts import SpeciesInfo as _SI
                _info = _SI(scientific_name=sp["scientific_name"],
                            common_name_ko=sp["common_name_ko"], common_name_en=sp["common_name_en"],
                            depth_range_m=sp["depth_range_m"], distribution=sp["distribution"],
                            habitat=sp["habitat"], diet=list(sp["diet"]),
                            fun_facts=list(sp["fun_facts"]), sources=list(sp["sources"]))
                try:
                    _vs(_info)
                except _PE as e:
                    fallback = "marine_life"
                    if args.category != fallback:
                        logging.warning("카테고리 부적합(%s) → '%s'로 자동 재분류해 제작합니다: %s",
                                        args.category, fallback, e)
                        args.category = fallback
                        cur2 = discovery.load_discovered(fallback)
                        cur2 = [x for x in cur2
                                if (x.get("key") or "").strip().lower() != rec["key"]]
                        discovery.save_discovered(fallback, cur2 + [rec])
        except Exception as e:  # noqa: BLE001
            logging.info("카테고리 적합성 사전확인 생략(%s) — 파이프라인 게이트가 판단합니다", e)

    return _run(args, query, manual)


def _run(args, query: str, manual: dict | None) -> int:
    """확정된 카테고리·질의로 파이프라인 실행 + 결과 출력(종료코드 반환)."""
    try:
        if args.mode == "reels":
            from src.core.pipeline import run_reels
            result = run_reels(args.category, query, episode=args.episode, manual=manual)
        elif args.mode == "narrated":
            from src.core.pipeline import run_narrated
            result = run_narrated(args.category, args.query, args.visualizer, episode=args.episode)
        else:
            result = run(args.category, args.query, args.visualizer,
                         episode=args.episode, scope=args.scope)
    except PipelineError as e:
        logging.error("파이프라인 중단: %s", e)
        return 1

    print(f"\n=== 완료 ===")
    print(f"영상: {result.video_path}")
    print(f"메타: {result.sidecar_meta}")
    print(f"QC: {'전 항목 통과' if result.qc_passed else '실패 항목 있음'}")
    for check, r in result.qc_report.items():
        print(f"  [{'O' if r['passed'] else 'X'}] {check}: {r['detail']}")
    return 0 if result.qc_passed else 2


if __name__ == "__main__":
    sys.exit(main())
