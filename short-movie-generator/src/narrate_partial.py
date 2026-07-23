"""나레이트(/nv) 부분 재생성 CLI — 영상 재렌더 없이 ① 제목·설명(meta) ② 썸네일(thumb)만 다시 만든다.

운영자 요청: /nv 페이지에 '제목·설명 재생성'·'썸네일 재생성' 버튼. narrate-video.yml 의
scope=meta|thumb 잡이 이 CLI를 호출한다(전체 재생성 scope=all 은 기존 경로 그대로).

- meta : 레코드의 더빙 대본(transcript.jp) — 없으면 기존 설명·훅 — 을 근거로 `_gen_metadata`를
  다시 돌려 제목·설명·해시태그(일/한)·훅을 갱신한다. 설명 끝의 챕터(타임스탬프) 블록은 보존.
  LLM 키가 없으면 결정론 폴백 메타로라도 갱신(실패로 멈추지 않음).
- thumb: 원본 영상에서 히어로 프레임을 다시 골라(제미나이 우선 `_pick_hero_frame`) 현재 훅·제목으로
  ROV HUD 썸네일을 재렌더한다. 표준출력 마지막 줄 = 썸네일 경로(워크플로가 릴리스에 업로드).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _strip_chapters(desc: str, header: str) -> tuple[str, str]:
    """설명문에서 챕터 블록(header로 시작)을 분리 → (본문, 챕터블록 또는 '')."""
    desc = desc or ""
    idx = desc.find(header)
    if idx < 0:
        return desc.strip(), ""
    return desc[:idx].strip(), desc[idx:].strip()


def _load_record(base: Path, cid: str) -> dict:
    p = base / "content" / f"{cid}.json"
    if not p.exists():
        raise SystemExit(f"ERROR: 레코드 없음: {p}")
    rec = json.loads(p.read_text(encoding="utf-8"))
    if rec.get("kind") != "narrate":
        raise SystemExit(f"ERROR: narrate 레코드가 아님: {cid} (kind={rec.get('kind')})")
    return rec


def regen_meta(base_dir: str, cid: str) -> bool:
    """제목·설명·해시태그(일/한)·훅 재생성 → 레코드 갱신. 챕터 블록 보존."""
    from src.core import content_store
    from src.core import narrate_attached as N
    base = Path(base_dir)
    rec = _load_record(base, cid)
    # 근거(대본): 더빙 대본 jp > (폴백) 기존 설명 본문 + 훅
    lines = [str(s.get("jp", "")).strip() for s in (rec.get("transcript") or []) if str(s.get("jp", "")).strip()]
    if not lines:
        body, _ = _strip_chapters(rec.get("yt_description", ""), "▼ チャプター")
        lines = [x for x in (rec.get("hook", ""), body) if x and x.strip()]
    if not lines:
        raise SystemExit("ERROR: 재생성 근거(대본/설명)가 없습니다.")
    meta = N._gen_metadata(lines, rec.get("mode", "longform"))
    # 챕터(타임스탬프) 블록 보존 — 새 설명 끝에 다시 붙인다
    _, ch_jp = _strip_chapters(rec.get("yt_description", ""), "▼ チャプター")
    _, ch_ko = _strip_chapters(rec.get("yt_description_ko", ""), "▼ 챕터")
    if ch_jp:
        meta["desc_jp"] = (str(meta.get("desc_jp", "")).strip() + "\n\n" + ch_jp).strip()
    if ch_ko:
        meta["desc_ko"] = (str(meta.get("desc_ko", "")).strip() + "\n\n" + ch_ko).strip()
    return content_store.update_narrate_meta(base_dir, cid, meta)


def regen_thumb(base_dir: str, cid: str, video_url: str) -> str:
    """원본에서 히어로 프레임 재선택(제미나이 우선) → 현재 훅·제목으로 썸네일 재렌더 → 경로 반환."""
    from src.core import narrate_attached as N
    base = Path(base_dir)
    rec = _load_record(base, cid)
    if not video_url or video_url == "-":
        raise SystemExit("ERROR: 썸네일 재생성에는 원본 영상 URL이 필요합니다.")
    work = base / "work" / "partial"
    work.mkdir(parents=True, exist_ok=True)
    if Path(video_url).exists():                       # 로컬 경로(테스트) 지원
        src = str(video_url)
    else:
        from src.narrate_video import _download
        dst = work / "input.mp4"
        if not _download(video_url, dst):
            raise SystemExit("ERROR: 원본 영상 다운로드 실패")
        src = str(dst)
    mode = rec.get("mode", "longform")
    w, h = (N.LONG_W, N.LONG_H) if mode == "longform" else (N.SHORTS_W, N.SHORTS_H)
    hero = N._pick_hero_frame(src, work / "hero", w, subject_hint=rec.get("yt_title", ""))
    if not hero:
        raise SystemExit("ERROR: 히어로 프레임 선택 실패")
    hook = (rec.get("hook") or rec.get("yt_title") or "").strip()
    out_dir = base / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    card = str(out_dir / "partial_card.png")
    thumb = str(out_dir / "partial_thumb.jpg")
    if not N._render_hook_and_thumb(hero, hook, rec.get("yt_title", ""), w, h, card, thumb):
        raise SystemExit("ERROR: 썸네일 렌더 실패")
    return thumb


def main() -> int:
    ap = argparse.ArgumentParser(description="나레이트 부분 재생성(제목·설명/썸네일)")
    ap.add_argument("--cid", required=True, help="콘텐츠 id (예: nv-123)")
    ap.add_argument("--scope", required=True, choices=["meta", "thumb"])
    ap.add_argument("--video-url", default="", help="thumb 스코프: 원본 영상 URL(또는 로컬 경로)")
    ap.add_argument("--base-dir", default=".")
    a = ap.parse_args()
    if a.scope == "meta":
        if not regen_meta(a.base_dir, a.cid):
            print("ERROR: 레코드 갱신 실패", file=sys.stderr)
            return 1
        print("META_OK")
        return 0
    thumb = regen_thumb(a.base_dir, a.cid, a.video_url)
    print(thumb)                                       # 마지막 줄 = 썸네일 경로(워크플로 파싱)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
