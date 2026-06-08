"""실시간 자동매매 현황 웹앱 (Streamlit).

심플한 웹 대시보드로, 선택한 전략의 현재 신호와 모의 투자 현황을 실시간으로 보여줍니다.
일정 간격으로 자동 새로고침되며, 매번 최신 시세를 받아 다시 계산합니다.

실행 (본인 PC):
    cd upbit-trader
    pip install -r requirements.txt
    streamlit run app/dashboard_app.py

  → 브라우저가 자동으로 http://localhost:8501 을 엽니다.

※ 인터넷이 막힌 환경에서는 자동으로 '데모 모드'(합성 데이터)로 동작합니다.
※ 실제 주문은 하지 않는 모의(paper) 현황입니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.paper_trader import run_paper_trading  # noqa: E402
from src.risk import apply_risk_management  # noqa: E402
from src.sample_data import generate_synthetic_ohlcv, load_csv  # noqa: E402
from src.strategies import (  # noqa: E402
    bollinger_bands,
    ma_crossover,
    macd,
    rsi_strategy,
    volatility_breakout,
)
from src.upbit_quotation import UpbitQuotation, candles_to_dataframe  # noqa: E402

STRATEGIES = {
    "변동성 돌파": volatility_breakout,
    "볼린저밴드": bollinger_bands,
    "RSI": rsi_strategy,
    "이동평균 교차": ma_crossover,
    "MACD": macd,
}


def load_live(market: str, count: int = 200):
    """실시간 시세(일봉)를 받아오되, 막히면 합성 데이터로 폴백.

    백테스트 검증과 동일하게 일봉을 사용합니다.
    """
    try:
        q = UpbitQuotation()
        candles = q.get_candles_days(market, count=count)
        df = candles_to_dataframe(candles)
        if len(df) > 0:
            return df, "live"
    except Exception:
        pass
    return generate_synthetic_ohlcv(days=count), "demo"


st.set_page_config(page_title="Upbit 자동매매 현황", page_icon="📈", layout="wide")

# 사이드바 설정
st.sidebar.header("⚙️ 설정")
source = st.sidebar.radio("데이터 소스", ["실시간 시세", "CSV 파일"])
market = st.sidebar.text_input("마켓", "KRW-BTC")
csv_path = st.sidebar.text_input("CSV 경로", "data/btc.csv")
strategy_name = st.sidebar.selectbox("전략", list(STRATEGIES.keys()))
cash = st.sidebar.number_input("시작 자금(원)", min_value=10_000, value=1_000_000, step=100_000)

st.sidebar.markdown("**리스크 관리** (0 = 미적용)")
sl = st.sidebar.number_input("손절 %", min_value=0.0, value=0.0, step=1.0) / 100 or None
tp = st.sidebar.number_input("익절 %", min_value=0.0, value=0.0, step=1.0) / 100 or None

refresh = st.sidebar.slider("자동 새로고침(초)", 5, 60, 10)
st.sidebar.caption(f"{refresh}초마다 자동 새로고침됩니다.")

# 자동 새로고침 (meta refresh)
st.markdown(
    f'<meta http-equiv="refresh" content="{refresh}">', unsafe_allow_html=True
)

st.title("📈 Upbit 자동매매 실시간 현황")

# 데이터 로딩
status = "demo"
if source == "CSV 파일":
    try:
        df = load_csv(csv_path)
        status = "csv"
    except Exception as exc:
        st.error(f"CSV 로드 실패: {exc}")
        df, status = generate_synthetic_ohlcv(days=200), "demo"
else:
    df, status = load_live(market)

if status == "live":
    st.success(f"🟢 실시간 데이터 연결됨 — {market} (일봉)")
elif status == "csv":
    st.info(f"📄 CSV 데이터 — {csv_path} ({len(df)}행, "
            f"{df['datetime'].iloc[0].date()} ~ {df['datetime'].iloc[-1].date()})")
else:
    st.warning("🟡 데모 모드 — 실시간 데이터에 연결되지 않아 합성 데이터를 사용합니다.")

# 전략 계산 (+ 손절/익절) + 모의매매 현황
strategy_fn = STRATEGIES[strategy_name]
positions = strategy_fn(df)
if sl or tp:
    positions = apply_risk_management(df, positions, sl, tp)
    strategy_for_paper = lambda d: apply_risk_management(d, strategy_fn(d), sl, tp)  # noqa: E731
else:
    strategy_for_paper = strategy_fn
account = run_paper_trading(df, strategy_for_paper, initial_cash=cash)

current_price = float(df["close"].iloc[-1])
holding = positions.iloc[-1] == 1
final_value = account.value(current_price)
profit = final_value - cash
profit_pct = profit / cash * 100

# 상단 지표 카드
c1, c2, c3, c4 = st.columns(4)
c1.metric("현재가", f"{current_price:,.0f} 원")
c2.metric("현재 신호", "🟢 보유(매수)" if holding else "⚪ 관망(현금)")
c3.metric("모의 평가자산", f"{final_value:,.0f} 원", f"{profit_pct:+.1f}%")
c4.metric("누적 매매", f"{len(account.trades)} 회")

# 가격 차트
st.subheader(f"{market} 가격 추이 — {strategy_name}")
chart_df = df.set_index("datetime")[["close"]].rename(columns={"close": "가격"})
st.line_chart(chart_df, height=320)

# 최근 거래 일지
st.subheader("최근 모의 거래")
if account.trades:
    rows = [
        {
            "시각": t.datetime.strftime("%Y-%m-%d %H:%M"),
            "구분": "매수" if t.action == "BUY" else "매도",
            "체결가": f"{t.price:,.0f}",
            "거래후 총자산": f"{t.value_after:,.0f}",
        }
        for t in reversed(account.trades[-15:])
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info("아직 매매 신호가 발생하지 않았습니다.")

st.caption("⚠️ 모의(paper) 현황입니다. 실제 주문은 이뤄지지 않습니다. "
           "데모 데이터일 경우 실제 수익을 의미하지 않습니다.")
