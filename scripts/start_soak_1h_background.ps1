param(
    [string]$BaseUrl = "https://bot-trading-ia-production.up.railway.app",
    [string]$Username = "Wadmin",
    [int]$SleepSec = 15,
    [int]$TimeoutSec = 12,
    [int]$Retries = 2
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$scriptPath = Join-Path $PSScriptRoot "soak_testnet.ps1"
$loops = 240
$label = "soak_1h_bg"

if (-not (Test-Path $scriptPath)) {
    throw "No existe script base: $scriptPath"
}

$password = Read-Host "ADMIN_PASSWORD"
if ([string]::IsNullOrWhiteSpace($password)) {
    throw "Password vacio. Cancelado."
}

$artifactsDir = Join-Path $repoRoot "artifacts"
New-Item -ItemType Directory -Force -Path $artifactsDir | Out-Null
$stdoutPath = Join-Path $artifactsDir "soak_1h_bg_stdout.log"
$stderrPath = Join-Path $artifactsDir "soak_1h_bg_stderr.log"

$argLine = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -BaseUrl `"$BaseUrl`" -Username `"$Username`" -Loops $loops -SleepSec $SleepSec -TimeoutSec $TimeoutSec -Retries $Retries -RunLabel $label"

$env:SOAK_ADMIN_PASSWORD = $password
try {
    $p = Start-Process -FilePath "powershell.exe" -ArgumentList $argLine -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
} finally {
    Remove-Item Env:SOAK_ADMIN_PASSWORD -ErrorAction SilentlyContinue
}

Write-Host "Soak 1h lanzado en segundo plano."
Write-Host "PID: $($p.Id)"
Write-Host "Status: artifacts\\soak_1h_bg_status.json"
Write-Host "StdErr: artifacts\\soak_1h_bg_stderr.log"
Write-Host "Done: artifacts\\soak_1h_bg_*_DONE.txt"
