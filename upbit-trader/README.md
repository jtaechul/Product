# Upbit 자동매매 (Upbit Auto Trader)

Upbit Open API를 활용한 가상화폐 자동매매 프로젝트입니다.
**안전 우선** 원칙으로, 돈을 거는 단계는 가장 마지막에 추가합니다.

> ⚠️ **경고**: 자동매매는 원금 손실 위험이 있습니다. 이 코드는 교육/연구 목적의
> 출발점이며, 실거래에 사용하기 전 충분한 백테스트와 소액 검증을 거치세요.
> 작성자는 이 코드 사용으로 인한 어떠한 손실에도 책임지지 않습니다.

## 개발 로드맵

- [x] **1단계: 시세 조회** — 인증 없이 마켓/캔들/현재가/호가 가져오기
- [x] **2단계: 전략** — 이동평균 교차 / RSI / 변동성 돌파 / 볼린저밴드 / MACD (5종)
- [x] **3단계: 백테스트** — 과거 데이터로 전략 검증 (+파라미터 최적화, 학습/검증 분할)
- [x] **4단계: 모의매매** — 실주문 없이 가상 계좌로 거래 일지 기록
- [x] **리스크 관리** — 손절/익절(stop-loss/take-profit)
- [x] **대시보드** — 결과를 차트 HTML 로 시각화
- [x] **5단계: 실거래 봇** — JWT 인증 + 시장가 주문, dry-run 기본 + 투자금 상한
- [x] **잠수함 급등 매매** — 스캐너(5분봉) + 1분봉 추적기 + 통합 자동 봇
- [ ] 6단계: 실시간 모니터링/알림 (텔레그램 등)

## 잠수함 알트코인 급등 매매

조용히 가라앉아(축적) 있다가 거래량이 터지며 급등하는 알트코인을 포착해
빠르게 진입하고, 트레일링 스탑으로 빠르게 청산하는 별도 시스템입니다.

```bash
# 1) 스캐너: 전체 KRW 마켓을 5분봉으로 훑어 급등 후보 순위표 (조회만, 안전)
python -m scripts.scan_pumps --watch 60

# 2) 추적기: 포착한 코인 1개를 1분봉/현재가로 정밀 추적 매매 (모의 기본)
python -m scripts.track_coin --market KRW-XYZ

# 3) 통합 봇: 스캐너(백그라운드) + 다종목 추적을 하나로 (모의 기본)
python -m scripts.auto_trade --max-positions 3 --invest 6000
python -m scripts.auto_trade --invest 6000 --live   # 소액 실거래

# 4) 백테스트: 합성 멀티코인(진짜/가짜 펌프 혼합)에 전략 재생 → 성적
python -m scripts.backtest_pumps --coins 36 --days 4
python -m scripts.backtest_pumps --trail 2.5 --stop 4 --arm 1.5  # 파라미터 실험
```

**조기손절(early-cut)**: 진입 후 5분 내 상승 모멘텀이 살아나지 못하면 작은
손실로 빠르게 탈출 — 가짜 펌프(불 트랩)에 물렸을 때 손절폭까지 버티지 않습니다.
(백테스트상 손익비 1.31→1.64 개선)

**수익↑/손실↓ 장치**: 손절 하한 + 트레일링 스탑 + 본전 스탑(수익권 반납 차단)
+ 단계별 트레일링(수익 클수록 좁게) + 일일 손실 한도 + 재진입 쿨다운.
보유 코인은 캔들이 아닌 **현재가 일괄 조회**로 빠르게(기본 2초) 감시합니다.

> ⚠️ 급등 추격은 가장 위험합니다. 신호가 잡힐 땐 이미 오른 경우가 많고,
> 잠수함 코인은 거래량이 적어 슬리피지가 큽니다. 반드시 모의로 충분히
> 검증한 뒤 소액으로만 실거래하세요.

## 주요 스크립트

```bash
python scripts/fetch_market_data.py KRW-BTC   # 시세 조회 (네트워크 필요)
python scripts/check_balance.py               # 내 잔고 (API 키 + IP 등록 필요)
python scripts/run_backtest.py                # 전략 성적 비교
python scripts/run_backtest.py --stop-loss 0.05 --take-profit 0.15  # 손절/익절 적용
python scripts/optimize.py                    # 전략별 좋은 파라미터 탐색
python scripts/validate.py                    # 학습/검증 분할로 과최적화 점검
python scripts/paper_trade.py --strategy bb   # 모의매매 거래 일지
python scripts/make_dashboard.py              # dashboard.html 생성 → 브라우저로 열기
python -m streamlit run app/dashboard_app.py  # 실시간 웹 대시보드
python -m scripts.live_trade --strategy vb              # 자동매매 봇 (모의/dry-run)
python -m scripts.live_trade --strategy vb --max-invest 6000 --live  # 실거래(소액)
```

위 백테스트/최적화/검증/모의매매/대시보드는 **API 키 없이** 합성 데이터로 동작하며,
`--csv 파일.csv` 로 실제 OHLCV 데이터를 넣으면 그대로 실데이터 검증이 됩니다.

## 빠른 시작

```bash
cd upbit-trader
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# KRW-BTC 현재가 / 호가 / 일봉 출력
python scripts/fetch_market_data.py KRW-BTC
```

인증이 필요 없는 **시세(Quotation) API**만 사용하므로 API 키 없이 바로 실행됩니다.

## 프로젝트 구조

```
upbit-trader/
├── README.md
├── requirements.txt
├── .gitignore
├── .env.example              # API 키 템플릿 (실제 키는 .env 에, 절대 커밋 금지)
├── src/
│   ├── __init__.py
│   ├── config.py             # 환경변수/설정 로딩
│   └── upbit_quotation.py    # 시세 조회 클라이언트 (인증 불필요)
└── scripts/
    └── fetch_market_data.py  # 시세 조회 데모 CLI
```

## Upbit Open API 메모

- 시세 API: 인증 불필요. `https://api.upbit.com/v1/...`
- 거래 API: JWT 인증 필요 (Access Key / Secret Key). 5단계에서 추가 예정.
- API 키 발급: **PC 웹(upbit.com) 전용** (모바일 앱에는 메뉴 없음). 로그인 →
  마이페이지 → Open API 관리(`https://upbit.com/mypage/open_api_management`) →
  권한 선택 → **허용 IP 등록** → 본인 인증 → Access/Secret key 발급.
  - 사전 조건: **고객확인(KYC) + 2채널 인증(2FA)** 완료해야 발급 가능.
  - **Secret key 는 최초 발급 화면에서 단 한 번만** 표시되므로 즉시 안전하게 보관.
- 자동매매에는 **자산조회 + 주문** 권한만. **출금 권한은 절대 켜지 마세요.**
- 호출 횟수 제한(rate limit)이 있으니 과도한 요청은 피하세요.
- 공식 문서: https://docs.upbit.com/
