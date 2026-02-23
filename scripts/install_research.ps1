param(
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Write-Host "Instalando stack research (offline)..." -ForegroundColor Cyan
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements-research.txt
Write-Host "OK: research instalado." -ForegroundColor Green
