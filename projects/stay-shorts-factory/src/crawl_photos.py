#!/usr/bin/env python3
"""숙소 **공식 홈페이지** 사진 수집 — 2026-10-11 운영자 결정("크롤링으로 사진을 확보해") 구현.

범위와 안전장치 (운영자 결정 + 위험 최소화):
  - 숙소 공식 홈페이지만 긁는다. 쿠팡·네이버·인스타·유튜브·OTA(야놀자·여기어때·아고다·부킹·익스피디아 등)는
    **절대 안 긁는다** (약관 위반 → 파트너스 계정 정지·플랫폼 차단 위험). `DENY` 목록으로 코드가 막는다
  - robots.txt 를 지킨다 (`urllib.robotparser`). 페이지 사이 1초 쉼. 한 숙소 최대 10페이지 · 사진 최대 24장
  - WAF(Incapsula·Cloudflare 등)·403·캡차가 보이면 **바로 포기**한다. 차단 우회는 하지 않는다 (롯데호텔 사이트가 이 경우)
  - 사진 파일은 저장소에 커밋하지 않는다 (공개 저장소에서 재배포하지 않기 위해). 어느 페이지의 어느 사진을 썼는지
    출처 장부(`photo_sources.json`)만 남겨 호텔이 삭제를 요청하면 바로 찾을 수 있게 한다
  - 저작권 책임은 운영자 몫이다 (CLAUDE.md 결정 기록). 영상 설명에는 "사진: 숙소 공식 홈페이지" 를 적는다

도구: 헤드리스 크롬 `--dump-dom`(JS 로 그려지는 사이트도 렌더) + urllib + Pillow. 추가 설치 없음
  (GitHub 러너에는 google-chrome 이 기본 탑재, 이 개발 환경에는 Playwright 크로미움이 있다).
  실측(2026-10-11): 소노(비발디파크·쏠비치)는 Nuxt 로 그려져 원본 HTML 에 사진이 0장 → 렌더해야 20~45장(1024px) 나온다.
  롯데호텔은 Incapsula 가 헤드리스 크롬도 막는다 → 수집 불가로 기록. 세인트존스·웰리힐리는 정적 페이지라 바로 나온다.

사용:
  python3 src/crawl_photos.py "쏠비치 삼척" --url https://www.sonohotelsresorts.com/solbeach_sc --out build/crawl_test
  (URL 을 안 주면 네이버 지역검색 `link` → Gemini 추정 순으로 공식 홈페이지를 찾는다. 키가 없으면 수집하지 않는다)
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0.0.0 Safari/537.36")
MAX_PAGES = 10
MAX_IMAGES = 24
MIN_SHORT = 560          # 짧은 변 최소 (px)
MIN_LONG = 900           # 긴 변 최소 (px) — 1024px 사진은 통과, 썸네일은 탈락
PAGE_PAUSE = 1.0

# 절대 긁지 않는 곳 — 플랫폼·OTA·포털. 공식 홈페이지가 아니다
DENY = re.compile(r"coupang|naver\.|daum\.|kakao|instagram|facebook|youtube|tiktok|google\.|booking\.com|agoda|expedia|"
                  r"hotels\.com|trip\.com|yanolja|goodchoice|yeogi|tripadvisor|airbnb|interpark|trivago|hotelscombined|"
                  r"klook|myrealtrip|tidesquare|hanatour|modetour|dailyhotel|hotelpass|wikipedia|blog\.|cafe\.", re.I)
# 페이지 링크 점수 — 경로·링크 글자에 이 낱말이 있으면 먼저 본다
PAGE_KW = [
    (3, re.compile(r"pool|water|aqua|swim|spa|sauna|onsen|hotspring|bath|수영|워터|풀|스파|사우나|온천|온수|물놀이", re.I)),
    (2, re.compile(r"room|suite|guest|stay|accommodation|객실|룸|스위트|숙박|hotel|호텔|condo|콘도|villa|빌라", re.I)),
    (2, re.compile(r"facilit|amenit|gallery|photo|highlight|view|ocean|sea|garden|terrace|lounge|resort|"
                   r"시설|갤러리|사진|전망|오션|바다|정원|테라스|라운지|리조트|산책|둘러보기|소개", re.I)),
    (1, re.compile(r"entertain|discover|featured|relax|pet|kids|키즈|엔터|휴식|즐길", re.I)),
    # 2026-10-11 운영자 "사진을 찾을 방법을 어떻게든": 같은 도메인의 보도자료·뉴스룸·미디어 페이지(시그니처 시설 사진이 자주 있다). 외부 언론사는 DENY 로 계속 금지
    (1, re.compile(r"press|newsroom|media|보도|뉴스룸|미디어|pr\b", re.I)),
]
PAGE_SKIP = re.compile(r"event|notice|board|login|member|join|reserv|book|faq|terms|privacy|recruit|career|\.pdf|download|"
                       r"cart|mypage|search|sitemap|/en\b|/eng\b|/jp\b|/jpn\b|/cn\b|/zh\b|/chn\b|lang=|mailto:|tel:|javascript:|"
                       r"wedding|group|shopping|bakery|bistro|restaurant|dining|livetalk|location|guidemap|aboutus|notice|"
                       r"promotion|package|coupon|price|rate|regulation|policy|footer|intro|company|affiliate|history|featured|"
                       r"웨딩|단체|쇼핑|예약|공지|채용|이벤트|프로모션|패키지|요금|회사소개|추천상품", re.I)
IMG_SKIP = re.compile(r"\.svg|\.gif|\.ico|\.mp4|\.webm|\.m3u8|/_nuxt/|facebook\.com/tr|google|analytics|pixel|icon|logo|btn_|"
                      r"button|arrow|label_|badge|sprite|blank|loading|spinner|qr|map_|/map|favicon|emoji", re.I)
BLOCK_RE = re.compile(r"incapsula|request unsuccessful|access denied|cf-browser-verification|captcha|just a moment|"
                      r"attention required|bot detection|403 forbidden", re.I)


def log(*a):
    print("[crawl]", *a, flush=True)


# ── 브라우저 ───────────────────────────────────────────────────────────
def find_chrome() -> str | None:
    env = (os.environ.get("STAY_CHROME") or "").strip()
    if env and Path(env).exists():
        return env
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    hits = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
    return hits[-1] if hits else None


def render(url: str, chrome: str, timeout: int = 90) -> str:
    """JS 까지 실행한 뒤의 HTML. 실패하면 빈 문자열."""
    try:
        r = subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                            "--window-size=1280,8000", "--virtual-time-budget=20000", f"--user-agent={UA}",
                            "--dump-dom", url], capture_output=True, text=True, timeout=timeout)
        return r.stdout or ""
    except Exception as e:  # noqa: BLE001
        log(f"렌더 실패 {url}: {str(e)[:80]}")
        return ""


def fetch(url: str, referer: str | None = None, timeout: int = 40) -> tuple[bytes, str]:
    hdr = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    if referer:
        hdr["Referer"] = referer
    with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=timeout) as r:
        return r.read(), str(r.headers.get("Content-Type") or "")


# ── robots.txt ────────────────────────────────────────────────────────
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def allowed(url: str) -> bool:
    host = urllib.parse.urlsplit(url).netloc
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            data, _ = fetch(urllib.parse.urlunsplit(("https", host, "/robots.txt", "", "")), timeout=15)
            rp.parse(data.decode("utf-8", "replace").splitlines())
            _robots[host] = rp
        except Exception:  # noqa: BLE001
            _robots[host] = None          # robots.txt 가 없거나 못 읽음 → 관례상 허용
    rp = _robots[host]
    return True if rp is None else rp.can_fetch("*", url)


def blocked(html: str) -> str | None:
    """WAF·캡차·빈 응답이면 이유를 돌려준다."""
    if not html.strip():
        return "응답 없음"
    head = html[:4000]
    if BLOCK_RE.search(head) and len(html) < 20000:
        return "봇 차단(WAF) 페이지"
    if len(html) < 1500 and "<img" not in html:
        return "내용 없는 페이지"
    return None


# ── 페이지·이미지 추출 ──────────────────────────────────────────────
class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.imgs: list[str] = []
        self.alts: dict[str, str] = {}               # 사진 주소 → 공식 페이지의 사진 이름(alt·title) — 시설 이름 근거(2026-10-14 자쿠지 오표기)
        self._a: str | None = None
        self._txt: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self._a = a["href"]
            self._txt = []
        if tag in ("img", "source"):
            alt = re.sub(r"\s+", " ", str(a.get("alt") or a.get("title") or "")).strip()[:60]
            for k in ("src", "data-src", "data-original", "data-lazy", "data-lazy-src", "data-bg"):
                if a.get(k):
                    self.imgs.append(a[k])
                    if alt:
                        self.alts[a[k].strip()] = alt
            if a.get("srcset"):
                # srcset 은 "url 640w, url2 1280w" — 마지막(대개 가장 큰 것)을 쓴다
                parts = [p.strip().split()[0] for p in a["srcset"].split(",") if p.strip()]
                if parts:
                    self.imgs.append(parts[-1])
        style = a.get("style") or ""
        for m in re.finditer(r"url\(['\"]?([^'\")]+)", style):
            self.imgs.append(m.group(1))
        if tag == "a" and a.get("href") and re.search(r"\.(jpe?g|png|webp)(\?|$)", a["href"], re.I):
            self.imgs.append(a["href"])

    def handle_data(self, data):
        if self._a is not None:
            self._txt.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._a is not None:
            self.links.append((self._a, " ".join(self._txt).strip()[:60]))
            self._a = None


def parse(html: str) -> _Links:
    p = _Links()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001
        pass
    return p


class _Text(HTMLParser):
    """보이는 글만 — 시설 설명(수온·길이·운영시간·전망)을 나레이션 사실로 쓰기 위해 (운영자 2026-10-11 "설명이 너무 짧다")."""
    SKIP = ("script", "style", "noscript", "svg", "template", "head")
    BLOCK = ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "br", "tr", "section", "article", "dd", "dt")

    def __init__(self):
        super().__init__()
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def page_text(html: str) -> str:
    p = _Text()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001
        pass
    t = re.sub(r"[ \t \r]+", " ", "".join(p.out))
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def _norm(u: str) -> str:
    s = urllib.parse.urlsplit(u.strip())
    return urllib.parse.urlunsplit((s.scheme, s.netloc, s.path.rstrip("/"), s.query, ""))


def _first_seg(path: str) -> str:
    return path.strip("/").split("/")[0] if path.strip("/") else ""


FACILITY_WORDS = ("사우나", "찜질", "스파", "온천", "노천", "키즈", "조식", "산책", "라운지", "피트니스", "수영장", "워터파크", "파도풀", "유수풀", "자쿠지",
                  "sauna", "spa", "kids", "breakfast", "trail", "lounge", "fitness", "pool", "waterpark", "jacuzzi")


def _want_words(want) -> list[str]:
    """운영자가 원하는 시설 낱말: 확인된 시설("실내 온수풀", "히노키 사우나")을 2자 이상 낱말로 쪼갠 것 + 기본 시설 낱말."""
    out = list(FACILITY_WORDS)
    for w in want or []:
        for t in re.split(r"[\s·/,()]+", str(w)):
            if len(t) >= 2 and t not in out:
                out.append(t)
    return out


def discover_pages(root: str, html: str, limit: int = MAX_PAGES, extra: list[str] | None = None, want: list[str] | None = None) -> list[str]:
    """같은 사이트 안에서 시설·객실·사진 페이지를 점수순으로 고른다. 뿌리 페이지가 항상 첫째, 운영자가 준 추가 페이지가 그 다음.

    한 사이트에 여러 숙소가 있는 경우(소노: /felice_vp, /solbeach_sc, /village_dp …)가 많아, 뿌리 주소에 경로가 있으면
    **같은 첫 경로 밑의 페이지만** 본다 — 다른 숙소 사진이 섞이면 '실제와 다른 시설' 사고가 된다."""
    base = urllib.parse.urlsplit(root)
    seg = _first_seg(base.path)
    out = [_norm(root)]
    for e in extra or []:
        if _norm(e) not in out:
            out.append(_norm(e))
    scored: dict[str, float] = {}
    for href, text in parse(html).links:
        u = urllib.parse.urljoin(root, href.strip())
        s = urllib.parse.urlsplit(u)
        if s.scheme not in ("http", "https") or s.netloc != base.netloc:
            continue
        if seg and _first_seg(s.path) != seg:
            continue
        u = _norm(u)
        if u in out or PAGE_SKIP.search(s.path + " " + text):
            continue
        hay = s.path + " " + text
        score = sum(w for w, rx in PAGE_KW if rx.search(hay))
        # 2026-10-11 운영자 "사우나 같은 필요한 사진을 공식 홈페이지에서 다 반영": 이 숙소의 확인된 시설·테마 낱말이 링크에 있으면 그 페이지를 가장 먼저 본다
        score += sum(4 for w in _want_words(want) if w.lower() in hay.lower())
        if score:
            scored[u] = max(scored.get(u, 0), score - s.path.count("/") * 0.1)
    ranked = sorted(scored, key=lambda k: -scored[k])
    return out + ranked[: max(0, limit - len(out))]


def image_alts(page: str, html: str) -> dict[str, str]:
    """사진 절대 주소 → alt/title 글(있을 때만). 이미지 파일 이름 같은 의미 없는 값은 버린다."""
    out = {}
    for raw, alt in parse(html).alts.items():
        if re.fullmatch(r"[\w\-. ]{0,20}\.(jpe?g|png|webp)|image|img|이미지|사진|\d+", alt, re.I):
            continue
        out[urllib.parse.urljoin(page, raw)] = alt
    return out


def image_urls(page: str, html: str) -> list[str]:
    out: list[str] = []
    for raw in parse(html).imgs:
        raw = raw.strip()
        if not raw or raw.startswith("data:") or IMG_SKIP.search(raw):
            continue
        u = urllib.parse.urljoin(page, raw)
        s = urllib.parse.urlsplit(u)
        if s.scheme not in ("http", "https") or DENY.search(s.netloc):
            continue
        if u not in out:
            out.append(u)
    return out


# ── 공식 홈페이지 찾기 ─────────────────────────────────────────────
def _clean_url(u: str) -> str | None:
    u = (u or "").strip()
    if not u:
        return None
    if not u.startswith("http"):
        u = "https://" + u
    s = urllib.parse.urlsplit(u)
    if not s.netloc or DENY.search(s.netloc):
        return None
    return u


def resolve_official(name: str, city: str = "", gemini_json=None, model: str | None = None) -> tuple[str | None, str]:
    """공식 홈페이지 URL 과 근거. 네이버 지역검색의 link → Gemini 추정(이름이 페이지에 보여야 함) 순."""
    cid = (os.environ.get("NAVER_CLIENT_ID") or "").strip()
    sec = (os.environ.get("NAVER_CLIENT_SECRET") or "").strip()
    if cid and sec:
        q = urllib.parse.urlencode({"query": f"{name} {city}".strip(), "display": 5})
        req = urllib.request.Request(f"https://openapi.naver.com/v1/search/local.json?{q}",
                                     headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                js = json.loads(r.read().decode("utf-8"))
            core = re.sub(r"\s+", "", name)[:4]
            for it in js.get("items") or []:
                title = re.sub(r"<[^>]+>", "", str(it.get("title", "")))
                link = _clean_url(str(it.get("link", "")))
                if link and ("숙박" in str(it.get("category", "")) or core in re.sub(r"\s+", "", title)):
                    return link, f"네이버 지역검색 '{title}' link"
        except Exception as e:  # noqa: BLE001
            log(f"네이버 지역검색 실패: {str(e)[:60]}")
    if gemini_json and model:
        try:
            js = gemini_json(model, "숙소의 공식 홈페이지 주소를 안다면 JSON 으로만 답한다. 모르면 url 을 빈 문자열로. "
                             "예약 플랫폼(야놀자·아고다 등)·블로그·네이버 주소는 절대 쓰지 않는다. {\"url\":\"https://...\"}",
                             f"숙소: {name} ({city})")
            link = _clean_url(str((js or {}).get("url", "")))
            if link:
                return link, "Gemini 추정 (페이지에서 이름 확인 필요)"
        except Exception as e:  # noqa: BLE001
            log(f"Gemini 주소 추정 실패: {str(e)[:60]}")
    return None, "공식 홈페이지를 못 찾음 (네이버 키 없음 또는 결과 없음)"


# ── 수집 본체 ─────────────────────────────────────────────────────
def collect(name: str, city: str, out_dir: Path, official_url: str | list | None = None, max_images: int = MAX_IMAGES,
            max_pages: int = MAX_PAGES, gemini_json=None, model: str | None = None, want: list[str] | None = None) -> dict:
    """공식 홈페이지에서 사진을 모아 out_dir 에 저장. official_url 은 문자열 하나 또는 [뿌리, 추가 페이지…] 목록. 돌려주는 것:
    {"ok", "url", "reason", "pages": [..], "photos": [{"path","url","page","size","sha1"}], "tried": n}"""
    out_dir.mkdir(parents=True, exist_ok=True)
    res = {"ok": False, "name": name, "url": None, "reason": "", "pages": [], "photos": [], "tried": 0}
    chrome = find_chrome()
    if not chrome:
        res["reason"] = "크롬이 없어 렌더 불가 (STAY_CHROME 또는 google-chrome 필요)"
        log(res["reason"])
        return res
    given = [official_url] if isinstance(official_url, str) else list(official_url or [])
    given = [u for u in (_clean_url(g) for g in given) if u]
    url = given[0] if given else None
    extra = [u for u in given[1:] if allowed(u)]
    how = "request.json official_urls" if url else ""
    if not url:
        url, how = resolve_official(name, city, gemini_json, model)
    if not url:
        res["reason"] = how
        log(f"{name}: {how}")
        return res
    res["url"], res["resolved_by"] = url, how
    if not allowed(url):
        res["reason"] = "robots.txt 가 금지"
        log(f"{name}: robots.txt 가 {url} 수집을 금지 — 포기")
        return res
    html = render(url, chrome)
    why = blocked(html)
    if why:
        res["reason"] = f"{why} ({url})"
        log(f"{name}: {res['reason']} — 포기 (우회하지 않는다)")
        return res
    if how.startswith("Gemini"):
        core = re.sub(r"\s+", "", name)[:3]
        if core not in re.sub(r"\s+", "", html):
            res["reason"] = f"추정 주소 {url} 에 숙소 이름이 없음 — 포기"
            log(f"{name}: {res['reason']}")
            return res
    pages = discover_pages(url, html, max_pages, extra, want)
    # p3 실측(2026-10-11): 숙소 첫 페이지엔 그룹 전체 프로모션(다른 지점의 바다 인피니티풀)이 섞인다 → 시설·객실 페이지를 먼저 보고 첫 페이지는 맨 뒤
    pages = pages[1:] + pages[:1]
    res["pages"] = pages
    log(f"{name}: {url} ({how}) · 볼 페이지 {len(pages)}개 (첫 페이지는 맨 뒤)")
    # 그룹 홈(호스트 뿌리)에 걸린 사진은 여러 지점이 공유하는 배너일 가능성이 커서 제외한다
    shared: set[str] = set()
    base = urllib.parse.urlsplit(url)
    if base.path.strip("/"):
        home = urllib.parse.urlunsplit((base.scheme, base.netloc, "/", "", ""))
        if allowed(home):
            time.sleep(PAGE_PAUSE)
            shared = set(image_urls(home, render(home, chrome)))
            log(f"  그룹 홈 {home} 의 공용 사진 {len(shared)}장은 제외 (다른 지점 사진 혼입 방지)")
    res["shared_excluded"] = 0
    res["text"] = {}                              # 페이지별 보이는 글 — 시설 사실(수온·길이·전망) 추출용. 사진 한도와 무관하게 모은다
    seen_url, seen_hash = set(), set()
    htmls = {_norm(url): html}
    for i, page in enumerate(pages):
        if page not in htmls:
            if not allowed(page):
                continue
            time.sleep(PAGE_PAUSE)
            htmls[page] = render(page, chrome)
            if blocked(htmls[page]):
                continue
        if len(res["text"]) < 12:
            res["text"][page] = page_text(htmls[page])[:2500]
        if len(res["photos"]) >= max_images:
            continue
        found = [u for u in image_urls(page, htmls[page]) if u not in seen_url]
        alts = image_alts(page, htmls[page])
        urls = [u for u in found if u not in shared]
        res["shared_excluded"] += len(found) - len(urls)
        got = 0
        for u in urls:
            if len(res["photos"]) >= max_images:
                break
            seen_url.add(u)
            res["tried"] += 1
            try:
                data, ctype = fetch(u, referer=page)
                if "image" not in ctype and not re.search(r"\.(jpe?g|png|webp)(\?|$)", u, re.I):
                    continue
                with Image.open(io.BytesIO(data)) as im:
                    w, h = im.size
                    if min(w, h) < MIN_SHORT or max(w, h) < MIN_LONG or not (0.35 <= w / h <= 2.8):
                        continue
                    sha = hashlib.sha1(data).hexdigest()
                    if sha in seen_hash:
                        continue
                    seen_hash.add(sha)
                    n = len(res["photos"])
                    dest = out_dir / f"off_{n:02d}.jpg"
                    im.convert("RGB").save(dest, "JPEG", quality=93)
                res["photos"].append({"path": str(dest), "url": u, "page": page, "size": [w, h], "sha1": sha[:12], "alt": alts.get(u, "")})
                got += 1
            except Exception as e:  # noqa: BLE001
                log(f"사진 실패 {u[-60:]}: {str(e)[:50]}")
            time.sleep(0.25)
        log(f"  페이지 {i + 1}/{len(pages)} {urllib.parse.urlsplit(page).path or '/'} → 사진 {got}장 (누적 {len(res['photos'])})")
    res["ok"] = bool(res["photos"])
    if res["ok"]:
        res["reason"] = ""
    elif res["tried"] == 0:
        res["reason"] = "사진 주소를 하나도 못 찾음 (봇 차단·빈 페이지 가능성)"
    else:
        res["reason"] = "조건(해상도 900px↑)에 맞는 사진이 없음"
    (out_dir / "text.json").write_text(json.dumps(res["text"], ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "photo_sources.json").write_text(json.dumps({k: v for k, v in res.items() if k != "text"}, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"{name}: 사진 {len(res['photos'])}장 (시도 {res['tried']}) · 글 {sum(len(t) for t in res['text'].values()):,}자 · 장부 {out_dir / 'photo_sources.json'}")
    return res


def contact_sheet(photos: list[dict], out: Path, cols: int = 6, cell: int = 300) -> Path | None:
    """검수용 한 장 — 번호·크기 표시."""
    if not photos:
        return None
    from PIL import ImageDraw
    rows = (len(photos) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (18, 18, 18))
    d = ImageDraw.Draw(sheet)
    for i, p in enumerate(photos):
        with Image.open(p["path"]) as im:
            im = im.convert("RGB")
            im.thumbnail((cell - 8, cell - 8), Image.LANCZOS)
            x, y = (i % cols) * cell + 4, (i // cols) * cell + 4
            sheet.paste(im, (x, y))
            d.rectangle([x, y, x + 86, y + 18], fill=(0, 0, 0))
            d.text((x + 3, y + 3), f"{i} {p['size'][0]}x{p['size'][1]}", fill=(255, 230, 100))
    sheet.save(out, "JPEG", quality=85)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="숙소 공식 홈페이지 사진 수집")
    ap.add_argument("name")
    ap.add_argument("--city", default="")
    ap.add_argument("--url", default=None, help="공식 홈페이지 주소 (없으면 네이버 지역검색으로 찾는다)")
    ap.add_argument("--out", default="build/crawl_test")
    ap.add_argument("--max", type=int, default=MAX_IMAGES)
    ap.add_argument("--pages", type=int, default=MAX_PAGES)
    a = ap.parse_args()
    out = Path(a.out) / re.sub(r"[^\w가-힣]+", "_", a.name)
    res = collect(a.name, a.city, out, a.url, a.max, a.pages)
    sheet = contact_sheet(res["photos"], out / "sheet.jpg")
    print(json.dumps({k: res[k] for k in ("ok", "url", "reason", "tried")} | {"photos": len(res["photos"]),
                      "sheet": str(sheet) if sheet else None}, ensure_ascii=False))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
