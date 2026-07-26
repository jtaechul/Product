"""소싱용 번역·검색어 확장 (Gemini 텍스트 — 저가·허용, 영상 생성 아님).

- expand_zh_terms: 한국어 키워드 → 중국어(간체) 검색어 3~5개로 확장(틱톡 중국 쇼핑 쇼츠 겨냥).
- translate_titles_ko: 영상 제목/설명(주로 중국어) → 한국어 한 줄 설명(선택 판단용).

의존성 없이 urllib로 Gemini generateContent 호출(소싱 워크플로는 stdlib만 설치).
키(GEMINI_API_KEY/SHORTS_GEMINI_API_KEY)가 없거나 실패하면 **원문 폴백**(발굴은 계속 동작).
call 인자로 Gemini 호출을 주입 가능(단위 테스트 — 네트워크 없이).
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL = "gemini-2.5-flash"


def gemini_key() -> str | None:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("SHORTS_GEMINI_API_KEY") or "").strip() or None


def _extract_json(txt: str) -> dict:
    m = re.search(r"\{.*\}", txt or "", re.S)
    return json.loads(m.group(0)) if m else {}


def _gemini_json(prompt: str, system: str, max_tokens: int = 1024,
                 model: str = GEMINI_MODEL, call=None, image: tuple | None = None) -> dict:
    """Gemini에 JSON 응답을 요청해 파싱한 dict 반환. call 주입 시 그걸로 호출(테스트).
    image=(base64, mime) 주면 비전(이미지+텍스트) 요청 — 영상 '생성'이 아니라 이미지 '입력' 분석(허용)."""
    parts = [{"text": prompt}]
    if image:
        parts.append({"inline_data": {"mime_type": image[1], "data": image[0]}})
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "maxOutputTokens": max_tokens, "temperature": 0.4,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0},   # 2.5 Flash 사고 OFF(출력 예산 확보)
        },
    }
    if call is not None:
        data = call(body)
    else:
        key = gemini_key()
        if not key:
            raise RuntimeError("Gemini 키 없음")
        req = urllib.request.Request(
            f"{GEMINI_BASE}/models/{model}:generateContent",
            data=json.dumps(body).encode("utf-8"),
            headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
    cands = data.get("candidates") or []
    parts = ((cands[0].get("content") or {}).get("parts") if cands else []) or []
    txt = "".join(p.get("text", "") for p in parts)
    return _extract_json(txt)


def expand_zh_terms(korean_keyword: str, call=None) -> list:
    """한국어 키워드 → 중국어 검색어 리스트(원문 폴백 포함, 항상 1개 이상)."""
    kw = (korean_keyword or "").strip()
    if not kw:
        return []
    if call is None and not gemini_key():
        return [kw]   # 키 없음 → 원문(틱톡은 원문으로도 검색됨)
    system = ("너는 쇼핑 쇼츠 소싱 도우미다. 한국어 키워드를 중국어(간체)로 번역하고, "
              "틱톡에서 조회수 높은 '중국 쇼핑/신박한 상품' 쇼츠를 찾기 좋은 관련 중국어 검색어로 확장한다. "
              "너무 일반적이지 않게 상품군을 특정하라. JSON만 출력.")
    prompt = (f'키워드: "{kw}"\n'
              '이 키워드와 관련된 중국어 검색어 3~5개를 JSON으로: {"terms": ["...", "..."]}')
    try:
        terms = [str(t).strip() for t in (_gemini_json(prompt, system, 512, call=call).get("terms") or []) if str(t).strip()]
        return terms[:5] or [kw]
    except Exception as e:
        print(f"[translate] 중국어 확장 실패: {e} → 원문 사용")
        return [kw]


def describe_and_keywords_ko(titles: list, call=None) -> list:
    """영상 제목/설명(주로 중국어) → 각 항목 [{"ko": 한 줄 설명, "keywords": [쿠팡 검색어 2~4개]}].

    §1(발굴) 카드에 '한국어 설명 + 운영자가 쿠팡에서 검색할 한국어 상품 검색어'를 함께 붙인다.
    개수·순서 보존. 키 없음/실패 시 폴백(ko=원문, keywords=[]) — 발굴은 계속 동작.
    """
    titles = [("" if t is None else str(t)) for t in (titles or [])]
    if not titles:
        return []
    fallback = [{"ko": t, "keywords": []} for t in titles]
    if call is None and not gemini_key():
        return list(fallback)
    system = ("너는 한국 쇼핑 쇼츠 소싱 도우미다. 틱톡 쇼핑 영상의 제목/설명(주로 중국어)을 보고 "
              "① 무슨 상품·무슨 내용인지 한국어 한 줄 설명 ② 그 상품을 한국 '쿠팡'에서 검색할 "
              "한국어 상품 검색어 2~4개를 뽑는다. 검색어는 상품의 '종류·핵심기능' 위주의 짧은 명사구로 "
              "(브랜드·과장·이모지·해시태그·'링크 클릭' 같은 판매유도 문구 제외). JSON만 출력.")
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
    prompt = (f"각 항목을 처리하라(입력 순서·개수 그대로):\n{numbered}\n"
              '출력 JSON: {"items": [{"ko": "한 줄 설명", "keywords": ["검색어1", "검색어2"]}, ...]}')
    try:
        items = _gemini_json(prompt, system, 2048, call=call).get("items") or []
        out = []
        for i in range(len(titles)):
            it = items[i] if i < len(items) and isinstance(items[i], dict) else {}
            ko = str(it.get("ko") or "").strip() or titles[i]
            kws = [str(k).strip() for k in (it.get("keywords") or []) if str(k).strip()][:4]
            out.append({"ko": ko, "keywords": kws})
        return out
    except Exception as e:
        print(f"[translate] 설명·검색어 추출 실패: {e} → 원문 폴백")
        return list(fallback)


def _fetch_image_b64(url: str, timeout: int = 20) -> tuple | None:
    """썸네일 URL → (base64 문자열, mime). 실패 시 None. stdlib만."""
    import base64
    u = (url or "").strip()
    if not u:
        return None
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            ct = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    except Exception as e:
        print(f"[vision] 썸네일 다운로드 실패({u[:60]}): {type(e).__name__}")
        return None
    if not raw or len(raw) > 6_000_000:   # 6MB 초과는 스킵(썸네일치곤 비정상)
        return None
    mime = ct if ct.startswith("image/") else "image/jpeg"
    return (base64.b64encode(raw).decode("ascii"), mime)


_VISION_SYSTEM = (
    "너는 한국 쇼핑 쇼츠 소싱 도우미다. 틱톡 쇼핑 영상의 '썸네일 이미지'와 제목(주로 중국어)을 함께 보고, "
    "영상이 실제로 '파는 물건(상품)'이 무엇인지 이미지를 근거로 식별한다. 사람·손·배경·화면 글자·로고는 무시하고 "
    "화면 중심의 주인공 상품에 집중하라. 브랜드가 불명확하면 '상품 종류 + 핵심 기능'으로 표현하라. JSON만 출력.")


def identify_by_image(items: list, call=None, fetch=None) -> list:
    """[{"title","cover"}] → [{"ko","keywords","zh"}] (개수·순서 보존).

    각 항목의 썸네일을 Gemini Vision으로 '보고' 실제 상품을 식별한다(제목 텍스트만 추측하던 오매칭 개선):
      - ko       : 한국어 한 줄 상품 설명(카드 표시)
      - keywords : 쿠팡에서 검색할 한국어 상품 검색어 2~4개(② 네이버·쿠팡 매칭용)
      - zh       : 틱톡에서 '같은 상품'의 다른 홍보영상을 찾을 중국어 검색어 2~3개(③ — 한국어 되돌림 왕복 제거)
    이미지가 없거나 비전 실패면 그 항목만 제목 기반(describe_and_keywords_ko)으로 폴백. call/fetch 주입(테스트).
    """
    items = list(items or [])
    if not items:
        return []
    titles = [str((it or {}).get("title") or "") for it in items]
    if call is None and not gemini_key():
        base = describe_and_keywords_ko(titles)
        return [{"ko": b["ko"], "keywords": b["keywords"], "zh": []} for b in base]
    fetch = fetch or _fetch_image_b64
    out = []
    for it, title in zip(items, titles):
        img = None
        try:
            img = fetch((it or {}).get("cover") or "")
        except Exception:
            img = None
        if not img:   # 이미지 없음 → 제목 기반 폴백(그 항목만)
            b = describe_and_keywords_ko([title])[0]
            out.append({"ko": b["ko"], "keywords": b["keywords"], "zh": []})
            continue
        prompt = (f'영상 제목: "{title}"\n'
                  "이 썸네일 속 '파는 상품'을 식별해 JSON으로 출력:\n"
                  '{"ko": "한국어 한 줄 설명", "keywords": ["쿠팡 한국어 검색어 2~4개(종류+핵심기능, 짧은 명사구, '
                  '브랜드·과장·이모지 제외)"], "zh": ["같은 상품을 틱톡에서 찾을 중국어 검색어 2~3개"]}')
        try:
            d = _gemini_json(prompt, _VISION_SYSTEM, 512, call=call, image=img)
            ko = str(d.get("ko") or "").strip() or title
            kws = [str(k).strip() for k in (d.get("keywords") or []) if str(k).strip()][:4]
            zh = [str(z).strip() for z in (d.get("zh") or []) if str(z).strip()][:3]
            if not kws:   # 비전이 검색어를 못 주면 제목 기반 보완
                kws = describe_and_keywords_ko([title])[0]["keywords"]
            out.append({"ko": ko, "keywords": kws, "zh": zh})
        except Exception as e:
            print(f"[vision] 상품 식별 실패({title[:30]}): {type(e).__name__} → 제목 폴백")
            b = describe_and_keywords_ko([title])[0]
            out.append({"ko": b["ko"], "keywords": b["keywords"], "zh": []})
    return out


def translate_titles_ko(titles: list, call=None) -> list:
    """영상 제목/설명 → 한국어 한 줄 설명(개수·순서 보존, 실패 시 원문 폴백)."""
    titles = [("" if t is None else str(t)) for t in (titles or [])]
    if not titles:
        return []
    if call is None and not gemini_key():
        return list(titles)
    system = ("너는 번역가다. 틱톡 쇼핑 영상의 제목/설명(주로 중국어)을 한국어 한 줄로 번역·요약한다. "
              "이모지·해시태그·'링크 클릭' 같은 판매유도 문구는 빼고 '무슨 상품/무슨 내용인지'만 담아라. "
              "JSON만 출력.")
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
    prompt = (f"각 항목을 한국어 한 줄 설명으로 바꿔라(입력 순서·개수 그대로):\n{numbered}\n"
              '출력 JSON: {"ko": ["0번 한국어", "1번 한국어", ...]}')
    try:
        ko = _gemini_json(prompt, system, 2048, call=call).get("ko") or []
        return [(str(ko[i]).strip() if i < len(ko) and str(ko[i]).strip() else titles[i])
                for i in range(len(titles))]
    except Exception as e:
        print(f"[translate] 제목 번역 실패: {e} → 원문 사용")
        return list(titles)
