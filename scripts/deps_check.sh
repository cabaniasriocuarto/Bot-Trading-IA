#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python}"

echo "[deps] Root: $ROOT_DIR"
echo "[deps] Python: $PYTHON_BIN"

echo "[deps] Ejecutando pip check..."
"$PYTHON_BIN" -m pip check

echo "[deps] Ejecutando pipdeptree --warn fail..."
if "$PYTHON_BIN" -m pipdeptree --version >/dev/null 2>&1; then
  "$PYTHON_BIN" -m pipdeptree --warn fail
elif command -v pipdeptree >/dev/null 2>&1; then
  pipdeptree --warn fail
else
  echo "[deps][ERROR] pipdeptree no está instalado."
  echo "[deps][HINT] Instalar con: $PYTHON_BIN -m pip install pipdeptree"
  exit 2
fi

echo "[deps] OK (sin conflictos detectados por pipdeptree/pip check)."
