"""소싱 실현성 프로브 (SSOT §6.2 — 자동 크롤이 GitHub Actions에서 되는지 판정).

GitHub Actions 러너의 데이터센터 IP에서 yt-dlp가 유튜브·틱톡 소싱 소스에 실제로 닿는지
**메타데이터만** 조회해 확인한다(다운로드·재게시 없음 → 저작권·부하 부담 0).

판정:
- youtube: 검색(ytsearch) + 개별 영상 메타 추출이 되면 VIABLE
- tiktok : 해시태그 페이지 추출이 되면 VIABLE
러너 IP 차단은 보통 'Sign in to confirm you're not a bot' / HTTP 429·403으로 드러난다.

읽는 법: 잡 로그의 'VERDICT:' 줄과 각 테스트의 [OK]/[FAIL] 을 본다. 항상 exit 0(정보성).
"""
import json
import sys

BOT_MARKERS = ("sign in to confirm", "not a bot", "http error 429",
               "http error 403", "captcha", "too many requests", "rate")


def classify(detail: str) -> str:
    d = (detail or "").lower()
    if any(m in d for m in BOT_MARKERS):
        return "IP차단추정(봇체크/429/403)"
    return "기타오류"


def main() -> int:
    try:
        import yt_dlp
    except Exception as e:
        print(f"[FATAL] yt-dlp 임포트 실패: {e}")
        print("VERDICT: youtube=UNKNOWN tiktok=UNKNOWN (yt-dlp 미설치)")
        return 0

    print(f"[env] yt-dlp {getattr(yt_dlp.version, '__version__', '?')}")
    results = []

    def run(name, target, flat, search):
        r = {"name": name, "target": target, "ok": False, "detail": ""}
        opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                "noplaylist": True, "socket_timeout": 30, "retries": 2,
                "extract_flat": bool(flat)}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target, download=False)
            if search:
                ents = [e for e in ((info or {}).get("entries") or []) if e]
                r["ok"] = len(ents) > 0
                r["detail"] = f"{len(ents)}건" + (f" · 첫제목={str(ents[0].get('title',''))[:34]}" if ents else "")
                r["_first_id"] = ents[0].get("id") if ents else None
            else:
                r["ok"] = bool(info)
                r["detail"] = f"title={str((info or {}).get('title',''))[:34]} · views={(info or {}).get('view_count')}"
        except Exception as e:
            r["detail"] = f"{type(e).__name__}: {str(e)[:180]}"
            r["cls"] = classify(r["detail"])
        results.append(r)
        mark = "OK  " if r["ok"] else "FAIL"
        extra = "" if r["ok"] else f"  <{r.get('cls','')}>"
        print(f"  [{mark}] {name}: {r['detail']}{extra}")
        return r

    print("── 유튜브 ──")
    yt_search = run("youtube_search", "ytsearch3:쇼핑 꿀템 리뷰", flat=True, search=True)
    yt_full = {"ok": False}
    if yt_search.get("_first_id"):
        url = f"https://www.youtube.com/watch?v={yt_search['_first_id']}"
        yt_full = run("youtube_full_meta", url, flat=False, search=False)

    print("── 틱톡 ──")
    tk = run("tiktok_tag", "https://www.tiktok.com/tag/꿀템", flat=True, search=True)

    yt_viable = bool(yt_search.get("ok") and yt_full.get("ok"))
    tk_viable = bool(tk.get("ok"))
    verdict = f"VERDICT: youtube={'VIABLE' if yt_viable else 'BLOCKED'} tiktok={'VIABLE' if tk_viable else 'BLOCKED'}"
    print()
    print(verdict)
    print("SUMMARY_JSON: " + json.dumps(
        {"youtube_viable": yt_viable, "tiktok_viable": tk_viable, "tests": results},
        ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
