param(
    [string]$BaseUrl = "https://bot-trading-ia-production.up.railway.app",
    [string]$Username = "Wadmin",
    [int]$Requests = 12,
    [int]$Warmup = 2,
    [int]$MinBotsRequired = 30,
    [int]$TargetBots = 30,
    [double]$TimeoutSec = 10.0,
    [string]$Password = "",
    [string]$AuthToken = "",
    [switch]$AutoSeed = $true,
    [switch]$Exact = $false,
    [switch]$AllowDelete = $false,
    [ValidateSet("seed-only", "any")]
    [string]$DeletePolicy = "seed-only",
    [double]$SeedPaceSec = 0.8,
    [ValidateSet("client", "server", "either")]
    [string]$PassCriterion = "either",
    [switch]$AllowNoEvidence,
    [switch]$Retry429 = $true,
    [int]$MaxRetries429 = 20,
    [double]$PaceSec = 0.0
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "No se encontro 'python' en PATH."
    }

    $adminPass = [string]$Password
    $token = [string]$AuthToken
    if ([string]::IsNullOrWhiteSpace($adminPass) -and [string]::IsNullOrWhiteSpace($token)) {
        $adminPass = Read-Host "ADMIN_PASSWORD"
    }
    if ($AutoSeed -and [string]::IsNullOrWhiteSpace($adminPass) -and [string]::IsNullOrWhiteSpace($token)) {
        throw "AutoSeed requiere auth: -AuthToken o -Password."
    }

    $prevAuthToken = $env:RTLAB_AUTH_TOKEN
    $prevPassword = $env:RTLAB_PASSWORD
    $prevBenchPassword = $env:RTLAB_BENCH_PASSWORD
    if (-not [string]::IsNullOrWhiteSpace($token)) {
        $env:RTLAB_AUTH_TOKEN = $token
    }
    if (-not [string]::IsNullOrWhiteSpace($adminPass)) {
        $env:RTLAB_PASSWORD = $adminPass
        $env:RTLAB_BENCH_PASSWORD = $adminPass
    }

    $effectiveTarget = [Math]::Max(1, [Math]::Max($TargetBots, $MinBotsRequired))
    if ($AutoSeed) {
        Write-Host "[0/2] Seed remoto a $effectiveTarget bots..."
        $seedArgs = @(
            "scripts/seed_bots_remote.py",
            "--base-url", $BaseUrl,
            "--username", $Username,
            "--target-bots", "$effectiveTarget",
            "--timeout-sec", "$TimeoutSec",
            "--max-retries-429", "$MaxRetries429",
            "--pace-sec", "$SeedPaceSec"
        )
        if (-not [string]::IsNullOrWhiteSpace($token)) {
            $seedArgs += "--auth-token"
            $seedArgs += "$token"
        }
        if ($Retry429) {
            $seedArgs += "--retry-429"
        }
        if ($Exact) {
            $seedArgs += "--exact"
            $seedArgs += "--delete-policy"
            $seedArgs += "$DeletePolicy"
            if ($AllowDelete) {
                $seedArgs += "--allow-delete"
            }
        }
        & python @seedArgs
        if ($LASTEXITCODE -ne 0) {
            throw "seed_bots_remote.py fallo (exit $LASTEXITCODE)."
        }
    }

    $dateTag = (Get-Date).ToUniversalTime().ToString("yyyyMMdd")
    $reportPath = "docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_${dateTag}_RERUN.md"

    Write-Host "[1/2] Ejecutando benchmark remoto..."
    $benchArgs = @(
        "scripts/benchmark_bots_overview.py",
        "--base-url", $BaseUrl,
        "--username", $Username,
        "--pass-criterion", "$PassCriterion",
        "--requests", "$Requests",
        "--warmup", "$Warmup",
        "--timeout-sec", "$TimeoutSec",
        "--min-bots-required", "$MinBotsRequired",
        "--report-path", $reportPath
    )
    if (-not [string]::IsNullOrWhiteSpace($token)) {
        $benchArgs += "--auth-token"
        $benchArgs += "$token"
    } else {
        throw "Falta autenticacion: pasar -AuthToken o -Password."
    }
    if (-not $AllowNoEvidence) {
        $benchArgs += "--require-evidence"
    }
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

    if ($LASTEXITCODE -eq 2 -and -not $AllowNoEvidence) {
        throw "Benchmark remoto sin evidencia suficiente (bots < minimo requerido)."
    }
    if ($LASTEXITCODE -eq 2 -and $AllowNoEvidence) {
        Write-Host "[WARN] Benchmark remoto en NO_EVIDENCIA (bots < minimo requerido), pero se permite continuar."
    }
    if ($LASTEXITCODE -eq 3) {
        throw "Benchmark remoto ejecutado pero no cumple objetivo p95."
    }
    if ($LASTEXITCODE -ne 0) {
        throw "benchmark_bots_overview.py fallo con exit $LASTEXITCODE."
    }

    Write-Host "[2/2] OK: benchmark remoto finalizado. Reporte: $reportPath"
    if (Test-Path -LiteralPath $reportPath) {
        $reportLines = Get-Content -LiteralPath $reportPath
        $edgeLine = ($reportLines | Select-String -Pattern "Railway edge:" -SimpleMatch | Select-Object -First 1).Line
        $stateLine = ($reportLines | Select-String -Pattern "- Estado:" -SimpleMatch | Select-Object -First 1).Line
        if ($edgeLine) { Write-Host $edgeLine }
        if ($stateLine) { Write-Host $stateLine }
    }
}
finally {
    if ($null -ne $prevAuthToken) { $env:RTLAB_AUTH_TOKEN = $prevAuthToken } else { Remove-Item Env:RTLAB_AUTH_TOKEN -ErrorAction SilentlyContinue }
    if ($null -ne $prevPassword) { $env:RTLAB_PASSWORD = $prevPassword } else { Remove-Item Env:RTLAB_PASSWORD -ErrorAction SilentlyContinue }
    if ($null -ne $prevBenchPassword) { $env:RTLAB_BENCH_PASSWORD = $prevBenchPassword } else { Remove-Item Env:RTLAB_BENCH_PASSWORD -ErrorAction SilentlyContinue }
    Remove-Variable adminPass -ErrorAction SilentlyContinue
    Remove-Variable token -ErrorAction SilentlyContinue
    Remove-Variable prevAuthToken -ErrorAction SilentlyContinue
    Remove-Variable prevPassword -ErrorAction SilentlyContinue
    Remove-Variable prevBenchPassword -ErrorAction SilentlyContinue
    Pop-Location
}
