param(
    [string]$BaseUrl = "https://bot-trading-ia-production.up.railway.app",
    [string]$Username = "Wadmin",
    [int[]]$Targets = @(10, 15, 20, 25, 30),
    [string]$TargetsCsv = "",
    [int]$Requests = 20,
    [int]$Warmup = 5,
    [double]$TimeoutSec = 10.0,
    [switch]$Retry429 = $true,
    [int]$MaxRetries429 = 20,
    [double]$PaceSec = 1.5,
    [double]$SeedPaceSec = 0.8,
    [string]$Engine = "bandit_thompson",
    [ValidateSet("shadow", "paper", "testnet")]
    [string]$Mode = "paper",
    [ValidateSet("active", "paused")]
    [string]$Status = "active",
    [switch]$Exact = $false,
    [switch]$AllowDelete = $false,
    [ValidateSet("seed-only", "any")]
    [string]$DeletePolicy = "seed-only"
)

$ErrorActionPreference = "Stop"

function Parse-Metric {
    param(
        [string[]]$Lines,
        [string]$Label
    )
    $line = $Lines | Where-Object { $_ -like "*$Label*" } | Select-Object -First 1
    if (-not $line) { return "" }
    if ($line -match "\*\*([0-9\.]+)\*\*") { return $matches[1] }
    return ""
}

function Parse-IntFromLine {
    param([string]$Line)
    if (-not $Line) { return $null }
    if ($Line -match "(\d+)") { return [int]$matches[1] }
    return $null
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "No se encontro 'python' en PATH."
    }

    $rawTargets = @()
    if (-not [string]::IsNullOrWhiteSpace($TargetsCsv)) {
        $parts = [regex]::Split($TargetsCsv, "[,;|\s]+") | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        $rawTargets += $parts
    } else {
        $rawTargets += $Targets
    }

    $targetsClean = @($rawTargets | ForEach-Object { [int]$_ } | Where-Object { $_ -gt 0 } | Sort-Object -Unique)
    if (-not $targetsClean -or $targetsClean.Count -eq 0) {
        throw "Targets vacio. Ejemplo: -Targets 10,15,20,25,30"
    }
    if ($targetsClean.Count -eq 1 -and $targetsClean[0] -gt 1000 -and [string]::IsNullOrWhiteSpace($TargetsCsv)) {
        throw "Targets parece mal parseado ($($targetsClean[0])). Usa: -TargetsCsv '10,15,20,25,30' o -Targets @(10,15,20,25,30)."
    }

    $adminPass = Read-Host "ADMIN_PASSWORD"
    if ([string]::IsNullOrWhiteSpace($adminPass)) {
        throw "ADMIN_PASSWORD vacio. Cancelado."
    }
    $prevAdminPasswordEnv = $env:RTLAB_ADMIN_PASSWORD
    $prevPasswordEnv = $env:RTLAB_PASSWORD
    $prevBenchPasswordEnv = $env:RTLAB_BENCH_PASSWORD
    $env:RTLAB_ADMIN_PASSWORD = $adminPass
    $env:RTLAB_PASSWORD = $adminPass
    $env:RTLAB_BENCH_PASSWORD = $adminPass

    $dateTag = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
    $summary = @()

    foreach ($target in $targetsClean) {
        Write-Host ""
        Write-Host "=== Sweep target bots: $target ==="

        $seedArgs = @(
            "scripts/seed_bots_remote.py",
            "--base-url", $BaseUrl,
            "--username", $Username,
            "--target-bots", "$target",
            "--engine", $Engine,
            "--mode", $Mode,
            "--status", $Status,
            "--timeout-sec", "$TimeoutSec",
            "--max-retries-429", "$MaxRetries429",
            "--pace-sec", "$SeedPaceSec"
        )
        if ($Exact) {
            $seedArgs += "--exact"
            $seedArgs += "--delete-policy"
            $seedArgs += "$DeletePolicy"
            if ($AllowDelete) {
                $seedArgs += "--allow-delete"
            }
        }
        if ($Retry429) {
            $seedArgs += "--retry-429"
        }
        & python @seedArgs
        if ($LASTEXITCODE -ne 0) {
            throw "seed_bots_remote.py fallo para target=$target (exit $LASTEXITCODE)."
        }

        $reportPath = "docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_SWEEP_${dateTag}_B${target}.md"
        $benchArgs = @(
            "scripts/benchmark_bots_overview.py",
            "--base-url", $BaseUrl,
            "--username", $Username,
            "--requests", "$Requests",
            "--warmup", "$Warmup",
            "--timeout-sec", "$TimeoutSec",
            "--min-bots-required", "$target",
            "--report-path", $reportPath,
            "--require-evidence"
        )
        if ($Retry429) {
            $benchArgs += "--retry-429"
            $benchArgs += "--max-retries-429"
            $benchArgs += "$MaxRetries429"
        }
        if ($PaceSec -gt 0) {
            $benchArgs += "--pace-sec"
            $benchArgs += "$PaceSec"
        }

        & python @benchArgs
        if ($LASTEXITCODE -ne 0) {
            throw "benchmark_bots_overview.py fallo para target=$target (exit $LASTEXITCODE)."
        }

        $lines = Get-Content $reportPath
        $botsObservedLine = ($lines | Select-String -Pattern "Bots observados" -SimpleMatch | Select-Object -First 1).Line
        $stateLine = ($lines | Select-String -Pattern "- Estado:" -SimpleMatch | Select-Object -First 1).Line
        $observed = Parse-IntFromLine -Line $botsObservedLine
        $stateValue = ($stateLine -replace ".*`:", "").Trim()
        if ($observed -ne $null -and [int]$observed -ne [int]$target) {
            $stateValue = "NOT_EXACT/$stateValue"
            Write-Host "[WARN] target=$target pero bots_observed=$observed. Esta corrida NO mide cardinalidad exacta."
        }
        $p95 = Parse-Metric -Lines $lines -Label "- `p95_ms`:"
        $serverP95 = Parse-Metric -Lines $lines -Label "- `server_p95_ms`:"
        $summary += [PSCustomObject]@{
            target_bots   = $target
            bots_observed = ($botsObservedLine -replace ".*`:", "").Trim()
            state         = $stateValue
            p95_ms        = $p95
            server_p95_ms = $serverP95
            report        = $reportPath
        }
    }

    Write-Host ""
    Write-Host "=== Sweep summary ==="
    $summary | Format-Table -AutoSize
}
finally {
    $env:RTLAB_ADMIN_PASSWORD = $prevAdminPasswordEnv
    $env:RTLAB_PASSWORD = $prevPasswordEnv
    $env:RTLAB_BENCH_PASSWORD = $prevBenchPasswordEnv
    Remove-Variable adminPass -ErrorAction SilentlyContinue
    Pop-Location
}
