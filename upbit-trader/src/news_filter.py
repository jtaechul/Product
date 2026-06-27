"""뉴스 감성 '브레이크' — Claude API로 XRP 뉴스를 평가해 위험한 매수를 거른다.

설계 철학(중요): 뉴스/AI는 '운전대'가 아니라 '브레이크'다.
  · 매수 결정의 주체는 검증된 기술적 신호(swing.is_entry)다.
  · 이 모듈은 기술적 신호가 '사라'고 할 때, 뉴스가 '강한 악재'면 그 매수만 보류시킨다.
  · 뉴스/AI 단독으로는 절대 매수하지 않는다(백테스트 불가 → 검증된 엣지가 아님).

안전한 점진 적용(graceful degradation):
  · ANTHROPIC_API_KEY 가 없거나, 뉴스 수집/평가가 실패하면 → '허용'(allow=True)으로
    되돌아가 봇은 순수 기술적 전략으로 정상 작동한다. 뉴스 때문에 봇이 멈추지 않는다.

환경변수:
  · ANTHROPIC_API_KEY : Claude API 키(없으면 뉴스 브레이크 비활성)
  · XRP_NEWS_MODEL    : 사용할 모델(기본 claude-haiku-4-5-20251001 — 저렴·빠름)
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

# Google 뉴스 RSS(무료, 키 불필요). XRP/Ripple 최근 헤드라인.
_RSS_URL = ("https://news.google.com/rss/search?q="
            + urllib.parse.quote("XRP OR Ripple cryptocurrency when:7d")
            + "&hl=en-US&gl=US&ceid=US:en")
_API_URL = "https://api.anthropic.com/v1/messages"
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class NewsVerdict:
    allow: bool          # 이 매수를 허용해도 되는가(강한 악재면 False)
    enabled: bool        # 뉴스 브레이크가 실제로 작동했는가(키/네트워크 OK)
    score: int           # -100(악재) ~ +100(호재)
    label: str           # POSITIVE / NEUTRAL / NEGATIVE / DISABLED / ERROR
    reason: str          # 한 줄 한국어 사유
    headlines: list[str]


def fetch_headlines(limit: int = 12, timeout: int = 10) -> list[str]:
    """Google 뉴스 RSS에서 XRP 관련 최근 헤드라인 제목만 추출."""
    req = urllib.request.Request(_RSS_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "ignore")
    # <item><title>…</title> 만 가볍게 추출(외부 XML 파서 의존 회피)
    titles = re.findall(r"<item>.*?<title>(.*?)</title>", raw, re.S)
    out = []
    for t in titles:
        t = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t, flags=re.S).strip()
        t = re.sub(r"<.*?>", "", t).strip()
        if t:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def _call_claude(headlines: list[str], timeout: int = 20) -> dict:
    """Claude API에 헤드라인 감성 평가를 요청. JSON dict 반환."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("no_api_key")
    model = os.environ.get("XRP_NEWS_MODEL", _DEFAULT_MODEL)
    bullets = "\n".join(f"- {h}" for h in headlines)
    prompt = (
        "다음은 암호화폐 XRP(리플) 관련 최근 영어 뉴스 헤드라인이다.\n"
        "전체를 종합해 단기(수일) 가격에 미칠 '감성'을 판정하라. 과장 금지, 보수적으로.\n\n"
        f"{bullets}\n\n"
        "아래 JSON만 출력(설명 금지):\n"
        '{\"score\": <-100~100 정수>, \"label\": \"POSITIVE|NEUTRAL|NEGATIVE\", '
        '\"reason\": \"한국어 한 문장\"}')
    body = json.dumps({
        "model": model,
        "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(_API_URL, data=body, headers={
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    text = "".join(b.get("text", "") for b in resp.get("content", []))
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError("no_json")
    return json.loads(m.group(0))


def assess(neg_threshold: int = 50) -> NewsVerdict:
    """뉴스를 수집·평가해 매수 허용 여부 판정.

    neg_threshold: 점수가 -neg_threshold 이하('강한 악재')면 매수 보류(allow=False).
    실패(키 없음/네트워크/파싱)는 모두 allow=True 로 안전 복귀.
    """
    try:
        heads = fetch_headlines()
    except Exception as exc:
        return NewsVerdict(True, False, 0, "ERROR", f"뉴스 수집 실패({exc})", [])
    if not heads:
        return NewsVerdict(True, False, 0, "ERROR", "헤드라인 없음", [])
    try:
        j = _call_claude(heads)
    except Exception as exc:
        tag = "DISABLED" if str(exc) == "no_api_key" else "ERROR"
        msg = ("API 키 없음 — 뉴스 브레이크 꺼짐(순수 기술적 매매)"
               if tag == "DISABLED" else f"평가 실패({exc})")
        return NewsVerdict(True, False, 0, tag, msg, heads)
    score = int(j.get("score", 0))
    label = str(j.get("label", "NEUTRAL")).upper()
    reason = str(j.get("reason", "")).strip()
    allow = score > -abs(neg_threshold)
    return NewsVerdict(allow, True, score, label, reason, heads)
