param(
    [string]$Repo = "cabaniasriocuarto/Bot-Trading-IA",
    [string]$Ref = "main",
    [string]$BaseUrl = "https://bot-trading-ia-production.up.railway.app",
    [string]$Username = "Wadmin",
    [int]$TimeoutSec = 15,
    [int]$WindowHours = 24,
    [ValidateSet("WARN", "PASS", "ANY")]
    [string]$ExpectG9 = "WARN",
    [switch]$NoStrict,
    [int]$PollSec = 10,
    [int]$WaitMinutes = 15,
    [switch]$AllowWorkflowFailure
)

$ErrorActionPreference = "Stop"

function Resolve-GhPath {
    $cmd = Get-Command gh -ErrorAction SilentlyContinue
    if ($cmd -and -not [string]::IsNullOrWhiteSpace($cmd.Source)) {
        return $cmd.Source
    }
    $candidates = @(
        "C:\Program Files\GitHub CLI\gh.exe",
        "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    throw "No se encontro gh CLI. Instalar GitHub CLI o agregar gh.exe al PATH."
}

function Invoke-GhJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GhPath,
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )
    $raw = & $GhPath @Args
    if ($LASTEXITCODE -ne 0) {
        throw "gh fallo: gh $($Args -join ' ')"
    }
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    return ($raw | ConvertFrom-Json)
}

