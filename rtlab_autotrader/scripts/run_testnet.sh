#!/usr/bin/env bash
set -euo pipefail

CONFIG=${1:-rtlab_config.yaml}

rtbot run --mode testnet --config "$CONFIG"
