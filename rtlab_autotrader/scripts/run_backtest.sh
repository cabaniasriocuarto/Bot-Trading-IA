#!/usr/bin/env bash
set -euo pipefail

CONFIG=${1:-rtlab_config.yaml}
STRATEGY=${2:-MicrostructureTrendPullbackStrategy}
TIMERANGE=${3:-20240101-}
PAIRS_RAW=${4:-"BTC/USDT ETH/USDT"}

read -r -a PAIRS <<< "$PAIRS_RAW"
PAIR_ARGS=()
for p in "${PAIRS[@]}"; do
  PAIR_ARGS+=("--pairs" "$p")
done

freqtrade backtesting \
  --config "$CONFIG" \
  --strategy "$STRATEGY" \
  --timerange "$TIMERANGE" \
  --timeframe-detail 1m \
  --export trades \
  --export-filename user_data/logs/backtest-result.json \
  "${PAIR_ARGS[@]}"
