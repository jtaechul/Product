#!/usr/bin/env bash
# 10분마다 GitHub 최신 코드를 받아 자동 반영 + 봇(실거래) 자동 구성 (GCP VM 용).
#
# 동작:
#   0) git 소유권 허용(root 가 사용자 저장소에서 git 쓰도록) — 'dubious ownership' 방지
#   1) 두 봇을 실거래(--live)로 보장: swing-bot 에 --live 추가, majors-bot(BTC·ETH) 설치/갱신
#   2) 원격 최신을 받아(reset --hard) 코드 반영, 변경 시 봇 재시작
#
# systemd timer(auto-update.timer)가 10분 간격으로 호출. .env(API키)는 git 비추적이라 보존됨.
set -uo pipefail   # -e 제외: 일부 단계 실패해도 전체가 죽지 않게(아래서 개별 처리)

REPO_DIR="${REPO_DIR:-/home/botuser/Product}"
SERVICES="${SERVICES:-swing-bot majors-bot}"

cd "$REPO_DIR" || exit 1
# root 가 사용자 소유 저장소에서 git 을 쓸 때 'dubious ownership' 오류 방지
git config --global --add safe.directory "$REPO_DIR" 2>/dev/null || true

# --- swing-bot 을 실거래(--live)로: ExecStart 에 --live 없으면 추가(금액 등은 그대로) ---
ensure_swing_live() {
    local S=/etc/systemd/system/swing-bot.service
    [ -f "$S" ] || return 0
    grep -q '^ExecStart=.*scripts.swing_trade' "$S" || return 0
    if grep -q '^ExecStart=.*--live' "$S"; then return 0; fi   # 이미 실거래
    sed -i 's#^\(ExecStart=.*scripts\.swing_trade.*\)$#\1 --live#' "$S"
    systemctl daemon-reload
    if systemctl restart swing-bot; then
        echo "  ✅ swing-bot 실거래(--live) 전환"
    else
        echo "  ⚠️ swing-bot 재시작 실패 — API키(주문권한) 확인 필요"
    fi
}

# --- majors-bot 을 swing-bot 설정 본떠 설치/갱신 (실거래, 총 10만원=BTC·ETH 각 5만) ---
ensure_majors_bot() {
    local SWING=/etc/systemd/system/swing-bot.service
    local MAJORS=/etc/systemd/system/majors-bot.service
    [ -f "$SWING" ] || return 0
    local PY
    PY="$(grep -oE '/[^ ]*/\.venv/bin/python' "$SWING" | head -1)"
    [ -z "$PY" ] && return 0
    local DESIRED="ExecStart=$PY -m scripts.majors_trade --invest 100000 --live"
    # 이미 원하는 설정이면 그대로 둠(매 사이클 불필요 재시작 방지)
    if [ -f "$MAJORS" ] && grep -qF "$DESIRED" "$MAJORS"; then return 0; fi
    sed -e 's/^Description=.*/Description=Upbit Majors (BTC-ETH) Trend Bot/' \
        -e "s#^ExecStart=.*#$DESIRED#" \
        -e 's#bot\.log#majors.log#g' \
        "$SWING" > "$MAJORS"
    systemctl daemon-reload
    systemctl enable majors-bot >/dev/null 2>&1 || true
    if systemctl restart majors-bot; then
        echo "  ✅ majors-bot 실거래 설치/갱신 (--invest 100000 --live)"
    else
        echo "  ⚠️ majors-bot 시작 실패 — API키(주문권한) 확인 필요"
    fi
}

ensure_swing_live
ensure_majors_bot

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || exit 0
git fetch --quiet origin "$BRANCH" || exit 0

LOCAL="$(git rev-parse HEAD 2>/dev/null)"
REMOTE="$(git rev-parse "origin/$BRANCH" 2>/dev/null)"

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0   # 코드 변경 없음 → 종료(봇 구성 점검은 위에서 이미 함)
fi

echo "[$(date '+%F %T %Z')] 새 코드 감지: ${LOCAL:0:7} → ${REMOTE:0:7} (브랜치 $BRANCH)"
git reset --hard "origin/$BRANCH"

# 의존성이 바뀌었을 수 있으니 가볍게 갱신 (venv 가 있으면)
if [ -x "$REPO_DIR/upbit-trader/.venv/bin/pip" ]; then
    "$REPO_DIR/upbit-trader/.venv/bin/pip" install -q -r "$REPO_DIR/upbit-trader/requirements.txt" || true
fi

for svc in $SERVICES; do
    if systemctl list-unit-files | grep -q "^${svc}.service"; then
        echo "  → ${svc} 재시작"
        systemctl restart "$svc" || true
    fi
done
echo "  ✅ 반영 완료"
