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
$label = "soak_6h_bg"
$artifactsDir = Join-Path $repoRoot "artifacts"
$statusPath = Join-Path $artifactsDir "$label`_status.json"

if (-not (Test-Path $scriptPath)) {
    throw "No existe script base: $scriptPath"
}
if (-not (Test-Path $statusPath)) {
    throw "No existe status previo: $statusPath"
}

$status = Get-Content $statusPath | ConvertFrom-Json
if (-not $status) {
    throw "No se pudo parsear status: $statusPath"
}

$done = [bool]$status.done
if ($done) {
    Write-Host "El soak 6h ya figura terminado. No hay nada para reanudar."
    Write-Host "Status: $statusPath"
    exit 0
}

$loopsTotal = [int]$status.loops
$iterDone = [int]$status.iter
$remaining = $loopsTotal - $iterDone
if ($remaining -le 0) {
    Write-Host "No hay iteraciones pendientes (loops=$loopsTotal iter=$iterDone)."
    exit 0
}

$running = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -match "powershell" -and
        $_.CommandLine -match "soak_testnet\.ps1" -and
        $_.CommandLine -match "RunLabel\s+soak_6h_bg"
    } |
    Select-Object -First 1

if ($running) {
    Write-Host "Ya hay un proceso soak 6h ejecutando."
    Write-Host "PID: $($running.ProcessId)"
    Write-Host "CommandLine: $($running.CommandLine)"
    exit 0
}

$password = Read-Host "ADMIN_PASSWORD"
if ([string]::IsNullOrWhiteSpace($password)) {
    throw "Password vacio. Cancelado."
}

New-Item -ItemType Directory -Force -Path $artifactsDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutPath = Join-Path $artifactsDir "soak_6h_bg_resume_$stamp`_stdout.log"
$stderrPath = Join-Path $artifactsDir "soak_6h_bg_resume_$stamp`_stderr.log"

$startIter = $iterDone + 1
$offsetOk = [int]$status.ok
$offsetErrors = [int]$status.errors
$offsetG10 = [int]$status.g10_pass
$startedAt = [string]$status.started_at
$logPath = [string]$status.log_path

if ([string]::IsNullOrWhiteSpace($logPath)) {
    $logPath = Join-Path $artifactsDir "$label`_$stamp.jsonl"
}

$argLine = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", "`"$scriptPath`"",
    "-BaseUrl", "`"$BaseUrl`"",
    "-Username", "`"$Username`"",
    "-Loops", "$remaining",
    "-SleepSec", "$SleepSec",
    "-TimeoutSec", "$TimeoutSec",
    "-Retries", "$Retries",
    "-RunLabel", "$label",
    "-StartIter", "$startIter",
    "-TotalLoops", "$loopsTotal",
    "-OffsetOk", "$offsetOk",
    "-OffsetErrors", "$offsetErrors",
    "-OffsetG10Pass", "$offsetG10",
    "-StartedAt", "`"$startedAt`"",
    "-StatusPath", "`"$statusPath`"",
    "-LogPath", "`"$logPath`""
) -join " "

$env:SOAK_ADMIN_PASSWORD = $password
try {
    $p = Start-Process -FilePath "powershell.exe" -ArgumentList $argLine -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
} finally {
    Remove-Item Env:SOAK_ADMIN_PASSWORD -ErrorAction SilentlyContinue
}

Write-Host "Reanudacion de soak 6h lanzada en segundo plano."
Write-Host "PID: $($p.Id)"
Write-Host "Pendientes retomadas: $remaining (iter $startIter .. $loopsTotal)"
Write-Host "Status: artifacts\\soak_6h_bg_status.json"
Write-Host "Log principal: $logPath"
Write-Host "StdOut resume: $stdoutPath"
Write-Host "StdErr resume: $stderrPath"
