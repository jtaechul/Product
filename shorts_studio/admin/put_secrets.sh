#!/usr/bin/env bash
# 워커에 비밀값을 밀어 넣는다.
#
# GitHub 시크릿을 고쳐도 그것만으로는 워커에 전달되지 않는다. 이 스크립트가 한 번
# 돌아야 반영된다. 그래서 배포 워크플로와 **주기 반영 워크플로가 같은 이 파일**을 쓴다
# — 두 군데에 같은 코드를 두면 한쪽만 고쳐져 "왜 반영이 안 되지"가 또 생긴다.
#
# 값은 인자가 아니라 환경변수로 받는다. 명령줄에 적으면 실행 기록에 남는다.
set -euo pipefail

W="npx --yes wrangler@4"
changed=0

put() {           # put <이름> <값>  — 값이 비었으면 건너뛴다
  if [ -n "${2:-}" ]; then
    printf '%s' "$2" | $W secret put "$1" >/dev/null
    echo "  $1 반영"
    changed=$((changed + 1))
  else
    echo "  $1 (값이 없어 건너뜀)"
  fi
}

echo "워커 비밀값 반영:"
put GH_TOKEN       "${SEC_GH_TOKEN:-}"
put ADMIN_PASSWORD "${SEC_ADMIN_PASSWORD:-}"
put SESSION_SECRET "${SEC_SESSION_SECRET:-}"
put KEY_SECRET     "${SEC_KEY_SECRET:-}"

# 사용자 목록은 아이디별 칸(U1..U8)을 모아서 만든다. 비밀번호는 찍지 않는다.
WHO=$(python3 build_users.py users.json)
echo "  $WHO"
if [ -s users.json ]; then
  $W secret put USERS < users.json >/dev/null
  echo "  USERS 반영"
  changed=$((changed + 1))
fi
rm -f users.json

echo "끝났습니다 (총 ${changed}개)."

# 로그를 뒤지지 않아도 "무슨 아이디로 들어가면 되는지" 바로 보이게 한다.
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "## 로그인 정보"
    echo ""
    echo "- $WHO"
    echo "- 관리자 계정 \`admin\` + \`MOVIEGEN_ADMIN_PASSWORD\` 는 **언제나** 살아 있습니다."
    echo "- 아이디 칸을 비우고 비밀번호만 쳐도 들어갑니다."
  } >> "$GITHUB_STEP_SUMMARY"
fi
