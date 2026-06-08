# Upbit 자동매매 (Upbit Auto Trader)

Upbit Open API를 활용한 가상화폐 자동매매 프로젝트입니다.
**안전 우선** 원칙으로, 돈을 거는 단계는 가장 마지막에 추가합니다.

> ⚠️ **경고**: 자동매매는 원금 손실 위험이 있습니다. 이 코드는 교육/연구 목적의
> 출발점이며, 실거래에 사용하기 전 충분한 백테스트와 소액 검증을 거치세요.
> 작성자는 이 코드 사용으로 인한 어떠한 손실에도 책임지지 않습니다.

## 개발 로드맵

- [x] **1단계: 시세 조회** — 인증 없이 마켓/캔들/현재가/호가 가져오기  ← *현재 여기*
- [ ] 2단계: 전략 정의 (이동평균 교차 / RSI / 변동성 돌파 등)
- [ ] 3단계: 백테스트 (과거 데이터로 전략 검증)
- [ ] 4단계: 모의매매 (실주문 없이 가상 체결 시뮬레이션)
- [ ] 5단계: 소액 실거래 (JWT 인증 + 주문 API)
- [ ] 6단계: 리스크 관리 + 모니터링/알림

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
