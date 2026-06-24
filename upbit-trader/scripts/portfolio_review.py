#!/usr/bin/env python3
"""포트폴리오 리뷰 — 상세 대시보드(HTML) 생성 + 국면별 비중조정 '제안'(텔레그램 승인 버튼).

하는 일(주기 실행 또는 수동):
  1) BTC 일봉으로 시장 국면(강세/중립/약세) 판별
  2) 전체 평가자산·보유코인·3봇 현황을 모아 상세 HTML 대시보드(아티팩트) 생성 → 텔레그램 전송
  3) 국면 권장비중이 현재 비중과 다르면 → 텔레그램에 '✅승인 / ❌거절' 버튼으로 제안
     (승인 시 notifier 가 allocation 비중을 갱신 → 봇들이 다음 점검부터 반영)

실행: python -m scripts.portfolio_review        (systemd portfolio-review.timer 가 매일 호출)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import allocation, notifier, regime  # noqa: E402
from src.timeutil import now_kst  # noqa: E402
from src.upbit_quotation import UpbitQuotation, candles_to_dataframe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "portfolio.html"
BOT_LABEL = {"majors": "대형코인", "swing": "잠수함"}


def gather():
    q = UpbitQuotation()
    btc = candles_to_dataframe(q.get_candles_days("KRW-BTC", count=210))
    reg = regime.detect_regime(btc)

    # 실제 잔고(키 있으면)
    holdings, total_krw = [], 0.0
    try:
        from src import config
        if config.has_api_keys():
            from src.upbit_exchange import UpbitExchange
            ex = UpbitExchange()
            accs = ex.get_accounts()
            coins = [f"KRW-{a['currency']}" for a in accs
                     if a.get("currency") != "KRW" and a.get("unit_currency", "KRW") == "KRW"
                     and (float(a.get("balance", 0) or 0) + float(a.get("locked", 0) or 0)) > 0]
            prices = {}
            if coins:
                prices = {t["market"]: float(t["trade_price"]) for t in q.get_ticker(coins)}
            for a in accs:
                cur = a.get("currency", "")
                if a.get("unit_currency", "KRW") != "KRW":
                    continue
                vol = float(a.get("balance", 0) or 0) + float(a.get("locked", 0) or 0)
                if cur == "KRW":
                    total_krw += vol
                    continue
                if vol <= 0:
                    continue
                avg = float(a.get("avg_buy_price", 0) or 0)
                px = prices.get(f"KRW-{cur}", avg)
                val = vol * px
                total_krw += val
                holdings.append({"coin": cur, "vol": vol, "avg": avg, "price": px,
                                 "value": val,
                                 "pl_pct": (px / avg - 1) * 100 if avg > 0 else 0.0,
                                 "pl_krw": (px - avg) * vol if avg > 0 else 0.0})
    except Exception:
        pass

    # 봇별 상태파일을 모은다. 단, notifier 와 '같은 화이트리스트'를 적용해
    # 운용 중단/폐기된 봇(예: 3_고위험, 1_잠수함)의 현황이 대시보드(→텔레그램)로
    # 새지 않게 한다. (이 글롭은 notifier._read_all_statuses 와 별개 경로라 반드시 필터)
    bots = []
    state_dir = ROOT / ".botstate"
    if state_dir.exists():
        for f in sorted(state_dir.glob("status_*.txt")):
            bot_name = f.stem[len("status_"):]
            if not notifier.status_allowed(bot_name):
                continue
            try:
                txt = f.read_text(encoding="utf-8").strip()
                if txt:
                    bots.append(txt)
            except Exception:
                pass

    return {"regime": reg, "total": total_krw, "holdings": holdings,
            "weights_cur": allocation.current_weights(), "bots": bots}


def build_html(ctx: dict, public: bool = False) -> str:
    """대시보드 HTML. public=True 면 민감정보(총자산 금액·보유수량·평단)를 가린다."""
    reg = ctx["regime"]
    total = ctx["total"]
    cur = ctx["weights_cur"]
    prop = reg["weights"]
    cash_cur = max(0.0, 1 - sum(cur.values()))
    cash_prop = reg["cash"]
    total_str = "비공개 🔒" if public else f"{total:,.0f}원"
    amt = (lambda v: "비공개") if public else (lambda v: f"{v:,.0f}원")

    def bar(pct, color):
        return (f"<div style='background:#eee;border-radius:6px;height:18px;width:160px;"
                f"display:inline-block;vertical-align:middle'>"
                f"<div style='background:{color};height:18px;border-radius:6px;"
                f"width:{min(100,pct*100):.0f}%'></div></div>")

    rows = ""
    for k in ("majors", "swing"):
        rows += (f"<tr><td>{BOT_LABEL[k]}</td>"
                 f"<td>{bar(cur.get(k,0),'#4a90d9')} {cur.get(k,0)*100:.0f}%</td>"
                 f"<td>{bar(prop.get(k,0),'#e09b3d')} {prop.get(k,0)*100:.0f}%</td>"
                 f"<td>{amt(total*prop.get(k,0))}</td></tr>")
    rows += (f"<tr><td>현금</td><td>{bar(cash_cur,'#9aa')} {cash_cur*100:.0f}%</td>"
             f"<td>{bar(cash_prop,'#9aa')} {cash_prop*100:.0f}%</td>"
             f"<td>{amt(total*cash_prop)}</td></tr>")

    hrows = ""
    for h in ctx["holdings"]:
        col = "#1a8" if h["pl_pct"] >= 0 else "#d33"
        if public:  # 공개본: 수량·평단·평가액 숨김, 손익%만
            hrows += (f"<tr><td><b>{h['coin']}</b></td><td>비공개</td><td>비공개</td>"
                      f"<td>{h['price']:,.0f}</td><td>비공개</td>"
                      f"<td style='color:{col}'>{h['pl_pct']:+.1f}%</td></tr>")
        else:
            hrows += (f"<tr><td><b>{h['coin']}</b></td><td>{h['vol']:.6f}</td>"
                      f"<td>{h['avg']:,.0f}</td><td>{h['price']:,.0f}</td>"
                      f"<td>{h['value']:,.0f}원</td>"
                      f"<td style='color:{col}'>{h['pl_pct']:+.1f}% ({h['pl_krw']:+,.0f}원)</td></tr>")
    if not hrows:
        hrows = "<tr><td colspan=6>보유 코인 없음(또는 키 미설정)</td></tr>"

    if public:   # 공개본: 봇 상태 텍스트엔 금액이 섞여 있어 제외
        botblocks = "<p style='color:#888'>봇별 상세(금액 포함)는 텔레그램에서만 확인할 수 있어요.</p>"
    else:
        botblocks = "".join(
            f"<pre style='background:#f7f7f9;padding:10px;border-radius:8px;white-space:pre-wrap'>"
            f"{b}</pre>" for b in ctx["bots"]) or "<p>봇 상태 파일 없음</p>"

    ma50 = f"{reg['ma50']:,.0f}" if reg["ma50"] else "-"
    ma200 = f"{reg['ma200']:,.0f}" if reg["ma200"] else "-"
    refresh = "<meta http-equiv=refresh content=60>" if public else ""
    return f"""<!doctype html><html lang=ko><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>{refresh}
