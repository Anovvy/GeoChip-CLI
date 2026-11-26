<#
.SYNOPSIS
    One-command installer for GeoChip CLI on Windows.
#>
$ErrorActionPreference = "Stop"

$RepoUrl = "git+https://github.com/Anovvy/GeoChip-CLI.git"

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
    uv tool install --force $RepoUrl
} elseif (Get-Command pipx -ErrorAction SilentlyContinue) {
    Write-Host "[INFO] Installing GeoChip CLI globally with pipx..." -ForegroundColor Cyan
    pipx install --force $RepoUrl
} else {
    Write-Host "[INFO] Installing GeoChip CLI with pip (--user)..." -ForegroundColor Cyan
    & $PythonCmd -m pip install --user --upgrade $RepoUrl
    $UserScripts = & $PythonCmd -c "import site, os; print(os.path.join(site.USER_BASE, 'Scripts'))"
    if ($env:PATH -notlike "*$UserScripts*") {
        Write-Host "[NOTE] Add this folder to your User PATH if 'GeoChip' is not recognized:" -ForegroundColor Yellow
        Write-Host "       $UserScripts"
    }
}

Write-Host ""
if (Get-Command GeoChip -ErrorAction SilentlyContinue) {
    GeoChip --version
    Write-Host "[SUCCESS] Installation complete! Type 'GeoChip' in any folder to start." -ForegroundColor Green
} else {
    Write-Host "[SUCCESS] Installed! Open a new terminal window and run: GeoChip" -ForegroundColor Green
}
