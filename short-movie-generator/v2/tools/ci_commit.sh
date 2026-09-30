#!/usr/bin/env bash
# v2-admin.yml 공용: 바뀐 상태 파일을 커밋·푸시(다른 실행과 겹치면 rebase 후 재시도). 사용: ci_commit.sh "메시지"
git add v2/pilots v2/topics.json v2/topic_media.json 2>/dev/null || true
git diff --cached --quiet && exit 0
git -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" commit -q -m "$1"
for i in 1 2 3 4 5; do
  git pull -q --rebase origin "$GITHUB_REF_NAME" && git push -q origin HEAD:"$GITHUB_REF_NAME" && exit 0
  sleep $((i*3))
done
exit 1