<title>코인 포트폴리오 대시보드</title>
<body style='font-family:-apple-system,system-ui,sans-serif;max-width:680px;margin:0 auto;
padding:16px;color:#222;background:#fafafb'>
<h2>🪙 코인 포트폴리오 대시보드</h2>
<p style='color:#888'>갱신: {now_kst():%Y-%m-%d %H:%M} (한국시간)</p>

<div style='background:#fff;border:1px solid #eee;border-radius:12px;padding:14px;margin:10px 0'>
<h3>📈 시장 국면: {reg['label']}</h3>
<p>BTC 현재가 {reg['price']:,.0f} · 50일선 {ma50} · 200일선 {ma200} · 변동성(연) {reg['vol']*100:.0f}%</p>
</div>

<div style='background:#fff;border:1px solid #eee;border-radius:12px;padding:14px;margin:10px 0'>
<h3>💰 총 평가자산: {total_str}</h3>
<table style='width:100%;border-collapse:collapse' cellpadding=6>
<tr style='text-align:left;color:#888'><th>구분</th><th>현재 비중</th><th>제안 비중</th><th>제안 금액</th></tr>
{rows}
</table>
<p style='color:#888;font-size:13px'>※ 제안 비중은 시장 국면 규칙 기반. 적용은 텔레그램 ✅승인 버튼으로.</p>
</div>

