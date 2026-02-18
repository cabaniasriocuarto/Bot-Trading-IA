#!/usr/bin/env bash
set -euo pipefail

CONFIG=${1:-rtlab_config.yaml}

freqtrade trade --config "$CONFIG" --dry-run
