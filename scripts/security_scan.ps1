param(
    [switch]$Strict,
    [string]$PythonBin = "python",
    [string]$OutDir = "artifacts/security_audit"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

    function Test-CommandExists {
        param([string]$Name)
        return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
    }

    function Invoke-PipAudit {
        param(
            [string]$ReqFile,
            [string]$OutFile
        )
        if (-not (Test-Path -LiteralPath $ReqFile)) {
            Write-Host "[security][SKIP] $ReqFile no existe."
            return 0
        }

        $supportsModule = $false
        try {
            & $PythonBin -m pip_audit --version *> $null
            if ($LASTEXITCODE -eq 0) {
                $supportsModule = $true
            }
        } catch {
            $supportsModule = $false
        }

        if ($supportsModule) {
            Write-Host "[security] pip-audit module -> $ReqFile"
            & $PythonBin -m pip_audit -r $ReqFile -f json -o $OutFile
            return $LASTEXITCODE
        }

        if (Test-CommandExists "pip-audit") {
            Write-Host "[security] pip-audit CLI -> $ReqFile"
            & pip-audit -r $ReqFile -f json -o $OutFile
            return $LASTEXITCODE
        }

        Write-Host "[security][WARN] pip-audit no instalado."
        return 2
    }

    Write-Host "[security] root=$repoRoot"
    Write-Host "[security] python=$PythonBin"

    $auditStatus = 0
    $r1 = Invoke-PipAudit -ReqFile "requirements-runtime.txt" -OutFile (Join-Path $OutDir "pip-audit-runtime.json")
    if ($r1 -ne 0) { $auditStatus = $r1 }
    $r2 = Invoke-PipAudit -ReqFile "requirements-research.txt" -OutFile (Join-Path $OutDir "pip-audit-research.json")
    if ($r2 -ne 0) { $auditStatus = $r2 }

    $gitleaksStatus = 0
    $baseline = Join-Path $OutDir "gitleaks-baseline.json"
    $sarif = Join-Path $OutDir "gitleaks.sarif"
    if (Test-CommandExists "gitleaks") {
        if (Test-Path -LiteralPath $baseline) {
            Write-Host "[security] gitleaks baseline-aware: $baseline"
            & gitleaks git --redact --baseline-path $baseline --report-format sarif --report-path $sarif
            $gitleaksStatus = $LASTEXITCODE
        } else {
            Write-Host "[security] gitleaks strict (sin baseline)"
            & gitleaks git --redact --report-format sarif --report-path $sarif
            $gitleaksStatus = $LASTEXITCODE
        }
    } else {
        if ($Strict) {
            Write-Host "[security][ERROR] gitleaks no instalado (modo estricto)."
            $gitleaksStatus = 2
        } else {
            Write-Host "[security][WARN] gitleaks no instalado."
            $gitleaksStatus = 0
        }
    }

    if ($auditStatus -eq 2 -and -not $Strict) {
        Write-Host "[security][WARN] pip-audit no disponible (modo no estricto)."
        $auditStatus = 0
    }

    if ($auditStatus -ne 0) {
        Write-Host "[security][ERROR] pip-audit fallo codigo=$auditStatus"
    }
    if ($gitleaksStatus -ne 0) {
        Write-Host "[security][ERROR] gitleaks fallo codigo=$gitleaksStatus"
    }

    if ($auditStatus -ne 0 -or $gitleaksStatus -ne 0) {
        exit 1
    }
    Write-Host "[security] OK"
}
finally {
    Pop-Location
}
