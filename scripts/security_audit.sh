#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python}"
OUT_DIR="${OUT_DIR:-artifacts/security_audit}"
mkdir -p "$OUT_DIR"

echo "[security] Root: $ROOT_DIR"
echo "[security] Python: $PYTHON_BIN"

run_pip_audit() {
  local req_file="$1"
  local out_file="$2"
  if [[ ! -f "$req_file" ]]; then
    echo "[security] Saltando $req_file (no existe)"
    return 0
  fi
  if "$PYTHON_BIN" -m pip_audit --version >/dev/null 2>&1; then
    echo "[security] pip-audit -> $req_file"
    "$PYTHON_BIN" -m pip_audit -r "$req_file" -f json -o "$out_file"
  elif command -v pip-audit >/dev/null 2>&1; then
    echo "[security] pip-audit (CLI) -> $req_file"
    pip-audit -r "$req_file" -f json -o "$out_file"
  else
    echo "[security][WARN] pip-audit no está instalado. Instalar con: $PYTHON_BIN -m pip install pip-audit"
    return 2
  fi
}

gen_sbom() {
  local req_file="$1"
  local out_file="$2"
  if [[ ! -f "$req_file" ]]; then
    return 0
  fi
  if command -v cyclonedx-py >/dev/null 2>&1; then
    echo "[security] Generando SBOM con cyclonedx-py -> $req_file"
    cyclonedx-py requirements "$req_file" -o "$out_file" >/dev/null
  elif command -v cyclonedx-bom >/dev/null 2>&1; then
    echo "[security] Generando SBOM con cyclonedx-bom -> $req_file"
    cyclonedx-bom -r -i "$req_file" -o "$out_file" >/dev/null 2>&1 || true
  else
    echo "[security][WARN] No se encontró cyclonedx-py/cyclonedx-bom. SBOM omitido para $req_file"
    return 2
  fi
}

AUDIT_STATUS=0
run_pip_audit "requirements-runtime.txt" "$OUT_DIR/pip-audit-runtime.json" || AUDIT_STATUS=$?
run_pip_audit "requirements-research.txt" "$OUT_DIR/pip-audit-research.json" || AUDIT_STATUS=$?

gen_sbom "requirements-runtime.txt" "$OUT_DIR/sbom-runtime.cdx.json" || true
gen_sbom "requirements-research.txt" "$OUT_DIR/sbom-research.cdx.json" || true

echo "[security] Reportes en $OUT_DIR"
exit "$AUDIT_STATUS"
