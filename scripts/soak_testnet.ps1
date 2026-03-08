param(
    [string]$BaseUrl = "https://bot-trading-ia-production.up.railway.app",
    [string]$Username = "Wadmin",
    [int]$Loops = 5760,
    [int]$SleepSec = 15,
    [int]$TimeoutSec = 12,
    [int]$Retries = 2,
    [string]$RunLabel = "soak_run",
    [string]$AdminPassword = "",
    [string]$StatusPath = "",
    [string]$LogPath = "",
    [string]$DonePath = "",
    [int]$StartIter = 1,
    [int]$TotalLoops = 0,
    [int]$OffsetOk = 0,
    [int]$OffsetErrors = 0,
    [int]$OffsetG10Pass = 0,
    [string]$StartedAt = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ($Loops -lt 1) { throw "Loops debe ser >= 1" }
if ($SleepSec -lt 1) { throw "SleepSec debe ser >= 1" }
if ($TimeoutSec -lt 1) { throw "TimeoutSec debe ser >= 1" }
if ($Retries -lt 0) { throw "Retries debe ser >= 0" }
if ($StartIter -lt 1) { throw "StartIter debe ser >= 1" }
if ($OffsetOk -lt 0 -or $OffsetErrors -lt 0 -or $OffsetG10Pass -lt 0) { throw "Offsets no pueden ser negativos" }

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$artifactsDir = Join-Path $repoRoot "artifacts"
New-Item -ItemType Directory -Force -Path $artifactsDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogPath = Join-Path $artifactsDir "$RunLabel`_$stamp.jsonl"
}
if ([string]::IsNullOrWhiteSpace($StatusPath)) {
    $StatusPath = Join-Path $artifactsDir "$RunLabel`_status.json"
}
if ([string]::IsNullOrWhiteSpace($DonePath)) {
    $DonePath = Join-Path $artifactsDir "$RunLabel`_$stamp`_DONE.txt"
}

if ($TotalLoops -le 0) {
    $TotalLoops = $Loops
}
$endIterTarget = $StartIter + $Loops - 1
if ($TotalLoops -lt $endIterTarget) {
    throw "TotalLoops ($TotalLoops) no puede ser menor que iter final del segmento ($endIterTarget)."
}

if ([string]::IsNullOrWhiteSpace($AdminPassword)) {
    $AdminPassword = $env:SOAK_ADMIN_PASSWORD
}

if ([string]::IsNullOrWhiteSpace($AdminPassword)) {
    $AdminPassword = Read-Host "ADMIN_PASSWORD"
}

if ([string]::IsNullOrWhiteSpace($AdminPassword)) {
    throw "Password vacio. Cancelado."
}

function Invoke-WithRetry {
    param(
        [scriptblock]$Action,
        [int]$MaxRetries = 2
    )
    $attempt = 0
    while ($true) {
        try {
            return & $Action
        } catch {
            if ($attempt -ge $MaxRetries) { throw }
            Start-Sleep -Seconds 2
            $attempt++
        }
    }
}

$okCount = $OffsetOk
$errorCount = $OffsetErrors
$g10PassCount = $OffsetG10Pass
$startTs = if ([string]::IsNullOrWhiteSpace($StartedAt)) { (Get-Date).ToString("o") } else { $StartedAt }

for ($segmentIdx = 0; $segmentIdx -lt $Loops; $segmentIdx++) {
    $i = $StartIter + $segmentIdx
    $ts = (Get-Date).ToString("o")
    $row = $null

    try {
        $loginBody = @{ username = $Username; password = $AdminPassword } | ConvertTo-Json
        $login = Invoke-WithRetry -MaxRetries $Retries -Action {
            Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/auth/login" -ContentType "application/json" -Body $loginBody -TimeoutSec $TimeoutSec
        }

        $headers = @{ Authorization = "Bearer $($login.token)" }

        $health = Invoke-WithRetry -MaxRetries $Retries -Action {
            Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/health" -TimeoutSec $TimeoutSec
        }
        $gates = Invoke-WithRetry -MaxRetries $Retries -Action {
            Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/gates" -Headers $headers -TimeoutSec $TimeoutSec
        }

        $g10 = ($gates.gates | Where-Object { $_.id -eq "G10_STORAGE_PERSISTENCE" } | Select-Object -First 1)

        $row = [ordered]@{
            ts = $ts
            iter = $i
            segment_iter = ($segmentIdx + 1)
            ok = [bool]$health.ok
            overall_status = [string]$gates.overall_status
            g10_status = [string]$g10.status
            persistent_storage = [bool]$health.storage.persistent_storage
            user_data_dir = [string]$health.storage.user_data_dir
        }

        $okCount++
        if ($row.g10_status -eq "PASS") { $g10PassCount++ }
        Write-Host ("[{0}/{1}] OK overall={2} g10={3}" -f $i, $TotalLoops, $row.overall_status, $row.g10_status)
    } catch {
        $row = [ordered]@{
            ts = $ts
            iter = $i
            segment_iter = ($segmentIdx + 1)
            error = [string]$_.Exception.Message
        }
        $errorCount++
        Write-Host ("[{0}/{1}] ERROR {2}" -f $i, $TotalLoops, $row.error)
    }

    ($row | ConvertTo-Json -Compress) | Add-Content -Path $LogPath

    $status = [ordered]@{
        run_label = $RunLabel
        started_at = $startTs
        last_ts = $ts
        iter = $i
        loops = $TotalLoops
        ok = $okCount
        errors = $errorCount
        g10_pass = $g10PassCount
        segment = [ordered]@{
            loops = $Loops
            start_iter = $StartIter
            offset_ok = $OffsetOk
            offset_errors = $OffsetErrors
            offset_g10_pass = $OffsetG10Pass
        }
        log_path = $LogPath
        done = $false
    }
    ($status | ConvertTo-Json -Depth 6) | Set-Content -Path $StatusPath -Encoding UTF8

    if ($segmentIdx -lt ($Loops - 1)) {
        Start-Sleep -Seconds $SleepSec
    }
}

$endTs = (Get-Date).ToString("o")
$final = [ordered]@{
    run_label = $RunLabel
    started_at = $startTs
    ended_at = $endTs
    iter = $endIterTarget
    loops = $TotalLoops
    ok = $okCount
    errors = $errorCount
    g10_pass = $g10PassCount
    segment = [ordered]@{
        loops = $Loops
        start_iter = $StartIter
        offset_ok = $OffsetOk
        offset_errors = $OffsetErrors
        offset_g10_pass = $OffsetG10Pass
    }
    log_path = $LogPath
    status_path = $StatusPath
    done = $true
}
($final | ConvertTo-Json -Depth 6) | Set-Content -Path $StatusPath -Encoding UTF8
@(
    "DONE"
    "run_label=$RunLabel"
    "started_at=$startTs"
    "ended_at=$endTs"
    "iter=$endIterTarget"
    "loops=$TotalLoops"
    "ok=$okCount"
    "errors=$errorCount"
    "g10_pass=$g10PassCount"
    "log_path=$LogPath"
) | Set-Content -Path $DonePath -Encoding UTF8

Write-Host ""
Write-Host "SOAK TERMINADO"
Write-Host "LOG: $LogPath"
Write-Host "STATUS: $StatusPath"
Write-Host "DONE: $DonePath"
Write-Host "RESUMEN: total=$TotalLoops iter=$endIterTarget ok=$okCount errors=$errorCount g10_pass=$g10PassCount"
