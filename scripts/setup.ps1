[CmdletBinding()]
param(
    [string]$PythonExe = "python",
    [switch]$SkipInit
)

if ([IO.Path]::DirectorySeparatorChar -ne [char]'\') {
    throw "setup.ps1 supports Windows only. Run 'bash ./scripts/setup.sh' on Linux or macOS."
}

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

$RepoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "path-guard.ps1")
$RequestedHome = if ([string]::IsNullOrWhiteSpace($env:ADAPTIVE_STUDY_HOME)) {
    "adaptive-study-data"
}
else {
    $env:ADAPTIVE_STUDY_HOME
}
$StudyHome = Get-ConfinedRepositoryPath `
    -RepositoryRoot $RepoRoot `
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

$VenvRoot = Join-Path $StudyHome "runtime\.venv"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
$Requirements = Join-Path $RepoRoot "requirements.txt"
$Launcher = Join-Path $RepoRoot ".agents\skills\adaptive-study-coach\scripts\run-study.ps1"

New-Item -ItemType Directory -Force -Path $env:TEMP, $env:PIP_CACHE_DIR, $env:PYTHONPYCACHEPREFIX | Out-Null

if (-not (Test-Path -LiteralPath $VenvPython)) {
    $PythonCommand = Get-Command $PythonExe -ErrorAction Stop
    & $PythonCommand.Source -m venv $VenvRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the repository-local virtual environment."
    }
}

& $VenvPython -m pip install --requirement $Requirements
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

if (-not $SkipInit) {
    $HealthText = & powershell -NoProfile -ExecutionPolicy Bypass -File $Launcher health
    if ($LASTEXITCODE -ne 0) {
        throw "Health check failed: $HealthText"
    }
    try {
        $Health = $HealthText | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "Health check returned non-JSON output and setup stopped: $HealthText"
    }
    if (-not $Health.initialized) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $Launcher init
        if ($LASTEXITCODE -ne 0) {
            throw "Database initialization failed."
        }
    }
}

Write-Output "Adaptive Study Coach is ready."
Write-Output "Workspace: $RepoRoot"
Write-Output "Data home: $StudyHome"
