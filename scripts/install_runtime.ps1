param(
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Write-Host "Instalando stack runtime (liviano)..." -ForegroundColor Cyan
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements-runtime.txt
Write-Host "OK: runtime instalado." -ForegroundColor Green
