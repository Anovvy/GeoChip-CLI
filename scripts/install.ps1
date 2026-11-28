<#
.SYNOPSIS
    One-command installer for GeoChip CLI on Windows.
#>
$ErrorActionPreference = "Stop"

$PackageName = "geochip"

function Add-ToUserPath {
    param([string]$DirPath)
    if ([string]::IsNullOrWhiteSpace($DirPath) -or -not (Test-Path $DirPath)) {
        return
    }
    $NormalizedTarget = $DirPath.TrimEnd("\")
    $CurrentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $UserEntries = @()
    if (-not [string]::IsNullOrWhiteSpace($CurrentUserPath)) {
        $UserEntries = $CurrentUserPath.Split(";") | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }
    $AlreadyInUserPath = $UserEntries | Where-Object { $_.TrimEnd("\") -ieq $NormalizedTarget }
    if (-not $AlreadyInUserPath) {
        $UpdatedUserPath = (@($UserEntries) + $NormalizedTarget) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $UpdatedUserPath, "User")
        Write-Host "[OK] Added '$NormalizedTarget' to Windows User PATH." -ForegroundColor Green
    }

    $SessionEntries = ($env:PATH -split ";") | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $AlreadyInSession = $SessionEntries | Where-Object { $_.TrimEnd("\") -ieq $NormalizedTarget }
    if (-not $AlreadyInSession) {
        $env:PATH = "$NormalizedTarget;$env:PATH"
    }
}

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "  GeoChip CLI - Windows Installer" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

$PythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCmd = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} else {
    Write-Host "[ERROR] Python 3.10+ was not found on PATH." -ForegroundColor Red
    Write-Host "Install Python from https://www.python.org/downloads/ (check 'Add Python to PATH') and retry."
    exit 1
}

$VerOutput = & $PythonCmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$Parts = $VerOutput.Split(".")
if ([int]$Parts[0] -lt 3 -or ([int]$Parts[0] -eq 3 -and [int]$Parts[1] -lt 10)) {
    Write-Host "[ERROR] Python 3.10 or newer is required (detected $VerOutput)." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Found Python $VerOutput" -ForegroundColor Green

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "[INFO] Installing GeoChip CLI globally with uv..." -ForegroundColor Cyan
    uv tool install --upgrade $PackageName
    Add-ToUserPath (Join-Path $env:USERPROFILE ".local\bin")
} elseif (Get-Command pipx -ErrorAction SilentlyContinue) {
    Write-Host "[INFO] Installing GeoChip CLI globally with pipx..." -ForegroundColor Cyan
    pipx install --force $PackageName
    Add-ToUserPath (Join-Path $env:USERPROFILE ".local\bin")
} else {
    Write-Host "[INFO] Installing GeoChip CLI from PyPI (pip --user)..." -ForegroundColor Cyan
    & $PythonCmd -m pip install --user --upgrade $PackageName
    $UserScripts = & $PythonCmd -c "import sysconfig, site, os; print(sysconfig.get_path('scripts', 'nt_user') or os.path.join(site.USER_BASE, 'Scripts'))"
    Add-ToUserPath $UserScripts
}

Write-Host ""
if (Get-Command GeoChip -ErrorAction SilentlyContinue) {
    GeoChip --version
    Write-Host "[SUCCESS] Installation complete! Run 'GeoChip' or 'geochip' to start." -ForegroundColor Green
} else {
    Write-Host "[SUCCESS] Installed! Open a new terminal window and run: GeoChip" -ForegroundColor Green
}
