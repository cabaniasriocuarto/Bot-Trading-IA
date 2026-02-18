#!/usr/bin/env bash
set -euo pipefail

CONFIG=${1:-rtlab_config.yaml}

freqtrade download-data \
  --config "$CONFIG" \
  --timeframes 1h 15m 5m 1m \
  --pairs BTC/USDT ETH/USDT
