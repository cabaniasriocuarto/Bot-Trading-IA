#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
STRICT_MODE="${SECURITY_SCAN_STRICT:-0}"

echo "[security-scan] root=$ROOT_DIR"

echo "[security-scan] pip-audit (runtime/research)"
AUDIT_STATUS=0
bash scripts/security_audit.sh || AUDIT_STATUS=$?
if [[ $AUDIT_STATUS -eq 2 && "$STRICT_MODE" != "1" ]]; then
  echo "[security-scan][WARN] pip-audit no disponible en local (modo no estricto)."
  AUDIT_STATUS=0
fi

GITLEAKS_STATUS=0
if command -v gitleaks >/dev/null 2>&1; then
  mkdir -p artifacts/security_audit
  echo "[security-scan] gitleaks detect"
  # --- gitleaks ---
GITLEAKS_REPORT_DIR="artifacts/security_audit"
mkdir -p "$GITLEAKS_REPORT_DIR"

BASELINE_JSON="$GITLEAKS_REPORT_DIR/gitleaks-baseline.json"
REPORT_SARIF="$GITLEAKS_REPORT_DIR/gitleaks.sarif"

echo "[security-scan] gitleaks (baseline-aware)"

if [ -f "$BASELINE_JSON" ]; then
  echo "[security-scan] usando baseline: $BASELINE_JSON"
  # Escanea historial pero ignora hallazgos presentes en baseline
  gitleaks git --redact --baseline-path "$BASELINE_JSON" \
    --report-format sarif --report-path "$REPORT_SARIF"
else
  echo "[security-scan] sin baseline (modo estricto)"
  gitleaks git --redact --report-format sarif --report-path "$REPORT_SARIF"
fi
  if [[ "$STRICT_MODE" == "1" ]]; then
    echo "[security-scan][ERROR] gitleaks no instalado y SECURITY_SCAN_STRICT=1"
    GITLEAKS_STATUS=2
  else
    echo "[security-scan][WARN] gitleaks no instalado. Instalar desde https://github.com/gitleaks/gitleaks"
  fi
fi

if [[ $AUDIT_STATUS -ne 0 ]]; then
  echo "[security-scan][ERROR] security_audit fallo con codigo=$AUDIT_STATUS"
fi
if [[ $GITLEAKS_STATUS -ne 0 ]]; then
  echo "[security-scan][ERROR] gitleaks fallo con codigo=$GITLEAKS_STATUS"
fi

if [[ $AUDIT_STATUS -ne 0 || $GITLEAKS_STATUS -ne 0 ]]; then
  exit 1
fi
echo "[security-scan] OK"
