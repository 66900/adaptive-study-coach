function Test-PathIsReparsePoint {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][System.IO.FileSystemInfo]$Item
    )

    if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        return $true
    }
    $LinkTypeProperty = $Item.PSObject.Properties["LinkType"]
    return $null -ne $LinkTypeProperty -and -not [string]::IsNullOrWhiteSpace(
        [string]$LinkTypeProperty.Value
    )
}


function Get-PathComparison {
    if ([IO.Path]::DirectorySeparatorChar -eq [char]'\') {
        return [StringComparison]::OrdinalIgnoreCase
    }
    return [StringComparison]::Ordinal
}


function Get-ConfinedRepositoryPath {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string]$Candidate,
        [string]$Label = "Path"
    )

    $RootFull = [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd("\", "/")
    if (-not (Test-Path -LiteralPath $RootFull -PathType Container)) {
        throw "$Label repository root does not exist or is not a directory: $RootFull"
    }
    $RootItem = Get-Item -LiteralPath $RootFull -Force
    if (Test-PathIsReparsePoint -Item $RootItem) {
        throw "$Label repository root is a symbolic link or junction and was rejected: $RootFull"
    }
    if ([IO.Path]::IsPathRooted($Candidate)) {
        $CandidateFull = [IO.Path]::GetFullPath($Candidate)
    }
    else {
        $CandidateFull = [IO.Path]::GetFullPath((Join-Path $RootFull $Candidate))
    }
    $Prefix = $RootFull + [IO.Path]::DirectorySeparatorChar
    $Comparison = Get-PathComparison
    if (
        $CandidateFull.Equals($RootFull, $Comparison) -or
        -not $CandidateFull.StartsWith($Prefix, $Comparison)
    ) {
        throw "$Label must be a child of the repository: $RootFull"
    }

    $Relative = $CandidateFull.Substring($Prefix.Length)
    $Current = $RootFull
    foreach ($Part in $Relative.Split([IO.Path]::DirectorySeparatorChar)) {
        if ([string]::IsNullOrWhiteSpace($Part)) {
            continue
        }
        $Current = Join-Path $Current $Part
        if (-not (Test-Path -LiteralPath $Current)) {
            break
        }
        $Item = Get-Item -LiteralPath $Current -Force
        if (Test-PathIsReparsePoint -Item $Item) {
            throw "$Label contains a symbolic link or junction and was rejected: $Current"
        }
    }
    return $CandidateFull
}


function Write-JsonFailure {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [string]$ErrorType = "LauncherError",
        [string]$Action = "Run the repository setup script."
    )

    [pscustomobject]@{
        ok = $false
        error = $Message
        error_type = $ErrorType
        action = $Action
    } | ConvertTo-Json -Compress
}