<div style='background:#fff;border:1px solid #eee;border-radius:12px;padding:14px;margin:10px 0'>
<h3>📦 보유 코인</h3>
<table style='width:100%;border-collapse:collapse' cellpadding=6>
<tr style='text-align:left;color:#888'><th>코인</th><th>수량</th><th>평단</th><th>현재가</th><th>평가액</th><th>손익</th></tr>
{hrows}
</table>
</div>

<div style='background:#fff;border:1px solid #eee;border-radius:12px;padding:14px;margin:10px 0'>
<h3>🤖 봇별 현황</h3>
{botblocks}
</div>
<p style='color:#aaa;font-size:12px'>참고용 정보이며 투자 조언이 아닙니다.</p>
</body></html>"""


def maybe_propose(ctx: dict) -> None:
    cur = ctx["weights_cur"]
    prop = ctx["regime"]["weights"]
    keys = set(cur) | set(prop)
    if not any(abs(prop.get(k, 0) - cur.get(k, 0)) > 0.02 for k in keys):
        return  # 현재 비중과 사실상 같음 → 제안 안 함
    allocation.write_pending({"weights": prop, "regime": ctx["regime"]["label"],
                              "ts": time.time()})
    cash = ctx["regime"]["cash"]
    msg = (f"⚖️ <b>비중 조정 제안</b>\n"
           f"시장 국면: <b>{ctx['regime']['label']}</b>\n"
           f"현재 → 제안\n"
           f"• 대형 {cur.get('majors',0)*100:.0f}% → {prop.get('majors',0)*100:.0f}%\n"
           f"• 잠수 {cur.get('swing',0)*100:.0f}% → {prop.get('swing',0)*100:.0f}%\n"
           f"• 현금 → {cash*100:.0f}%\n"
           f"승인하면 봇들이 이 비중으로 운용합니다.")
    notifier.send_buttons(msg, [[("✅ 승인", "approve_weights"),
                                 ("❌ 거절", "reject_weights")]])


PUBLIC_PATH = "upbit-trader/live/dashboard.html"   # GitHub Pages 게시 경로


def publish_via_git(html_content: str, path: str = "upbit-trader/live/dashboard.html") -> tuple[bool, str]:
    """git으로 HTML을 커밋/푸시. (GitHub API 토큰 문제 우회)"""
    import subprocess
    try:
        filepath = ROOT.parent / path
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(html_content, encoding="utf-8")

        result = subprocess.run(["git", "add", "-f", path], cwd=str(ROOT.parent),
                              capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return False, f"git add failed: {result.stderr}"

        result = subprocess.run(["git", "commit", "-m", f"dashboard {now_kst():%Y-%m-%d %H:%M}"],
                              cwd=str(ROOT.parent), capture_output=True, text=True, timeout=10)
        if result.returncode not in (0, 1):
            return False, f"git commit failed: {result.stderr}"

        result = subprocess.run(["git", "push", "-q"], cwd=str(ROOT.parent),
                              capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return False, f"git push failed: {result.stderr}"

        return True, f"https://raw.githubusercontent.com/jtaechul/Product/main/{path}"
    except Exception as e:
        return False, str(e)


def main() -> None:
    quiet = "--quiet" in sys.argv
    ctx = gather()
    OUT.write_text(build_html(ctx, public=False), encoding="utf-8")
    print(f"대시보드 생성: {OUT}")

    ok, info = publish_via_git(build_html(ctx, public=True), PUBLIC_PATH)
    if ok:
        print(f"공개 대시보드 게시: {info}")
    else:
        print(f"공개 게시 건너뜀: {info}")

    if not quiet:
        notifier.send_document(str(OUT),
                               caption=f"🪙 포트폴리오 대시보드 ({now_kst():%m-%d %H:%M})")
        if ok:
            notifier.send(f"🌐 라이브 대시보드: {info}")
        maybe_propose(ctx)


if __name__ == "__main__":
    main()
