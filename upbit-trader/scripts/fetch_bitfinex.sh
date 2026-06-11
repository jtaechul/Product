#!/usr/bin/env bash
# Bitfinex 1분봉 검증 데이터 재생성 (거래소 API 차단 환경에서도 동작).
# 공개 GitHub 저장소(Zombie-3000/Bitfinex-historical-data)에서 연도별 merged.csv만
# 받아 data/bitfinex/{COIN}-{YEAR}.csv 로 정리합니다. (약 474MB, git clone 필요)
#
# 사용:  bash scripts/fetch_bitfinex.sh
set -euo pipefail
DEST="$(cd "$(dirname "$0")/.." && pwd)/data/bitfinex"
TMP="$(mktemp -d)"
echo "Bitfinex 1분봉 받는 중... (merged.csv만, 수백 MB)"
git clone --depth 1 --filter=blob:none --no-checkout \
  https://github.com/Zombie-3000/Bitfinex-historical-data "$TMP/bfx"
cd "$TMP/bfx"
git sparse-checkout init --no-cone >/dev/null 2>&1
git sparse-checkout set "*/Candles_1m/*/merged.csv" >/dev/null 2>&1
git checkout HEAD >/dev/null 2>&1
mkdir -p "$DEST"
for f in $(find . -name merged.csv); do
  coin=$(echo "$f" | cut -d/ -f2 | sed 's/USD$//')
  year=$(echo "$f" | cut -d/ -f4)
  cp "$f" "$DEST/${coin}-${year}.csv"
done
rm -rf "$TMP"
echo "완료: $DEST ($(ls "$DEST" | wc -l)개 파일)"
echo "이제: python -m scripts.backtest_bitfinex"
