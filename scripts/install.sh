#!/usr/bin/env bash
# One-command installer for GeoChip CLI on macOS and Linux.
set -euo pipefail

REPO_URL="git+https://github.com/Anovvy/GeoChip-CLI.git"

echo ""
echo "==============================================="
echo "  GeoChip CLI - macOS / Linux Installer"
echo "==============================================="
echo ""

if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python 3.10+ was not found. Please install Python 3.10+ and retry."
    exit 1
fi

PY_VER="$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_OK="$($PYTHON_CMD -c 'import sys; print(int(sys.version_info >= (3, 10)))')"
if [ "$PY_OK" -ne 1 ]; then
    echo "[ERROR] Python 3.10 or newer is required (detected $PY_VER)."
    exit 1
fi
echo "[OK] Found Python $PY_VER"

if command -v uv >/dev/null 2>&1; then
    echo "[INFO] Installing GeoChip CLI globally with uv..."
    uv tool install --force "$REPO_URL"
elif command -v pipx >/dev/null 2>&1; then
    echo "[INFO] Installing GeoChip CLI globally with pipx..."
    pipx install --force "$REPO_URL"
else
    echo "[INFO] Installing GeoChip CLI with pip (--user)..."
    "$PYTHON_CMD" -m pip install --user --upgrade "$REPO_URL"
    echo "[NOTE] Ensure ~/.local/bin is in your PATH."
fi

echo ""
if command -v GeoChip >/dev/null 2>&1; then
    GeoChip --version
    echo "[SUCCESS] Installation complete! Type 'GeoChip' in any folder to start."
else
    echo "[SUCCESS] Installed! Open a new terminal or add ~/.local/bin to PATH, then run: GeoChip"
fi
