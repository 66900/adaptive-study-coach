[CmdletBinding()]
param(
    [string]$RepositoryRoot
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
}
. (Join-Path $PSScriptRoot "path-guard.ps1")

function Assert-PathRejected {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Operation,
        [Parameter(Mandatory = $true)][string]$ExpectedPattern
    )

    try {
        & $Operation | Out-Null
    }
    catch {
        if ($_.Exception.Message -notmatch $ExpectedPattern) {
            throw
        }
        return
    }
    throw "Expected path rejection matching '$ExpectedPattern', but the operation succeeded."
}

$RepoFull = [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd("\", "/")
$TestRoot = Join-Path $RepoFull (".path-guard-test-" + [Guid]::NewGuid().ToString("N"))
$Workspace = Join-Path $TestRoot "workspace"
$Outside = Join-Path $TestRoot "outside"
$Child = Join-Path $Workspace "safe-child"
$Link = Join-Path $Workspace "linked"
$RootLink = Join-Path $TestRoot "root-link"

try {
    New-Item -ItemType Directory -Path $Child, $Outside -Force | Out-Null

    $Safe = Get-ConfinedRepositoryPath `
        -RepositoryRoot $Workspace `
        -Candidate $Child `
        -Label "Safe path"
    if ($Safe -ne [IO.Path]::GetFullPath($Child)) {
        throw "Safe child path was not normalized correctly."
    }

    Assert-PathRejected `
        -ExpectedPattern "must be a child" `
        -Operation {
            Get-ConfinedRepositoryPath `
                -RepositoryRoot $Workspace `
                -Candidate (Join-Path (Join-Path $Workspace "..") "outside") `
                -Label "Traversal path"
        }

    Assert-PathRejected `
        -ExpectedPattern "must be a child" `
        -Operation {
            Get-ConfinedRepositoryPath `
                -RepositoryRoot $Workspace `
                -Candidate $Outside `
                -Label "Absolute outside path"
        }

    if ([IO.Path]::DirectorySeparatorChar -eq [char]'\') {
        New-Item -ItemType Junction -Path $Link -Target $Outside | Out-Null
        Assert-PathRejected `
            -ExpectedPattern "symbolic link or junction" `
            -Operation {
                Get-ConfinedRepositoryPath `
                    -RepositoryRoot $Workspace `
                    -Candidate (Join-Path $Link "escape") `
                    -Label "Junction path"
            }

        New-Item -ItemType Junction -Path $RootLink -Target $Workspace | Out-Null
        Assert-PathRejected `
            -ExpectedPattern "repository root is a symbolic link or junction" `
            -Operation {
                Get-ConfinedRepositoryPath `
                    -RepositoryRoot $RootLink `
                    -Candidate (Join-Path $RootLink "safe-child") `
                    -Label "Linked root"
            }
    }

    Write-Output "POWERSHELL_PATH_GUARD=PASS"
}
finally {
    if (Test-Path -LiteralPath $Link) {
        [IO.Directory]::Delete($Link, $false)
    }
    if (Test-Path -LiteralPath $RootLink) {
        [IO.Directory]::Delete($RootLink, $false)
    }
    $Comparison = Get-PathComparison
    $Prefix = $RepoFull + [IO.Path]::DirectorySeparatorChar
    $ResolvedTestRoot = [IO.Path]::GetFullPath($TestRoot)
    if (-not $ResolvedTestRoot.StartsWith($Prefix, $Comparison)) {
        throw "Test cleanup target escaped the repository."
    }
    if (Test-Path -LiteralPath $TestRoot) {
        Remove-Item -LiteralPath $TestRoot -Recurse -Force
    }
}
