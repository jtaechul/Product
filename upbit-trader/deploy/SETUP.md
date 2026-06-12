# 무료 클라우드에서 스윙 봇 24시간 돌리기 (GCP Always Free)

로컬 PC를 끄지 않고, **구글 클라우드 무료 VM**에서 봇을 항상 가동하는 가이드입니다.
스윙 전략이라 서버 위치(미국)와 업비트(서울) 간 지연은 문제가 안 됩니다.

> 💡 왜 GCP Always Free? `e2-micro` 1대가 미국 리전(us-west1/us-central1/us-east1)에서
> **영구 무료**이고, 켜두면 회수되지 않아 안정적입니다. 이 봇은 매우 가벼워 1GB로 충분.
> (대안: Oracle Cloud Always Free ARM은 더 강력하지만 가입 시 용량 부족이 잦습니다.)

---

## 0. 준비물
- 구글 계정 + 신용카드(무료 등급 확인용, 과금 안 됨)
- 업비트 API 키 (자산조회+주문 권한만, **출금 권한 OFF**)
- (선택) 텔레그램 봇 토큰 + chat id — 휴대폰 알림용

## 1. 무료 VM 생성 (GCP 콘솔)
1. https://console.cloud.google.com → 프로젝트 생성
2. Compute Engine → VM 인스턴스 → **인스턴스 만들기**
3. 설정 (무료 등급 조건 정확히 맞추기):
   - 리전: **us-west1** (또는 us-central1 / us-east1)
   - 머신 유형: **e2-micro**
   - 부팅 디스크: **표준 영구 디스크 30GB**, Ubuntu 22.04 LTS
   - 나머지 기본값
4. 만들기 → 목록에서 **SSH** 버튼으로 접속

## 2. 봇 설치 (VM 안에서 복붙)
```bash
sudo apt update && sudo apt install -y python3-venv git
git clone https://github.com/jtaechul/Product.git
cd Product/upbit-trader
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 3. 키 설정
```bash
cp .env.example .env
nano .env          # 업비트 키 + (선택)텔레그램 토큰 입력 후 저장
chmod 600 .env     # 키 파일 권한 잠그기
```

## 4. 먼저 모의로 검증 (실주문 없음)
```bash
.venv/bin/python -m scripts.swing_trade --max-positions 3 --invest 100000
```
- 텔레그램을 설정했다면 시작 메시지 + 1시간마다 하트비트가 옵니다.
- 며칠 돌려 스캔/매수/매도 로그가 합리적인지 확인하세요. (Ctrl+C 로 종료)

## 5. 자동 재시작 서비스 등록 (systemd) — 안정성의 핵심
```bash
# 서비스 파일의 botuser/경로를 본인 환경에 맞게 수정
sudo cp deploy/swing-bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/swing-bot.service   # User=, 경로 확인
sudo systemctl daemon-reload
sudo systemctl enable --now swing-bot     # 부팅 시 자동 시작 + 지금 시작
sudo systemctl status swing-bot           # 상태 확인
tail -f ~/Product/upbit-trader/bot.log    # 실시간 로그
```
이제 VM이 재부팅되거나 봇이 죽어도 `Restart=always`로 자동 부활합니다.

## 6. 실거래 전환 (충분히 모의 검증 후, 소액으로)
```bash
sudo nano /etc/systemd/system/swing-bot.service
#   ExecStart 줄 끝에  --live  추가, --invest 를 소액으로
sudo systemctl daemon-reload && sudo systemctl restart swing-bot
```

---

## 안전 체크리스트
- [ ] 업비트 키 **출금 권한 OFF**, 허용 IP에 VM 외부 IP 등록
- [ ] `.env` 는 `chmod 600`, 절대 git 커밋 금지(이미 .gitignore 처리됨)
- [ ] 텔레그램 하트비트로 "봇 생존" 확인 — 신호 끊기면 VM 점검
- [ ] **모의로 며칠 검증 후** 소액 실거래부터. 백테스트 ≠ 실제 체결
- [ ] 무료 등급 한도(디스크 30GB, 리전) 준수 — 초과 시 과금

## 자주 쓰는 명령
```bash
sudo systemctl stop swing-bot      # 중지
sudo systemctl restart swing-bot   # 재시작
sudo systemctl disable swing-bot   # 자동시작 해제
journalctl -u swing-bot -f         # systemd 로그
```