function Invoke-Gh {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GhPath,
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )
    & $GhPath @Args
    if ($LASTEXITCODE -ne 0) {
        throw "gh fallo: gh $($Args -join ' ')"
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
    $ghPath = Resolve-GhPath
    $strictEnabled = -not $NoStrict.IsPresent
    $strictFlag = if ($strictEnabled) { "true" } else { "false" }
    $failOnWorkflowFailure = -not $AllowWorkflowFailure.IsPresent
    $startUtc = (Get-Date).ToUniversalTime()

    Write-Host "Dispatch workflow Remote Protected Checks (GitHub VM)..."
    Invoke-Gh -GhPath $ghPath -Args @(
        "workflow", "run", "remote-protected-checks.yml",
        "--repo", $Repo,
        "--ref", $Ref,
        "-f", "base_url=$BaseUrl",
        "-f", "username=$Username",
        "-f", "timeout_sec=$TimeoutSec",
        "-f", "window_hours=$WindowHours",
        "-f", "expect_g9=$ExpectG9",
        "-f", "strict=$strictFlag"
    )

    Start-Sleep -Seconds 5

    $run = $null
    for ($i = 0; $i -lt 24; $i++) {
        $runs = Invoke-GhJson -GhPath $ghPath -Args @(
            "run", "list",
            "--repo", $Repo,
            "--workflow", "remote-protected-checks.yml",
            "--branch", $Ref,
            "--event", "workflow_dispatch",
            "--limit", "20",
            "--json", "databaseId,status,conclusion,url,createdAt,headBranch"
        )
        if ($runs) {
            $run = $runs |
                Where-Object { $_.headBranch -eq $Ref } |
                Sort-Object { [DateTime]::Parse($_.createdAt) } -Descending |
                Select-Object -First 1
            if ($run) {
                $runCreated = ([DateTime]::Parse($run.createdAt)).ToUniversalTime()
                if ($runCreated -ge $startUtc.AddMinutes(-2)) {
                    break
                }
                $run = $null
            }
        }
        Start-Sleep -Seconds 5
    }
    if (-not $run) {
        throw "No se encontro run nuevo de remote-protected-checks.yml para ref '$Ref'."
    }

    $runId = [int64]$run.databaseId
    Write-Host ("Run detectado: {0}" -f $runId)

    $deadline = (Get-Date).AddMinutes([Math]::Max(1, $WaitMinutes))
    $view = $null
    while ((Get-Date) -lt $deadline) {
        $view = Invoke-GhJson -GhPath $ghPath -Args @(
            "run", "view", "$runId",
            "--repo", $Repo,
            "--json", "status,conclusion,url,createdAt,updatedAt"
        )
        $status = [string]$view.status
        $conclusion = [string]$view.conclusion
        Write-Host ("Run {0}: status={1} conclusion={2}" -f $runId, $status, $conclusion)
        if ($status -eq "completed") {
            break
        }
        Start-Sleep -Seconds ([Math]::Max(3, $PollSec))
    }

    if (-not $view -or [string]$view.status -ne "completed") {
        throw ("Timeout esperando finalizacion de run {0}." -f $runId)
    }
    if ($failOnWorkflowFailure -and [string]$view.conclusion -ne "success") {
        throw ("Workflow {0} completo con conclusion '{1}'." -f $runId, [string]$view.conclusion)
    }

    $artifactDir = Join-Path $repoRoot ("artifacts/protected_checks_gha_{0}" -f $runId)
    New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
    $artifactName = "protected-checks-$runId"

    Write-Host ("Descargando artifact '{0}'..." -f $artifactName)
    try {
        Invoke-Gh -GhPath $ghPath -Args @(
            "run", "download", "$runId",
            "--repo", $Repo,
            "--name", $artifactName,
            "--dir", $artifactDir
        )
    }
    catch {
        Invoke-Gh -GhPath $ghPath -Args @(
            "run", "download", "$runId",
            "--repo", $Repo,
            "--dir", $artifactDir
        )
    }

    $jsonPattern = "ops_protected_checks_gha_{0}_*.json" -f $runId
    $jsonReport = Get-ChildItem -Path $artifactDir -Recurse -Filter $jsonPattern -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $jsonReport) {
        $jsonReport = Get-ChildItem -Path $artifactDir -Recurse -Filter "ops_protected_checks_gha_*.json" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
    }
    $summaryPath = Join-Path $artifactDir ("protected_checks_summary_{0}.json" -f $runId)
    if (-not $jsonReport) {
        $stdoutLog = Get-ChildItem -Path $artifactDir -Recurse -Filter "protected_checks_stdout.log" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        $errorExcerpt = ""
        if ($stdoutLog) {
            $errorLine = Select-String -Path $stdoutLog.FullName -Pattern "ERROR:|Invalid credentials|Missing staging secrets|401" |
                Select-Object -First 1
            if ($errorLine) {
                $errorExcerpt = [string]$errorLine.Line
            }
        }
        $summary = [ordered]@{
            run_id                     = $runId
            run_url                    = [string]$view.url
            workflow_status            = [string]$view.status
            workflow_conclusion        = [string]$view.conclusion
            base_url                   = [string]$BaseUrl
            overall_pass               = $false
            protected_checks_complete  = $false
            g10_status                 = "NO_EVIDENCE"
            g9_status                  = "NO_EVIDENCE"
            breaker_ok                 = $false
            internal_proxy_status_ok   = $false
            json_report                = ""
            artifact_dir               = [string]$artifactDir
            diagnostic_error_excerpt   = $errorExcerpt
            diagnostic_no_json_report  = $true
        }
        $summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $summaryPath -Encoding UTF8
        Write-Host "Resultado (sin JSON de reporte):"
        Write-Host ("- run_id: {0}" -f $summary.run_id)
        Write-Host ("- run_url: {0}" -f $summary.run_url)
        Write-Host ("- workflow_conclusion: {0}" -f $summary.workflow_conclusion)
        Write-Host ("- diagnostic_error_excerpt: {0}" -f $summary.diagnostic_error_excerpt)
        Write-Host ("- summary_json: {0}" -f $summaryPath)
        exit 3
    }

    $report = Get-Content -LiteralPath $jsonReport.FullName -Raw | ConvertFrom-Json
    $checks = $report.checks

    $summary = [ordered]@{
        run_id                     = $runId
        run_url                    = [string]$view.url
        workflow_status            = [string]$view.status
        workflow_conclusion        = [string]$view.conclusion
        base_url                   = [string]$BaseUrl
        overall_pass               = [bool]$checks.overall_pass
        protected_checks_complete  = [bool]$checks.protected_checks_complete
        g10_status                 = [string]$checks.g10_status
        g9_status                  = [string]$checks.g9_status
        breaker_ok                 = [bool]$checks.breaker_ok
        internal_proxy_status_ok   = [bool]$checks.internal_proxy_status_ok
        json_report                = [string]$jsonReport.FullName
        artifact_dir               = [string]$artifactDir
    }

    $summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $summaryPath -Encoding UTF8

    Write-Host "Resultado:"
    Write-Host ("- run_id: {0}" -f $summary.run_id)
    Write-Host ("- run_url: {0}" -f $summary.run_url)
    Write-Host ("- overall_pass: {0}" -f $summary.overall_pass)
    Write-Host ("- protected_checks_complete: {0}" -f $summary.protected_checks_complete)
    Write-Host ("- g10_status: {0}" -f $summary.g10_status)
    Write-Host ("- g9_status: {0}" -f $summary.g9_status)
    Write-Host ("- breaker_ok: {0}" -f $summary.breaker_ok)
    Write-Host ("- internal_proxy_status_ok: {0}" -f $summary.internal_proxy_status_ok)
    Write-Host ("- summary_json: {0}" -f $summaryPath)

    if ($strictEnabled -and -not [bool]$checks.overall_pass) {
        exit 2
    }
    exit 0
}
finally {
    Pop-Location
}
