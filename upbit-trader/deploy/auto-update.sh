#!/usr/bin/env bash
# GitHub 최신 코드를 받아 자동 반영 + 봇(실거래) 자동 구성 (GCP VM 용).
#
# 핵심: '배포된 커밋 != 봇이 실행 중인 커밋'이면 항상 봇을 재시작한다.
#       (수동 git pull 후 실행해도 새 코드가 확실히 반영되도록 — 마커 파일로 추적)
set -uo pipefail

REPO_DIR="${REPO_DIR:-/home/botuser/Product}"
SERVICES="${SERVICES:-swing-bot majors-bot highrisk-bot}"
UPBIT="$REPO_DIR/upbit-trader"
MARKER="$UPBIT/.botstate/deployed_commit"

cd "$REPO_DIR" || exit 1
git config --global --add safe.directory "$REPO_DIR" 2>/dev/null || true

# ── 1) 최신 코드 받기 (원격이 앞서면 reset) ──────────────────────────────
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || exit 0
git fetch --quiet origin "$BRANCH" 2>/dev/null || true
LOCAL="$(git rev-parse HEAD 2>/dev/null)"
REMOTE="$(git rev-parse "origin/$BRANCH" 2>/dev/null)"
if [ -n "$REMOTE" ] && [ "$LOCAL" != "$REMOTE" ]; then
    echo "[$(date '+%F %T %Z')] 새 코드 수신: ${LOCAL:0:7} → ${REMOTE:0:7}"
    git reset --hard "origin/$BRANCH"
    if [ -x "$UPBIT/.venv/bin/pip" ]; then
        "$UPBIT/.venv/bin/pip" install -q -r "$UPBIT/requirements.txt" || true
    fi
fi

# ── 2) 봇 서비스 구성 보장 (실거래 전환 / 신규 봇·타이머 설치) ───────────
ensure_swing_live() {
    local S=/etc/systemd/system/swing-bot.service
    [ -f "$S" ] || return 0
    grep -q '^ExecStart=.*scripts.swing_trade' "$S" || return 0
    grep -q '^ExecStart=.*--live' "$S" && return 0
    sed -i 's#^\(ExecStart=.*scripts\.swing_trade.*\)$#\1 --live#' "$S"
    systemctl daemon-reload
    systemctl restart swing-bot || true
    echo "  ✅ swing-bot 실거래(--live) 전환"
}

ensure_clone_bot() {  # $1=서비스명 $2=Description $3=실행모듈+인자 $4=로그파일명
    local SWING=/etc/systemd/system/swing-bot.service
    local DST="/etc/systemd/system/$1.service"
    [ -f "$SWING" ] || return 0
    local PY
    PY="$(grep -oE '/[^ ]*/\.venv/bin/python' "$SWING" | head -1)"
    [ -z "$PY" ] && return 0
    local DESIRED="ExecStart=$PY -m $3"
    if [ -f "$DST" ] && grep -qF "$DESIRED" "$DST"; then return 0; fi
    sed -e "s/^Description=.*/Description=$2/" \
        -e "s#^ExecStart=.*#$DESIRED#" \
        -e "s#bot\.log#$4#g" \
        "$SWING" > "$DST"
    systemctl daemon-reload
    systemctl enable "$1" >/dev/null 2>&1 || true
    systemctl restart "$1" || true
    echo "  ✅ $1 설치/갱신·재시작"
}

# oneshot 서비스+타이머를 swing-bot 의 User/경로/venv 를 본떠 생성·설치
ensure_oneshot_timer() {  # $1=이름 $2=Description $3=실행모듈 $4=타이머파일명 $5=즉시1회(1/0)
    local SWING=/etc/systemd/system/swing-bot.service
    local RS="/etc/systemd/system/$1.service" RT="/etc/systemd/system/$1.timer"
    [ -f "$SWING" ] || return 0
    [ -f "$RT" ] && return 0
    local PY WD USERN ENVF
    PY="$(grep -oE '/[^ ]*/\.venv/bin/python' "$SWING" | head -1)"
    WD="$(grep '^WorkingDirectory=' "$SWING" | head -1 | cut -d= -f2-)"
    USERN="$(grep '^User=' "$SWING" | head -1 | cut -d= -f2-)"
    ENVF="$(grep '^EnvironmentFile=' "$SWING" | head -1 | cut -d= -f2-)"
    [ -z "$PY" ] && return 0
    {
        echo "[Unit]"; echo "Description=$2"; echo "After=network-online.target"
        echo "[Service]"; echo "Type=oneshot"
        [ -n "$USERN" ] && echo "User=$USERN"
        [ -n "$WD" ] && echo "WorkingDirectory=$WD"
        [ -n "$ENVF" ] && echo "EnvironmentFile=$ENVF"
        echo "ExecStart=$PY -m $3"
    } > "$RS"
    cp "$UPBIT/deploy/$4" "$RT" 2>/dev/null || return 0
    systemctl daemon-reload
    systemctl enable --now "$1.timer" >/dev/null 2>&1 || true
    [ "$5" = "1" ] && systemctl start "$1.service" >/dev/null 2>&1 || true
    echo "  ✅ $1.timer 설치"
}

ensure_swing_live
ensure_clone_bot "majors-bot"   "Upbit Majors (BTC-ETH) Trend Bot" \
    "scripts.majors_trade --invest 100000 --live" "majors.log"
ensure_clone_bot "highrisk-bot" "Upbit High-Risk Momentum Bot" \
    "scripts.highrisk_trade" "highrisk.log"          # 모의(--live 없음)
ensure_oneshot_timer "rebalance" "Upbit portfolio rebalance (50/30/20)" \
    "scripts.rebalance" "rebalance.timer" 1          # 설치 즉시 1회 배분
ensure_oneshot_timer "portfolio-review" "Upbit portfolio review (dashboard+proposal)" \
    "scripts.portfolio_review" "portfolio-review.timer" 1   # 설치 즉시 1회 대시보드 전송

# ── 3) 배포 커밋 != 실행 중 커밋 이면 모든 봇 재시작 (수동 pull 포함 확실 반영) ──
HEAD="$(git rev-parse HEAD 2>/dev/null)"
mkdir -p "$(dirname "$MARKER")" 2>/dev/null || true
if [ "$(cat "$MARKER" 2>/dev/null)" != "$HEAD" ]; then
    for svc in $SERVICES; do
        if systemctl list-unit-files | grep -q "^${svc}\.service"; then
            echo "  → ${svc} 재시작(새 코드 반영)"
            systemctl restart "$svc" || true
        fi
    done
    echo "$HEAD" > "$MARKER"
    echo "  ✅ 반영 완료 (${HEAD:0:7})"
fi
