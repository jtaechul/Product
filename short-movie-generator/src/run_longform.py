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

try:  # 경량 텍스트 재생성 경로(deps 미설치 CI: regen-longform-meta.yml)에서도 임포트 가능하게
    from dotenv import load_dotenv
except ImportError:  # python-dotenv 미설치 시 no-op (CLI 제작 경로에서만 .env 로드가 필요)
    def load_dotenv(*_a, **_k):  # type: ignore[misc]
        return False

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
            ko_name=info.common_name_ko or "",
        ))
        specs[-1]._source = fv.get("source", "")   # 메타용(캡션 출처)
        specs[-1]._credit = fv.get("credit", "NOAA Ocean Exploration")
        rank += 1
    return specs


def _infer_theme_for(category, species_queries: list[str]) -> str:
    """테마 미지정('' · '자동') 시 선택된 종들의 사실만 보고 테마를 자동으로 고른다."""
    from src.categories.deep_sea import longform_script as LS

    facts = []
    for q in species_queries:
        q = q.strip()
        if not q:
            continue
        try:
            subject = category.parse_input(q)
            info = category.get_info(subject)
            facts.append((info.common_name_ko or q, info.fun_facts or []))
        except Exception as e:  # noqa: BLE001
            log.warning("[longform] 테마 추론용 종 정보 실패(무시): %r (%s)", q, e)
    theme = LS.infer_theme(facts) if facts else LS.DEFAULT_THEME
    log.info("[longform] 자동 테마 추론 → %s", theme)
    return theme


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


