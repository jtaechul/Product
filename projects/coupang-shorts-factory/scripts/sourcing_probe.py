"""틱톡 소싱 실현성 프로브 (SSOT §6.2 · 2026-07-26 사용자 확정 방향).

사용자 결정: 유튜브 제외, **틱톡만** 소싱·자동 다운로드. GA가 틱톡에 직접 붙는 건 봇차단
(1차 프로브 확인)이라, '틱톡 다운로더 서비스'(공개 API)를 경유해 우회한다(사용자 제안).

이 프로브는 무료 서비스(tikwm)가 GitHub Actions 러너에서 실제로 되는지 확인한다:
  1) 검색(발굴): 키워드로 틱톡 쇼츠 목록을 받는가  → 운영자에게 5~10개 추천 가능?
  2) 취득(다운로드): 무워터마크 재생 URL에서 실제 영상 바이트를 받는가

메타 + 소량(1개) 다운로드만. 항상 exit 0(정보성). 잡 로그의 'VERDICT:' 를 본다.
비공식 API라 불안정 가능 → 실제 구현은 서비스 교체 가능한 어댑터로 감싼다.
"""
import json
import sys
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BASE = "https://www.tikwm.com"
KEYWORD = "꿀템"


def http(url, data=None, timeout=45):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body,
                                 headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def search(keywords):
    """tikwm 키워드 검색 — POST 우선, 실패 시 GET. (how, json|err) 반환."""
    last = None
    for how in ("post", "get"):
        try:
            params = {"keywords": keywords, "count": 6, "cursor": 0, "hd": 1}
            if how == "post":
                raw = http(f"{BASE}/api/feed/search", data=params)
            else:
                raw = http(f"{BASE}/api/feed/search?" + urllib.parse.urlencode(params))
            j = json.loads(raw)
            if j.get("code") == 0:
                return how, j
            last = f"code={j.get('code')} msg={j.get('msg')}"
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:130]}"
    return None, last


def main() -> int:
    results = {}

    print(f"── 틱톡 무료 우회(tikwm) · 키워드='{KEYWORD}' ──")
    how, j = search(KEYWORD)
    vids = []
    if how:
        vids = ((j.get("data") or {}).get("videos")) or []
    ok_search = len(vids) > 0
    first = vids[0] if vids else {}
    results["search"] = {"ok": ok_search, "how": how, "n": len(vids),
                         "err": None if how else j,
                         "first_title": str(first.get("title", ""))[:40],
                         "first_id": first.get("video_id"),
                         "first_views": first.get("play_count")}
    if ok_search:
        print(f"  [OK  ] 검색({how}): {len(vids)}건 · 첫 제목={str(first.get('title',''))[:34]} · 조회={first.get('play_count')}")
    else:
        print(f"  [FAIL] 검색: {j}")

    # 취득: 첫 결과의 무워터마크 재생 URL에서 실제 바이트 소량 확인
    play = first.get("play")
    if play and not play.startswith("http"):
        play = BASE + play
    if play:
        try:
            data = http(play, timeout=60)
            n = len(data)
            ok_dl = n > 100_000 and data[:12] not in (b"", None)   # 100KB+ = 실제 영상
            results["download"] = {"ok": bool(ok_dl), "bytes": n,
                                   "head": data[4:12].decode("latin1", "replace")}
            print(f"  [{'OK  ' if ok_dl else 'FAIL'}] 다운로드: {n:,} bytes (head={data[4:12]!r})")
        except Exception as e:
            results["download"] = {"ok": False, "err": f"{type(e).__name__}: {str(e)[:150]}"}
            print(f"  [FAIL] 다운로드: {type(e).__name__}: {str(e)[:150]}")
    else:
        results["download"] = {"ok": False, "err": "검색 결과 없음(play URL 없음)"}
        print("  [SKIP] 다운로드: 검색 결과 없어 건너뜀")

    viable = bool(results["search"]["ok"] and results["download"]["ok"])
    print()
    print(f"VERDICT: tiktok_free={'VIABLE' if viable else 'BLOCKED'}  (검색+다운로드 모두 성공해야 VIABLE)")
    print("SUMMARY_JSON: " + json.dumps(results, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
