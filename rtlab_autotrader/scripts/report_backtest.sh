#!/usr/bin/env bash
set -euo pipefail

if [ -f user_data/logs/backtest-result.json ]; then
  echo "Backtest artifact: user_data/logs/backtest-result.json"
  wc -c user_data/logs/backtest-result.json
else
  echo "No backtest artifact found."
fi