def _fmt_ts(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def _ko_chapters(chapters_jp: str, chapter_items: list | None) -> str:
    """구조화 chapter_items(t·label_jp·rank·ko_name)로 한국어 챕터 문자열 재구성.

    없으면(구버전 compile 결과 등) 일본어 챕터 문자열을 그대로 반환(항상 문자열 보장).
    """
    if not chapter_items:
        return chapters_jp
    fixed = {"オープニング": "오프닝", "エンディング": "엔딩"}
    lines = []
    for it in chapter_items:
        rank = it.get("rank")
        if rank:
            lines.append(f"{_fmt_ts(it['t'])} {rank}위 {it.get('ko_name') or it.get('label_jp', '')}")
        else:
            lab_jp = it.get("label_jp", "")
            lines.append(f"{_fmt_ts(it['t'])} {fixed.get(lab_jp, lab_jp)}")
    return "\n".join(lines)


def _tagify(name: str) -> str:
    """생물명을 해시태그 토큰으로: 공백·괄호·구두점 제거, '#' 접두. (일/한 공통)"""
    import re as _re
    s = _re.sub(r"[\s()（）・,、。/／\-—’'\"]+", "", str(name or "")).strip()
    return ("#" + s) if s else ""


def _seo_hashtags(theme_key: str, segs: list) -> tuple[list[str], list[str]]:
    """롱폼(랭킹형)용 SEO 최적화 해시태그를 일본어/한국어로 도출.

    구성 = ①필수 공통(#深海·#海洋生物 / #심해·#해양생물) ②포맷·랭킹 태그
    ③테마 태그 ④등장 종명(1위부터) ⑤심해·자연 일반 검색어. 중복 제거 후
    유튜브 권장 상한(15개 안팎)으로 컷. 사실 왜곡 태그(괴물·UMA 등)는 넣지 않는다.
    """
    n = len(segs)
    ordered = sorted(segs, key=lambda s: s.rank)
    # ② 포맷/랭킹
    fmt_jp = ["#深海", "#海洋生物", "#深海生物", "#ランキング", f"#TOP{n}", "#雑学", "#生き物"]
    fmt_ko = ["#심해", "#해양생물", "#심해생물", "#랭킹", f"#TOP{n}", "#잡학", "#생물"]
    # ③ 테마
    theme_map_jp = {"기이한": "#奇妙な生き物", "위험한": "#危険生物", "놀라운": "#驚きの生物",
                    "미스터리한": "#ミステリー", "무서운": "#閲覧注意"}
    theme_map_ko = {"기이한": "#기이한생물", "위험한": "#위험생물", "놀라운": "#놀라운생물",
                    "미스터리한": "#미스터리", "무서운": "#소름"}
    if theme_map_jp.get(theme_key):
        fmt_jp.append(theme_map_jp[theme_key]); fmt_ko.append(theme_map_ko[theme_key])
    # ④ 등장 종명(1위부터)
    sp_jp = [_tagify(s.jp_name) for s in ordered]
    sp_ko = [_tagify(s.ko_name or s.jp_name) for s in ordered]
    # ⑤ 일반 검색어
    gen_jp = ["#海の生き物", "#深海魚", "#自然", "#海", "#神秘", "#不思議な生き物"]
    gen_ko = ["#바다생물", "#심해어", "#자연", "#바다", "#신비", "#신기한생물"]

    def _dedup(seq: list[str], limit: int = 15) -> list[str]:
        out: list[str] = []
        for t in seq:
            if t and t not in out:
                out.append(t)
        return out[:limit]

    return _dedup(fmt_jp + sp_jp + gen_jp), _dedup(fmt_ko + sp_ko + gen_ko)


def _compose_meta_text(theme_key: str, segs: list, chapters: str, chapters_ko: str) -> dict:
    """제목·설명·해시태그(일/한) 텍스트만 조립. 챕터(일/한)는 이미 만들어진 값을 그대로 받는다.

    최초 제작(`_build_meta`)과 사후 텍스트 재생성(`rebuild_meta_from_record`)이 같은 규칙을
    공유하도록 분리한 순수 함수(렌더·소싱 불필요 → 재생성이 빠르고 결정적).
    """
    from src.categories.deep_sea import longform_script as LS
    adj, _title_word, _tone = LS.theme_words(theme_key)
    n = len(segs)
    top = min(segs, key=lambda s: s.rank)
    ordered = sorted(segs, key=lambda s: s.rank)
    names = " / ".join(s.jp_name for s in ordered)
    names_ko = " / ".join((s.ko_name or s.jp_name) for s in ordered)
    yt_title = (f"深海の{adj}生き物 TOP{n}｜{top.jp_name}ほか")[:30]
    yt_title_ko = (f"심해의 {theme_key} 생물 TOP{n} | {top.ko_name or top.jp_name} 외")[:34]
    tags_jp, tags_ko = _seo_hashtags(theme_key, segs)
    desc = (
        f"光の届かない深海に潜む、{adj}生き物たちのランキング TOP{n}。\n"
        f"第{n}位から、第1位まで。あなたが一番ゾッとするのはどれでしょうか。\n\n"
        f"― 目次 ―\n{chapters}\n\n"
        f"登場: {names}\n\n"
        f"映像: NOAA Ocean Exploration ほか・Public Domain / CC0\n"
        f"チャンネル登録で、次の深海へ。\n"
        f"{' '.join(tags_jp)}"
    )
    desc_ko = (
        f"빛이 닿지 않는 심해에 사는, {theme_key} 생물들의 랭킹 TOP{n}.\n"
        f"{n}위부터 1위까지. 당신이 가장 소름 돋는 건 어느 쪽일까요?\n\n"
        f"― 목차 ―\n{chapters_ko}\n\n"
        f"등장: {names_ko}\n\n"
        f"영상: NOAA Ocean Exploration 외 · Public Domain / CC0\n"
        f"구독하면, 다음 심해로.\n"
        f"{' '.join(tags_ko)}"
    )
    return {"yt_title": yt_title, "yt_title_ko": yt_title_ko,
            "yt_description": desc, "yt_description_ko": desc_ko,
            "hashtags": tags_jp, "hashtags_ko": tags_ko}


class _RecSeg:
    """레코드(content/<id>.json)에서 복원한 세그먼트 어댑터(재생성용)."""
    def __init__(self, rank, jp_name, ko_name, sci_name):
        self.rank, self.jp_name, self.ko_name, self.sci_name = rank, jp_name, ko_name, sci_name


def _segs_from_record(rec: dict) -> list:
    """레코드의 sources(+chapters_ko)로 세그먼트를 복원. ko_name은 sources에 있으면 그걸,
    없으면 chapters_ko의 'N위 국문명' 줄에서 순위로 매칭해 채운다(구 레코드 호환)."""
    import re as _re
    ko_by_rank: dict[int, str] = {}
    for ln in (rec.get("chapters_ko") or "").splitlines():
        m = _re.search(r"(\d+)\s*위\s+(.+)", ln.strip())
        if m:
            ko_by_rank[int(m.group(1))] = m.group(2).strip()
    segs = []
    for s in rec.get("sources", []):
        rank = int(s.get("rank", 0) or 0)
        ko = s.get("ko_name") or ko_by_rank.get(rank) or s.get("jp_name", "")
        segs.append(_RecSeg(rank, s.get("jp_name", ""), ko, s.get("sci_name", "")))
    return segs


def rebuild_meta_from_record(rec: dict) -> dict:
    """기존 롱폼 레코드에서 제목·설명·해시태그(일/한)를 다시 도출(영상 재렌더 없음).

    대시보드의 '제목/설명/해시태그 재생성' 버튼이 부르는 저비용 경로. 챕터·종·테마 등
    영상에 종속된 값은 레코드에 저장된 것을 그대로 재사용한다.
    """
    theme_key = rec.get("theme", "") or "기이한"
    segs = _segs_from_record(rec)
    if not segs:
        return {}
    return _compose_meta_text(theme_key, segs, rec.get("chapters", ""), rec.get("chapters_ko", ""))


def _build_meta(theme_key: str, segs: list, chapters: str, chapter_items: list | None = None) -> dict:
    from src.categories.deep_sea import longform_script as LS
    _adj, title_word, _tone = LS.theme_words(theme_key)
    n = len(segs)
    ordered = sorted(segs, key=lambda s: s.rank)
    chapters_ko = _ko_chapters(chapters, chapter_items)
    text = _compose_meta_text(theme_key, segs, chapters, chapters_ko)
    sources = [{"jp_name": s.jp_name, "sci_name": s.sci_name, "rank": s.rank,
                "ko_name": (s.ko_name or s.jp_name),
                "source": getattr(s, "_source", ""), "credit": getattr(s, "_credit", "")}
               for s in ordered]
    return {"theme": theme_key, "title_word": title_word,
            "chapters": chapters, "chapters_ko": chapters_ko,
            "n": n, "sources": sources, **text}


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
    if LS.is_auto_theme(theme_key):
        theme_key = _infer_theme_for(category, species)
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
    # ※최종 전체영상 재검증은 제거했다(속도). 각 세그먼트 본문이 이미 렌더 직후 검증되고
    # (segment.render_segment), 콜드오픈은 그 깨끗한 구간·박스를 재사용하므로 실사 구간은
    # 세그먼트 단계에서 이미 커버된다. 타이틀·지도·아웃트로는 자체 제작(소스 문구 없음).
    # → 완성본 전체를 420프레임씩 다시 OCR하던 중복(가장 큰 비용)을 없애 제작시간을 크게 단축.
    meta = _build_meta(theme_key, segs, r["chapters"], r.get("chapter_items"))
    meta.update({"video": str(final), "total_s": r["total_s"]})
    # ★유튜브 썸네일 자동 생성(체계 반영): 1위 종의 대표 프레임 + 테마 제목 + 종수(N選)로
    #   1280x720 썸네일을 생성해 out/thumbnail.png에 저장하고 meta에 등록한다. 워크플로가
    #   이를 Release에 올려 대시보드 커버·유튜브 업로드에 사용. 실패해도 본편 발행은 계속.
    try:
        from src.core.longform import thumbnail as TH
        top = sorted(segs, key=lambda s: s.rank)[0]
        hero = TH.pick_hero_frame(top.footage_path, str(out / "hero.jpg"))
        TH.render_thumbnail(str(out / "thumbnail.png"), str(out / "work" / "thumb"),
                            title_lines=["深海の", f"{title_word}生物"], tag="実在します",
                            count=len(segs), creature_img=hero)
        meta["thumbnail"] = "thumbnail.png"
        log.info("[longform] 썸네일 생성 완료: %s", out / "thumbnail.png")
    except Exception as e:  # noqa: BLE001
        log.warning("[longform] 썸네일 생성 실패(무시하고 발행 계속): %s", e)
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("[longform] 완료: %s (%.1fs, %d종)", final, r["total_s"], len(segs))
    return meta


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(description="롱폼 랭킹형(TOP N) 제작")
    ap.add_argument("--theme", default="", help="테마: 기이한/위험한/놀라운/미스터리한/무서운 "
                    "(비우거나 '자동' → 선택된 종의 사실을 보고 자동 추론)")
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
