#!/usr/bin/env bash
# One-command installer for GeoChip CLI on macOS and Linux.
set -euo pipefail

PACKAGE_NAME="geochip"

add_to_path() {
    local target_dir="$1"
    if [ -z "$target_dir" ] || [ ! -d "$target_dir" ]; then
        return
    fi

    case ":$PATH:" in
        *":$target_dir:"*) ;;
        *)
            export PATH="$target_dir:$PATH"
            local profile_file="$HOME/.profile"
            local login_shell
            login_shell="$(basename "${SHELL:-}")"
            if [ "$login_shell" = "zsh" ] || [ -n "${ZSH_VERSION:-}" ] || [ "$(uname -s)" = "Darwin" ]; then
                profile_file="$HOME/.zshrc"
            elif [ -f "$HOME/.bashrc" ]; then
                profile_file="$HOME/.bashrc"
            fi
            if ! grep -Fq "$target_dir" "$profile_file" 2>/dev/null; then
                printf '\nexport PATH="%s:$PATH"\n' "$target_dir" >> "$profile_file"
                echo "[OK] Added '$target_dir' to PATH in $profile_file"
            fi
            ;;
    esac
}

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
    uv tool install --upgrade "$PACKAGE_NAME"
    UV_BIN_DIR="$(uv tool dir --bin 2>/dev/null || printf '%s' "${XDG_BIN_HOME:-$HOME/.local/bin}")"
    add_to_path "$UV_BIN_DIR"
elif command -v pipx >/dev/null 2>&1; then
    echo "[INFO] Installing GeoChip CLI globally with pipx..."
    pipx install --force "$PACKAGE_NAME"
    add_to_path "${PIPX_BIN_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}"
else
    echo "[INFO] Installing GeoChip CLI from PyPI (pip --user)..."
    "$PYTHON_CMD" -m pip install --user --upgrade "$PACKAGE_NAME"
    USER_SCRIPTS="$($PYTHON_CMD -c "import sysconfig, site, os; print(sysconfig.get_path('scripts', 'posix_user') or os.path.join(site.USER_BASE, 'bin'))")"
    add_to_path "$USER_SCRIPTS"
fi

echo ""
if command -v GeoChip >/dev/null 2>&1; then
    GeoChip --version
    echo "[SUCCESS] Installation complete! Run 'GeoChip' or 'geochip' to start."
else
    echo "[SUCCESS] Installed! Open a new terminal window and run: GeoChip"
fi
