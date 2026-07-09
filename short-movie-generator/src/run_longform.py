"""롱폼(랭킹형 TOP N) 제작 CLI 진입점.

테마(기이한/위험한/놀라운/미스터리한/무서운) + 종 4~6개 → 종별 세그먼트 조립 →
콜드오픈·타이틀·글로벌맵·세그먼트×N(5→1)·아웃트로 합성 → 8분 안팎 16:9 롱폼 + 챕터/설명.

사용:
  .venv/bin/python -m src.run_longform --theme 기이한 \
      --species "덤보문어,머리없는닭괴물,다이오우구소쿠무시,메가로디코피아,움벨룰라" \
      --out output/longform

출력: {out}/longform.mp4 + {out}/meta.json (제목·설명·챕터·종·출처).
- 종별 상세 나레이션은 LLM(Claude→Gemini) 생성, 실패 시 시드 확장 폴백.
- 실사 영상 미확보 종은 건너뛴다(날조 금지). 최소 3종 확보 실패 시 중단.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.core.contracts import ALLOWED_LICENSES, PipelineError

log = logging.getLogger("run_longform")


def _entry_base() -> int:
    try:
        from src.categories.deep_sea import catalog
        return int(catalog.peek_next())
    except Exception:  # noqa: BLE001
        return 1


def build_segments(category, species_queries: list[str], theme_key: str, raw_root: Path) -> list:
    """입력 순서 = 순위(1위 먼저). 실사 영상 확보된 종만 세그먼트화."""
    from src.core import footage
    from src.core.longform import segment as SEG
    from src.categories.deep_sea import longform_script as LS

    base = _entry_base()
    specs, rank = [], 1
    for idx, q in enumerate(species_queries):
        q = q.strip()
        if not q:
            continue
        try:
            subject = category.parse_input(q)
            info = category.get_info(subject)
        except Exception as e:  # noqa: BLE001
            log.warning("[longform] 종 정보 실패 → 건너뜀: %r (%s)", q, e)
            continue
        seg_raw = raw_root / f"seg{rank}"
        seg_raw.mkdir(parents=True, exist_ok=True)
        fv = footage.fetch_footage(info.scientific_name, info.common_name_en, str(seg_raw))
        if not fv:
            log.warning("[longform] 실사 영상 미확보 → 건너뜀: %s", info.scientific_name)
            continue
        if (fv["license"] or "").strip().lower() not in ALLOWED_LICENSES:
            log.warning("[longform] 라이선스 차단 → 건너뜀: %s (%s)", info.scientific_name, fv["license"])
            continue
        sc = LS.build_segment_script(info, theme_key)
        nx, ny, region_jp = LS.region_for(info)
        dmin, dmax = category._parse_depth(info.depth_range_m)
        sci = (info.scientific_name or "").strip()
        sci = sci[0].upper() + sci[1:] if sci else sci
        jp = _jp_name(category, info)
        specs.append(SEG.SegmentSpec(
            rank=rank, jp_name=jp, sci_name=sci, depth_min=dmin, depth_max=dmax,
            size_label=_size_label(info), region_nx=nx, region_ny=ny, region_label_jp=region_jp,
            narration=sc["narration"], stamp_line=sc["stamp_line"], stamp_big=sc["stamp_big"],
            entry_no=base + idx, footage_path=fv["path"], footage_start=8.0,
            target_depth_m=min(6000, max(1000, dmax)), logo_box=fv.get("logo_box"),
        ))
        specs[-1]._source = fv.get("source", "")   # 메타용(캡션 출처)
        specs[-1]._credit = fv.get("credit", "NOAA Ocean Exploration")
        rank += 1
    return specs


def _jp_name(category, info) -> str:
    """일본어 통칭(훅 스펙 재사용, 없으면 학명 카타카나 대체 없이 국문/영문)."""
    try:
        t = category.hook_intro_spec(info)
        if t and t[0] and getattr(t[0], "jp_name", ""):
            return t[0].jp_name
    except Exception:  # noqa: BLE001
        pass
    return info.common_name_ko or info.common_name_en or info.scientific_name


def _size_label(info) -> str:
    for f in (info.fun_facts or []):
        import re
        m = re.search(r"(\d+(?:[~\-–]\d+)?)\s*(cm|센치|센티|m)\b", f)
        if m:
            unit = "cm" if m.group(2) != "m" else "m"
            return f"約 {m.group(1)} {unit}"
    return "—"


def _build_meta(theme_key: str, segs: list, chapters: str) -> dict:
    from src.categories.deep_sea import longform_script as LS
    adj, title_word, _tone = LS.theme_words(theme_key)
    n = len(segs)
    top = min(segs, key=lambda s: s.rank)
    names = " / ".join(s.jp_name for s in sorted(segs, key=lambda s: s.rank))
    yt_title = f"深海の{adj}生き物 TOP{n}｜{top.jp_name}ほか"
    yt_title = yt_title[:30]
    desc = (
        f"光の届かない深海に潜む、{adj}生き物たちのランキング TOP{n}。\n"
        f"第{n}位から、第1位まで。あなたが一番ゾッとするのはどれでしょうか。\n\n"
        f"― 目次 ―\n{chapters}\n\n"
        f"登場: {names}\n\n"
        f"映像: NOAA Ocean Exploration ほか・Public Domain / CC0\n"
        f"チャンネル登録で、次の深海へ。\n"
        f"#深海 #深海生物 #ランキング"
    )
    sources = [{"jp_name": s.jp_name, "sci_name": s.sci_name, "rank": s.rank,
                "source": getattr(s, "_source", ""), "credit": getattr(s, "_credit", "")}
               for s in sorted(segs, key=lambda s: s.rank)]
    return {"theme": theme_key, "title_word": title_word, "yt_title": yt_title,
            "yt_description": desc, "chapters": chapters, "n": n, "sources": sources}


def run_longform(theme_key: str, species: list[str], base_dir: str = ".",
                 out_dir: str | None = None) -> dict:
    from src.core.longform import compile as C
    from src.categories.deep_sea import longform_script as LS
    from src.core.pipeline import get_category

    base = Path(base_dir)
    raw_root = base / "assets" / "raw" / "longform"
    out = Path(out_dir) if out_dir else base / "output" / "longform"
    out.mkdir(parents=True, exist_ok=True)
    raw_root.mkdir(parents=True, exist_ok=True)

    category = get_category("deep_sea")
    segs = build_segments(category, species, theme_key, raw_root)
    if len(segs) < 3:
        raise PipelineError("longform", f"실사 영상 확보 종 부족(확보 {len(segs)}종, 최소 3종)")

    _adj, title_word, _tone = LS.theme_words(theme_key)
    # 콜드오픈 도발 훅(마케터 페르소나) + 오프닝 나레이션 — 랭킹 순(1위 먼저) 노출명 기준
    jp_names = [s.jp_name for s in sorted(segs, key=lambda s: s.rank)]
    opening = LS.opening_hook(theme_key, jp_names, len(segs))
    log.info("[longform] %d종 세그먼트 조립 시작 (테마=%s, 훅=%r)", len(segs), theme_key, opening["text"])
    r = C.compile_longform(title_word, segs, str(out / "work"), C.CompileConfig(), opening=opening)
    # 최종 산출물을 out 루트로 이동
    final = out / "longform.mp4"
    Path(r["video"]).replace(final)
    meta = _build_meta(theme_key, segs, r["chapters"])
    meta.update({"video": str(final), "total_s": r["total_s"]})
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("[longform] 완료: %s (%.1fs, %d종)", final, r["total_s"], len(segs))
    return meta


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(description="롱폼 랭킹형(TOP N) 제작")
    ap.add_argument("--theme", default="기이한", help="테마: 기이한/위험한/놀라운/미스터리한/무서운")
    ap.add_argument("--species", required=True, help="종 4~6개 콤마 구분(입력 순서=순위, 첫째=1위)")
    ap.add_argument("--base", default=".", help="작업 루트")
    ap.add_argument("--out", default=None, help="출력 디렉토리(기본 {base}/output/longform)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    species = [s for s in (args.species or "").split(",") if s.strip()]
    if not (3 <= len(species) <= 6):
        log.error("종 개수는 3~6개여야 합니다(입력 %d개).", len(species))
        return 2
    try:
        meta = run_longform(args.theme, species, args.base, args.out)
    except PipelineError as e:
        log.error("제작 실패: %s", e)
        return 1
    print(json.dumps({"video": meta["video"], "total_s": meta["total_s"],
                      "yt_title": meta["yt_title"], "n": meta["n"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
