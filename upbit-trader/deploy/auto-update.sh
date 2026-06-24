#!/usr/bin/env bash
# GitHub 최신 코드를 받아 자동 반영 + 봇(실거래) 자동 구성 (GCP VM 용).
#
# 핵심: '배포된 커밋 != 봇이 실행 중인 커밋'이면 항상 봇을 재시작한다.
#       (수동 git pull 후 실행해도 새 코드가 확실히 반영되도록 — 마커 파일로 추적)
set -uo pipefail

REPO_DIR="${REPO_DIR:-/home/botuser/Product}"
# 경로 자동보정: 기본 경로가 없으면 스크립트 위치(<repo>/upbit-trader/deploy/)에서 추정
if [ ! -d "$REPO_DIR" ]; then
    _guess="$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)"
    [ -n "$_guess" ] && REPO_DIR="$_guess"
fi
SERVICES="${SERVICES:-swing-bot majors-bot}"
# 고위험봇 영구 폐기: 서버에 '설치된' auto-update.service 가 옛 3봇 시절
# SERVICES(=...highrisk-bot)를 환경변수로 갖고 있어도, 재시작 대상에서 무조건 제외.
# (아래 ③ 재시작 루프가 highrisk-bot 을 절대 되살리지 못하게 하는 안전장치)
SERVICES="$(printf '%s\n' $SERVICES | grep -vx 'highrisk-bot' | tr '\n' ' ')"
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

# ── 2) 봇 서비스 구성 보장 (잠수함·고위험=모의 / 신규 봇·타이머 설치) ──────
# 검증 결과: 잠수함·고위험은 2019~2026 + ATR/부분익절 비교까지 모두 손실(과최적화).
# 실거래에선 손실만 누적(LAYER 등) → 검증 통과 전략(대형) 나올 때까지 '모의'로 강제.
ensure_swing_paper() {
    local S=/etc/systemd/system/swing-bot.service
    [ -f "$S" ] || return 0
    grep -q '^ExecStart=.*scripts.swing_trade' "$S" || return 0
    grep -q '^ExecStart=.*--live' "$S" || return 0   # 이미 모의면 끝
    sed -i '/scripts\.swing_trade/ s/ --live//g' "$S"
    systemctl daemon-reload
    systemctl restart swing-bot || true
    echo "  ✅ swing-bot 모의(paper) 전환 (--live 제거)"
}

# 고위험봇 영구 폐기(2019~2026 + ATR/부분익절 검증 전부 실패 → 삭제). 코드는 이미
# 리포에서 지웠지만, 서버에 '설치된' 서비스·실행 중 프로세스·잔존 상태파일은 그대로
# 남는다. 이걸 능동적으로 제거하지 않으면 옛 프로세스가 메모리상 옛 코드로 계속 돌며
# '투자 현황'을 텔레그램으로 보낸다. 매 실행마다 멱등(idempotent)하게 완전 제거한다.
ensure_highrisk_removed() {
    local changed=0
    # 1) systemd 서비스/타이머 정지·비활성·삭제
    for unit in highrisk-bot.service highrisk-bot.timer; do
        if systemctl list-unit-files 2>/dev/null | grep -q "^${unit}\b"; then
            systemctl stop "$unit" 2>/dev/null || true
            systemctl disable "$unit" 2>/dev/null || true
            changed=1
        fi
        if [ -f "/etc/systemd/system/$unit" ]; then
            rm -f "/etc/systemd/system/$unit"
            changed=1
        fi
    done
    [ "$changed" = 1 ] && systemctl daemon-reload 2>/dev/null || true
    # 2) 메모리상 옛 코드로 살아있을 수 있는 고위험 프로세스 강제 종료
    pkill -f 'scripts\.highrisk_trade' 2>/dev/null || true
    # 3) 텔레그램 합산 현황(_read_all_statuses)이 읽는 잔존 상태/소유/포지션 파일 삭제
    rm -f "$UPBIT/.botstate/status_3_고위험.txt" \
          "$UPBIT/.botstate/owned_highrisk.txt" \
          "$UPBIT/.botstate/positions_highrisk.json" 2>/dev/null || true
    [ "$changed" = 1 ] && echo "  🗑️  highrisk-bot 서비스·프로세스·상태파일 완전 제거"
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
    # 이미 설치돼 있고 타이머 내용이 deploy 버전과 같으면 건너뜀(아니면 갱신).
    if [ -f "$RT" ] && cmp -s "$UPBIT/deploy/$4" "$RT" 2>/dev/null; then
        return 0
    fi
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
    echo "  ✅ $1.timer 설치/갱신"
}

ensure_swing_paper
ensure_highrisk_removed                              # 고위험봇 서버 잔재 완전 제거(매 실행)
ensure_clone_bot "majors-bot"   "Upbit Majors (BTC-ETH) Trend Bot" \
    "scripts.majors_trade --invest 100000 --live" "majors.log"
ensure_oneshot_timer "rebalance" "Upbit daily equity snapshot + rebalance" \
    "scripts.rebalance" "rebalance.timer" 1          # 매일 자산기록·현행화(설치 즉시 1회)
ensure_oneshot_timer "portfolio-review" "Upbit portfolio review (dashboard+proposal)" \
    "scripts.portfolio_review" "portfolio-review.timer" 1   # 설치 즉시 1회 대시보드 전송
ensure_oneshot_timer "dashboard-publish" "Publish live dashboard to GitHub Pages" \
    "scripts.portfolio_review --quiet" "dashboard-publish.timer" 1   # 라이브 URL 게시(시간당)

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
