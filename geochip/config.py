"""
GeoChip Configuration and Credentials Management.
Centralizes global credentials (~/.config/geochip/.env), workspace directory resolution,
secret masking, and Roboflow slug parsing.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from dotenv import load_dotenv

GLOBAL_CONFIG_DIR = Path.home() / ".config" / "geochip"
GLOBAL_ENV_FILE = GLOBAL_CONFIG_DIR / ".env"

DUMMY_PLACEHOLDERS = {
    "your_gcp_project_id",
    "your_private_api_key_here",
    "your_workspace_id",
    "your_project_id",
    "none",
    "null",
}


def is_valid_credential_val(val: str | None) -> bool:
    """Return True if value is a real credential rather than an empty or placeholder string."""
    if not val:
        return False
    val_clean = str(val).strip().lower()
    return (
        bool(val_clean)
        and val_clean not in DUMMY_PLACEHOLDERS
        and not val_clean.startswith("your_")
    )


def mask_secret(secret: str | None) -> str:
    """Mask an API key or secret so raw values are never echoed to the terminal."""
    if not secret:
        return ""
    cleaned = str(secret).strip()
    if len(cleaned) <= 8:
        return "****"
    return f"{cleaned[:4]}****{cleaned[-4:]}"


def extract_roboflow_slug(val: str | None) -> str:
    """Clean a full Roboflow URL or path into a bare workspace/project slug."""
    if not val:
        return ""
    cleaned = str(val).strip().rstrip("/")
    if "roboflow.com/" in cleaned:
        cleaned = cleaned.split("roboflow.com/")[-1]
    if "/" in cleaned:
        cleaned = cleaned.split("/")[-1]
    return cleaned.strip()


def resolve_work_dir(work_dir: str | Path | None = None) -> Path:
    """Resolve the active GeoChip workspace root directory."""
    if work_dir is not None:
        return Path(work_dir).expanduser().resolve()
    return Path.cwd().resolve()


def ensure_workspace_dirs(work_dir: Path) -> dict[str, Path]:
    """Ensure data/aoi, data/raw, and data/chips exist inside the workspace."""
    dirs = {
        "aoi": work_dir / "data" / "aoi",
        "raw": work_dir / "data" / "raw",
        "chips": work_dir / "data" / "chips",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def load_app_env(work_dir: Path | None = None) -> None:
    """Load environment variables from local .env (highest priority) and global config."""
    ws = resolve_work_dir(work_dir)
    candidates = [ws / ".env", ws / "data" / ".env", GLOBAL_ENV_FILE]
    for env_path in candidates:
        if env_path.is_file():
            load_dotenv(dotenv_path=str(env_path), override=False)


def save_env_variable(key: str, value: str, work_dir: Path | None = None) -> Path:
    """Persist an environment variable to global config (and existing local .env if present)."""
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    targets = [GLOBAL_ENV_FILE]

    if work_dir is not None:
        local_env = resolve_work_dir(work_dir) / ".env"
        if local_env.is_file():
            targets.append(local_env)

    for env_file in targets:
        env_file.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if not line.startswith(f"{key}="):
                    lines.append(line)
        lines.append(f"{key}={value}")
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if os.name != "nt":
            with contextlib.suppress(OSError):
                env_file.chmod(0o600)

    os.environ[key] = str(value)
    return GLOBAL_ENV_FILE
