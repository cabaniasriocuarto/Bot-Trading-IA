#!/usr/bin/env bash
set -euo pipefail

FILE=${1:?"usage: strategy_pack_import.sh <pack.txt>"}
NOTES=${2:-""}

if [ -n "$NOTES" ]; then
  rtbot pack import --file "$FILE" --notes "$NOTES"
else
  rtbot pack import --file "$FILE"
fi
