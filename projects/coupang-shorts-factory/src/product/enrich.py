"""M2.5 — 상품 정보 보강 (쿠팡 API 승인 전 운영 플로우).

관리자 페이지에서 사용자는 제휴 링크 + 상세 자료만 등록한다. 자료 소스(data/notes/):
  {row_hash}.md              — 붙여넣은 텍스트
  {row_hash}_N.pdf           — 쿠팡 상품 페이지 전체 캡처 PDF (iOS 스크린샷 '전체 페이지' 등)
  {row_hash}_N.jpg|png|webp  — 캡처 이미지
상품명·가격·특징이 비어 있거나 캡처가 있으면 Claude 비전으로 핵심 정보를 추출해 채우고,
추출 요약은 notes로 M3 대본 생성(후기 통증포인트)에 전달된다.

전체 페이지 캡처 PDF는 세로로 극단적으로 긴 1페이지(예: 1180x14400pt)라 그대로 주면
렌더링 축소로 글자가 뭉개진다 → PyMuPDF로 상단(제목·가격)과 '상품평'·'상품상세' 주변을
타일 이미지로 잘라 보낸다. 텍스트 레이어도 함께 추출해 첨부(가격 등은 텍스트가 정확).

쿠팡 페이지 자동 수집(크롤링)은 봇 차단(403) + 스펙 §2·§3.2 위반이라 구현하지 않는다.
캡처 이미지는 '정보 추출 전용'이며 영상 화면에는 넣지 않는다(§3.2 화이트리스트).
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOTES_DIR = PROJECT_ROOT / "data" / "notes"
IMG_EXTS = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
MAX_IMAGE_BYTES = 4_500_000  # Anthropic 이미지 한도(5MB) 아래로 방어
MAX_IMAGES = 6

_EXTRACT_PROMPT = """첨부는 사용자가 올린 쿠팡 상품 페이지 자료다(캡처 이미지/PDF 타일 + 텍스트).
'메인 상품' 정보만 추출하라 — 페이지에는 광고·추천·비교 상품이 섞여 있으니 전부 무시한다
(메인 상품 = 페이지 최상단 제목과 가격 박스의 상품).
JSON만 반환, 다른 텍스트·백틱 금지. 스키마:
{"name": "상품명(30자 내)", "price": 현재판매가_정수, "specs": ["숫자 위주 핵심 특징 2~4개"],
 "category": "카테고리 한 단어", "review_points": ["실사용 후기 요점 0~3개 (후기가 보일 때만)"]}
