#!/usr/bin/env bash
# 10분마다 GitHub 최신 코드를 받아 자동 반영하는 스크립트 (GCP VM 용).
#
# 동작:
#   1) 현재 브랜치의 원격 최신을 fetch
#   2) 새 커밋이 없으면 아무 것도 안 함(조용히 종료)
#   3) 새 커밋이 있으면 하드 리셋으로 최신과 일치시키고, 봇 서비스를 재시작
#
# systemd timer(auto-update.timer)가 이 스크립트를 10분 간격으로 호출합니다.
# .env(API키)는 git 추적 대상이 아니므로 reset 으로 지워지지 않습니다.
set -euo pipefail

# 봇이 설치된 저장소 경로 (SETUP.md 와 동일하게 맞추세요)
REPO_DIR="${REPO_DIR:-/home/botuser/Product}"
# 재시작할 봇 서비스들 (존재하는 것만 재시작)
SERVICES="${SERVICES:-swing-bot majors-bot}"

cd "$REPO_DIR"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git fetch --quiet origin "$BRANCH"

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0   # 변경 없음 → 종료(로그도 남기지 않음)
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
