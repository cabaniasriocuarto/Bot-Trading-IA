param(
    [string]$BaseUrl = "https://bot-trading-ia-production.up.railway.app",
    [string]$Username = "Wadmin",
    [int]$Requests = 12,
    [int]$Warmup = 2,
    [int]$MinBotsRequired = 30,
    [int]$TargetBots = 30,
    [double]$TimeoutSec = 10.0,
    [string]$Password = "",
    [switch]$AutoSeed = $true,
    [switch]$Exact = $false,
    [switch]$AllowDelete = $false,
    [ValidateSet("seed-only", "any")]
    [string]$DeletePolicy = "seed-only",
    [double]$SeedPaceSec = 0.8,
    [switch]$RequireTargetPass,
    [switch]$AllowProtected404Fallback,
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
    if ([string]::IsNullOrWhiteSpace($adminPass)) {
        $adminPass = Read-Host "ADMIN_PASSWORD"
    }
    if ([string]::IsNullOrWhiteSpace($adminPass)) {
        throw "ADMIN_PASSWORD vacio. Cancelado."
    }

    $effectiveTarget = [Math]::Max(1, [Math]::Max($TargetBots, $MinBotsRequired))
    if ($AutoSeed) {
        Write-Host "0/3 Ajustando cardinalidad de bots a $effectiveTarget..."
        $seedArgs = @(
            "scripts/seed_bots_remote.py",
            "--base-url", $BaseUrl,
            "--username", $Username,
            "--password", $adminPass,
            "--target-bots", "$effectiveTarget",
            "--timeout-sec", "$TimeoutSec",
            "--max-retries-429", "$MaxRetries429",
            "--pace-sec", "$SeedPaceSec"
        )
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
    $benchmarkReport = "docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_${dateTag}_FINAL.md"

    Write-Host "1/3 Verificando storage persistente + G10..."
    & python scripts/check_storage_persistence.py `
        --base-url $BaseUrl `
        --username $Username `
        --password $adminPass `
        --timeout-sec $TimeoutSec `
        --require-persistent
    if ($LASTEXITCODE -ne 0) {
        throw "check_storage_persistence fallo (exit $LASTEXITCODE)."
    }

    Write-Host "2/3 Generando snapshot estricto con endpoints protegidos..."
    & python scripts/build_ops_snapshot.py `
        --base-url $BaseUrl `
        --username $Username `
        --password $adminPass `
        --timeout-sec $TimeoutSec `
        --require-protected `
        --label ops_block2_snapshot_final
    if ($LASTEXITCODE -ne 0) {
        $latestStrict = Get-ChildItem -LiteralPath "artifacts" -Filter "ops_block2_snapshot_final_*.json" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        $notes = @()
        if ($latestStrict) {
            try {
                $payload = Get-Content -LiteralPath $latestStrict.FullName -Raw | ConvertFrom-Json
                $notes = @($payload.notes)
            } catch {
                $notes = @()
            }
        }
        $hasProtected404 = ($notes | Where-Object { $_ -match "breaker_events_unavailable: http_404|internal_proxy_status_unavailable: http_404" }).Count -gt 0
        if ($AllowProtected404Fallback -and $hasProtected404) {
            Write-Host "[WARN] Endpoints protegidos no disponibles en deploy actual (HTTP 404). Sigo con snapshot no estricto."
            & python scripts/build_ops_snapshot.py `
                --base-url $BaseUrl `
                --username $Username `
                --password $adminPass `
                --timeout-sec $TimeoutSec `
                --label ops_block2_snapshot_final_legacy
            if ($LASTEXITCODE -ne 0) {
                throw "build_ops_snapshot fallback fallo (exit $LASTEXITCODE)."
            }
        } else {
            throw "build_ops_snapshot fallo (exit $LASTEXITCODE). Revisar artifacts/ops_block2_snapshot_final_*.json (notes). Si son 404 de endpoints protegidos, correr con -AllowProtected404Fallback."
        }
    }

    Write-Host "3/3 Ejecutando benchmark remoto de /api/v1/bots..."
    $benchArgs = @(
        "scripts/benchmark_bots_overview.py",
        "--base-url", $BaseUrl,
        "--username", $Username,
        "--password", $adminPass,
        "--requests", "$Requests",
        "--warmup", "$Warmup",
        "--timeout-sec", "$TimeoutSec",
        "--min-bots-required", "$MinBotsRequired",
        "--report-path", $benchmarkReport
    )
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
    if ($RequireTargetPass) {
        $benchArgs += "--require-target-pass"
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

    Write-Host "OK: cierre remoto completado."
    Write-Host "Reporte benchmark: $benchmarkReport"
    if (Test-Path -LiteralPath $benchmarkReport) {
        $reportLines = Get-Content -LiteralPath $benchmarkReport
        $edgeLine = ($reportLines | Select-String -Pattern "Railway edge:" -SimpleMatch | Select-Object -First 1).Line
        $stateLine = ($reportLines | Select-String -Pattern "- Estado:" -SimpleMatch | Select-Object -First 1).Line
        if ($edgeLine) { Write-Host $edgeLine }
        if ($stateLine) { Write-Host $stateLine }
    }
}
finally {
    Remove-Variable adminPass -ErrorAction SilentlyContinue
    Pop-Location
}
