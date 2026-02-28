#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[security-scan] root=$ROOT_DIR"

echo "[security-scan] pip-audit (runtime/research)"
bash scripts/security_audit.sh || true

if command -v gitleaks >/dev/null 2>&1; then
  mkdir -p artifacts/security_audit
  echo "[security-scan] gitleaks detect"
  gitleaks detect --source . --report-format sarif --report-path artifacts/security_audit/gitleaks.sarif
else
  echo "[security-scan][WARN] gitleaks no instalado. Instalar desde https://github.com/gitleaks/gitleaks"
fi
