param(
    [string]$RepoPath = "G:\Users\Admin\Desktop\Nueva carpeta\VS Code\Trading IA\Bot-Trading-IA",
    [Parameter(Mandatory = $true)]
    [string]$NewBranch,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Join-GitArguments {
    param([string[]]$Arguments)

    $escaped = foreach ($argument in $Arguments) {
        if ($null -eq $argument) {
            '""'
        } elseif ($argument -match '[\s"]') {
            '"' + ($argument -replace '"', '\"') + '"'
        } else {
            $argument
        }
    }
    return ($escaped -join " ")
}

function Split-ProcessOutput {
    param([string]$Text)

    if ([string]::IsNullOrEmpty($Text)) {
        return @()
    }

    $lines = @($Text -split "\r?\n", -1)
    if ($lines.Count -gt 0 -and $lines[-1] -eq "") {
        $lines = @($lines[0..($lines.Count - 2)])
    }
    return $lines
}

function Invoke-GitCapture {
    param(
        [string[]]$Arguments,
        [switch]$Mutating
    )

    $argumentString = Join-GitArguments -Arguments $Arguments
    $display = "git $argumentString"
    if ($DryRun -and $Mutating) {
        Write-Host "[DryRun] $display" -ForegroundColor Yellow
        return @()
    }

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "git"
    $startInfo.Arguments = $argumentString
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    $output = @()
    $output += Split-ProcessOutput -Text $stdout
    $output += Split-ProcessOutput -Text $stderr

    if ($process.ExitCode -ne 0) {
        $detail = ($output | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($detail)) {
            throw "Fallo el comando: $display (exit $($process.ExitCode))."
        }
        throw "Fallo el comando: $display (exit $($process.ExitCode)).`n$detail"
    }
    return $output
}

function Show-Status {
    $statusLines = Invoke-GitCapture -Arguments @("status", "--short", "--branch")
    if ($statusLines.Count -eq 0) {
        Write-Host "(sin salida de git status)"
    } else {
        $statusLines | ForEach-Object { Write-Host $_ }
    }
    return @($statusLines)
}

function Split-StatusOutput {
    param([string[]]$StatusLines)

    $warningLines = @($StatusLines | Where-Object { $_ -match "^warning:" })
    $effectiveLines = @($StatusLines | Where-Object { $_ -and $_ -notmatch "^warning:" })
    return @{
        Warnings = $warningLines
        Effective = $effectiveLines
    }
}

$resolvedRepoPath = (Resolve-Path $RepoPath).Path

Push-Location $resolvedRepoPath
try {
    Write-Step "Repo"
    Write-Host "RepoPath: $resolvedRepoPath"

    Write-Step "safe.directory"
    $safeDirectoryArgs = @("config", "--global", "--add", "safe.directory", $resolvedRepoPath)
    [void](Invoke-GitCapture -Arguments $safeDirectoryArgs -Mutating)
    if (-not $DryRun) {
        Write-Host "safe.directory agregado para este repo."
    }

    Write-Step "Estado actual"
    $currentBranch = ((Invoke-GitCapture -Arguments @("branch", "--show-current")) -join "").Trim()
    Write-Host "Rama actual: $currentBranch"
    $statusLines = Show-Status
    $statusSplit = Split-StatusOutput -StatusLines $statusLines
    $effectiveStatus = @($statusSplit.Effective)

    $branchExists = $false
    try {
        [void](Invoke-GitCapture -Arguments @("show-ref", "--verify", "--quiet", "refs/heads/$NewBranch"))
        $branchExists = $true
    } catch {
        $branchExists = $false
    }
    if ($branchExists) {
        throw "La rama '$NewBranch' ya existe. Elegi otro nombre o borrala primero."
    }

    if ($effectiveStatus.Count -gt 1 -or ($effectiveStatus.Count -eq 1 -and $effectiveStatus[0] -notmatch "^## ")) {
        $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $stashMessage = "wip/auto-before-$NewBranch-$timestamp"
        Write-Step "Cambios locales detectados"
        Write-Host "Se va a generar stash: $stashMessage"
        [void](Invoke-GitCapture -Arguments @("stash", "push", "-u", "-m", $stashMessage) -Mutating)
    } else {
        Write-Step "Cambios locales"
        Write-Host "No hay cambios locales para stashear."
    }

    Write-Step "Cambio a main"
    [void](Invoke-GitCapture -Arguments @("switch", "main") -Mutating)

    Write-Step "Actualizacion de main"
    [void](Invoke-GitCapture -Arguments @("pull", "--ff-only") -Mutating)

    Write-Step "Creacion de rama"
    [void](Invoke-GitCapture -Arguments @("switch", "-c", $NewBranch) -Mutating)

    Write-Step "Estado final"
    if ($DryRun) {
        Write-Host "Rama final esperada: $NewBranch"
        Write-Host "Status final esperado: rama nueva creada desde main actualizado."
    } else {
        $finalBranch = ((Invoke-GitCapture -Arguments @("branch", "--show-current")) -join "").Trim()
        Write-Host "Rama final: $finalBranch"
        [void](Show-Status)
    }
}
finally {
    Pop-Location
}
