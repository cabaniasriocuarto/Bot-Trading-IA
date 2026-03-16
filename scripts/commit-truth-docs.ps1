param(
    [string]$RepoPath = "G:\Users\Admin\Desktop\Nueva carpeta\VS Code\Trading IA\Bot-Trading-IA",
    [Parameter(Mandatory = $true)]
    [string]$CommitMessage,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$truthFiles = @(
    "docs/truth/CHANGELOG.md",
    "docs/truth/NEXT_STEPS.md",
    "docs/truth/SOURCE_OF_TRUTH.md"
)

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

$resolvedRepoPath = (Resolve-Path $RepoPath).Path

Push-Location $resolvedRepoPath
try {
    Write-Step "Repo"
    Write-Host "RepoPath: $resolvedRepoPath"

    Write-Step "safe.directory"
    [void](Invoke-GitCapture -Arguments @("config", "--global", "--add", "safe.directory", $resolvedRepoPath) -Mutating)
    if (-not $DryRun) {
        Write-Host "safe.directory agregado para este repo."
    }

    Write-Step "Rama actual"
    $currentBranch = ((Invoke-GitCapture -Arguments @("branch", "--show-current")) -join "").Trim()
    Write-Host "Rama actual: $currentBranch"

    Write-Step "Diff de docs/truth"
    $diffArgs = @("diff", "HEAD", "--") + $truthFiles
    $diffOutput = Invoke-GitCapture -Arguments $diffArgs
    if ($diffOutput.Count -eq 0) {
        Write-Host "No hay cambios contra HEAD en docs/truth permitidos."
        return
    }
    $diffOutput | ForEach-Object { Write-Host $_ }

    Write-Step "Commit de docs/truth"
    [void](Invoke-GitCapture -Arguments (@("add", "--") + $truthFiles) -Mutating)
    [void](Invoke-GitCapture -Arguments @("commit", "-m", $CommitMessage) -Mutating)

    Write-Step "Status final"
    $statusOutput = Invoke-GitCapture -Arguments @("status", "--short")
    if ($statusOutput.Count -eq 0) {
        Write-Host "(sin cambios pendientes)"
    } else {
        $statusOutput | ForEach-Object { Write-Host $_ }
    }
}
finally {
    Pop-Location
}