가격이 여러 개 보이면 할인 적용된 현재 판매가를 고른다. 후기가 안 보이면 review_points는 []."""


def enrich_product(product: dict, settings: dict) -> dict:
    """이름·가격·특징이 비거나 캡처 자료가 있으면 추출해 보강. notes는 항상 첨부."""
    text, pdf_text, images = _gather_assets(product["_row_hash"])

    fields_missing = not (product.get("name") and product.get("price", 0) > 0 and product.get("specs"))
    if not fields_missing and not images:
        if text:
            product["notes"] = text[:4000]
        return product
    if fields_missing and not (text or images):
        raise RuntimeError(
            "상품명·가격·특징이 비어 있고 상세 자료(텍스트/캡처)도 없습니다. "
            "관리자 페이지에서 캡처 파일을 첨부하거나 직접 입력으로 등록해 주세요.")

    data = _extract(text, pdf_text, images, settings)

    if not product.get("name"):
        product["name"] = str(data.get("name", "")).strip()[:60]
    if product.get("price", 0) <= 0:
        product["price"] = int(re.sub(r"[^\d]", "", str(data.get("price", 0))) or 0)
    if not product.get("specs"):
        product["specs"] = [str(s).strip() for s in (data.get("specs") or []) if str(s).strip()][:4]
    if not product.get("category"):
        product["category"] = str(data.get("category", "")).strip()[:20]

    reviews = [str(r).strip() for r in (data.get("review_points") or []) if str(r).strip()][:3]
    digest = "특징: " + "; ".join(product.get("specs") or [])
    if reviews:
        digest += "\n실사용 후기 요점: " + " / ".join(reviews)
    product["notes"] = ((text + "\n" if text else "") + "[캡처에서 추출한 요점]\n" + digest)[:4000]

    if not product["name"] or product["price"] <= 0:
        raise RuntimeError(
            "자료에서 상품명 또는 가격을 찾지 못했습니다. 캡처에 상단 제목·가격 부분이 "
            "포함됐는지 확인하거나, 관리자 페이지 '직접 입력'에 채워 다시 등록해 주세요.")
    print(f"[enrich] M2.5 보강 완료: {product['name']} ({product['price']:,}원, "
          f"특징 {len(product['specs'])}개, 후기 요점 {len(reviews)}개, "
          f"자료: 이미지 {len(images)}장/텍스트 {len(text) + len(pdf_text)}자)")
    return product


def _gather_assets(row_hash: str):
    """data/notes/에서 이 상품의 텍스트·PDF 타일·이미지를 수집."""
    text = ""
    md = NOTES_DIR / f"{row_hash}.md"
    if md.exists():
        text = md.read_text(encoding="utf-8").strip()

    pdf_text, images = "", []
    for p in sorted(NOTES_DIR.glob(f"{row_hash}*")):
        if len(images) >= MAX_IMAGES:
            break
        suf = p.suffix.lower()
        if suf == ".pdf":
            try:
                tiles = _pdf_tiles(p, max_tiles=MAX_IMAGES - len(images))
                images += [("image/png", t) for t in tiles]
                full = _pdf_text(p)
                # 앞부분(상품명·가격·스펙) + 끝부분(상품평 후기가 몰리는 구간) 샘플링
                pdf_text += full[:1800] + ("\n...(중략)...\n" + full[-1700:] if len(full) > 3600 else full[1800:])
            except Exception as e:
                print(f"[enrich] 경고: PDF 처리 실패({p.name}: {e}) — 건너뜀")
        elif suf in IMG_EXTS:
            data = p.read_bytes()
            if len(data) > MAX_IMAGE_BYTES:
                print(f"[enrich] 경고: {p.name} 이 너무 큼({len(data) >> 20}MB) — 건너뜀")
                continue
            images.append((IMG_EXTS[suf], data))
    return text, pdf_text[:3500], images


def _pdf_text(pdf_path: Path) -> str:
    import fitz
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)


def _pdf_tiles(pdf_path: Path, width_px: int = 768, max_tiles: int = 5) -> list:
    """PDF를 읽을 수 있는 타일 PNG로 분할.
    일반 페이지는 통짜 1장, 전체 캡처형 초장문 페이지는 상단 2타일 + '상품평'/'상품상세'
    키워드 주변 타일을 우선 렌더링한다."""
    import fitz
    doc = fitz.open(pdf_path)
    out = []
    for pidx, page in enumerate(doc):
        if len(out) >= max_tiles:
            break
        # 뒤 페이지(상세 하단·리뷰)에도 최소 1장씩 배정되도록 앞 페이지 사용량 제한
        allow = max(1, (max_tiles - len(out)) - (doc.page_count - pidx - 1))
        r = page.rect
        zoom = width_px / r.width
        mat = fitz.Matrix(zoom, zoom)
        if r.height <= r.width * 3:  # 일반 비율 페이지 → 통짜
            out.append(page.get_pixmap(matrix=mat).tobytes("png"))
            continue
        tile_h = r.width * 2.2
        ys = [0.0, tile_h]  # 상단(제목·가격 박스) 우선
        for kws in (("상품평", "리뷰"), ("상품상세", "상품 상세")):
            for kw in kws:
                hits = page.search_for(kw)
                if hits:
                    ys.append(max(0.0, hits[-1].y0 - tile_h * 0.1))
                    break
        # 전체 캡처는 하단 상세컷·리뷰가 글자층 없이 이미지로만 존재하는 경우가 많다
        # → 중·하단을 비율 샘플링해 스펙 이미지와 후기 영역도 커버
        ys += [r.height * f for f in (0.35, 0.62, 0.88)]
        merged = []
        for y in sorted(set(ys)):
            if not merged or y - merged[-1] >= tile_h * 0.6:
                merged.append(y)
        for y in merged[:allow]:
            clip = fitz.Rect(0, y, r.width, min(y + tile_h, r.height))
            if clip.height < 60:
                continue
            out.append(page.get_pixmap(matrix=mat, clip=clip).tobytes("png"))
    return out


def _extract(text: str, pdf_text: str, images: list, settings: dict) -> dict:
    from src.script.generate import anthropic_key
    key = anthropic_key()
    if not key:
        raise RuntimeError(
            "상품 정보 자동 추출에 Anthropic 키가 필요합니다 "
            "(SHORTS_ANTHROPIC_API_KEY 또는 ANTHROPIC_API_KEY 시크릿).")

    content = []
    for media, data in images:
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": media, "data": base64.b64encode(data).decode()}})
    body = ""
    if text:
        body += f"\n[사용자가 붙여넣은 텍스트]\n{text[:3000]}"
    if pdf_text:
        body += f"\n[PDF 텍스트 레이어(가격·수치는 이쪽이 정확)]\n{pdf_text}"
    content.append({"type": "text", "text": body.strip() or "(첨부 이미지 참조)"})

    import anthropic
    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model=settings.get("script", {}).get("model", "claude-sonnet-4-6"),
        max_tokens=800,
        system=_EXTRACT_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    u = getattr(resp, "usage", None)
    if u:  # 비용 투명화: 입력 1만 토큰 ≈ 45원(Sonnet) 수준
        print(f"[enrich] 토큰 사용: 입력 {u.input_tokens:,} / 출력 {u.output_tokens:,}")
    out = "".join(b.text for b in resp.content if b.type == "text")
    start, end = out.find("{"), out.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("자료에서 상품 정보를 추출하지 못했습니다(JSON 없음).")
    return json.loads(out[start:end + 1])
