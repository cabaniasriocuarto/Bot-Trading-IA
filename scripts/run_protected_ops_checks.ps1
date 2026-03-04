param(
    [string]$BaseUrl = "https://bot-trading-ia-production.up.railway.app",
    [string]$Username = "Wadmin",
    [double]$TimeoutSec = 15.0,
    [string]$AuthToken = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "No se encontro 'python' en PATH."
    }

    $token = [string]$AuthToken
    $adminPass = ""
    if ([string]::IsNullOrWhiteSpace($token)) {
        $adminPass = Read-Host "ADMIN_PASSWORD"
        if ([string]::IsNullOrWhiteSpace($adminPass)) {
            throw "Falta auth: pasar -AuthToken o ingresar ADMIN_PASSWORD."
        }
    }

    $prevToken = $env:RTLAB_AUTH_TOKEN
    $prevPass = $env:RTLAB_PASSWORD
    if (-not [string]::IsNullOrWhiteSpace($token)) {
        $env:RTLAB_AUTH_TOKEN = $token
    } else {
        $env:RTLAB_PASSWORD = $adminPass
    }

    Write-Host "1/2 Verificando storage persistente + G10..."
    & python scripts/check_storage_persistence.py `
        --base-url $BaseUrl `
        --username $Username `
        --timeout-sec $TimeoutSec `
        --require-persistent
    if ($LASTEXITCODE -ne 0) {
        throw "check_storage_persistence fallo (exit $LASTEXITCODE)."
    }

    Write-Host "2/2 Generando snapshot con checks protegidos estrictos..."
    & python scripts/build_ops_snapshot.py `
        --base-url $BaseUrl `
        --username $Username `
        --timeout-sec $TimeoutSec `
        --require-protected `
        --label ops_block2_snapshot_final
    if ($LASTEXITCODE -ne 0) {
        throw "build_ops_snapshot fallo (exit $LASTEXITCODE)."
    }

    Write-Host "OK: checks protegidos completados."
}
finally {
    if ($null -ne $prevToken) { $env:RTLAB_AUTH_TOKEN = $prevToken } else { Remove-Item Env:RTLAB_AUTH_TOKEN -ErrorAction SilentlyContinue }
    if ($null -ne $prevPass) { $env:RTLAB_PASSWORD = $prevPass } else { Remove-Item Env:RTLAB_PASSWORD -ErrorAction SilentlyContinue }
    Remove-Variable adminPass -ErrorAction SilentlyContinue
    Remove-Variable token -ErrorAction SilentlyContinue
    Remove-Variable prevToken -ErrorAction SilentlyContinue
    Remove-Variable prevPass -ErrorAction SilentlyContinue
    Pop-Location
}
