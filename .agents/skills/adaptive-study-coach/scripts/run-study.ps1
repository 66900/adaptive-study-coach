param()

$ErrorActionPreference = "Stop"
$StudyArgs = @($args)

try {
    $SkillRoot = Split-Path -Parent $PSScriptRoot
    $WorkspaceRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $SkillRoot))
    $PathGuard = Join-Path $WorkspaceRoot "scripts\path-guard.ps1"
    if (-not (Test-Path -LiteralPath $PathGuard -PathType Leaf)) {
        throw "Repository path guard is missing: $PathGuard"
    }
    . $PathGuard
    if ([IO.Path]::DirectorySeparatorChar -ne [char]'\') {
        throw "run-study.ps1 supports Windows only. Use run-study.sh on Linux or macOS."
    }
    [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $OutputEncoding = [Console]::OutputEncoding

    $RequestedHome = if ([string]::IsNullOrWhiteSpace($env:ADAPTIVE_STUDY_HOME)) {
        "adaptive-study-data"
    }
    else {
        $env:ADAPTIVE_STUDY_HOME
    }
    $StudyHome = Get-ConfinedRepositoryPath `
        -RepositoryRoot $WorkspaceRoot `
        -Candidate $RequestedHome `
        -Label "ADAPTIVE_STUDY_HOME"
    $CacheRoot = Join-Path $StudyHome "cache"

    $env:TEMP = Join-Path $CacheRoot "temp"
    $env:TMP = $env:TEMP
    $env:PIP_CACHE_DIR = Join-Path $CacheRoot "pip"
    $env:PYTHONPYCACHEPREFIX = Join-Path $CacheRoot "pycache"
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONWARNINGS = "ignore"
    $env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

    $Python = Join-Path $StudyHome "runtime\.venv\Scripts\python.exe"
    $Manager = Join-Path $PSScriptRoot "study_coach.py"
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        Write-JsonFailure `
            -Message "Local Python runtime is missing: $Python" `
            -ErrorType "RuntimeMissing"
        exit 2
    }

    New-Item -ItemType Directory -Force `
        -Path $env:TEMP, $env:PIP_CACHE_DIR, $env:PYTHONPYCACHEPREFIX | Out-Null
    & $Python $Manager --home $StudyHome @StudyArgs
    exit $LASTEXITCODE
}
catch {
    Write-JsonFailure `
        -Message $_.Exception.Message `
        -ErrorType $_.Exception.GetType().Name `
        -Action "Fix the repository-local path or rerun setup."
    exit 2
}
