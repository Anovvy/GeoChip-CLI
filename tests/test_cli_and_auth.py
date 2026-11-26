"""
Offline tests for GeoChip CLI entrypoints, configuration, and secret masking.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from geochip import __version__, config
from geochip.cli import build_parser


def test_cli_parser_and_module_help() -> None:
    """CLI parser and module invocation should expose GeoChip CLI v3.0.0 and help."""
    parser = build_parser()
    assert parser.prog == "GeoChip"

    help_res = subprocess.run(
        [sys.executable, "-m", "geochip.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert help_res.returncode == 0
    assert "geochip" in help_res.stdout.lower()

    ver_res = subprocess.run(
        [sys.executable, "-m", "geochip.cli", "--version"],
        capture_output=True,
        text=True,
    )
    assert ver_res.returncode == 0
    assert f"GeoChip CLI {__version__}" in ver_res.stdout


def test_mask_secret_never_exposes_raw_key() -> None:
    """Secret masker should obscure the middle of long keys and all of short keys."""
    assert config.mask_secret("") == ""
    assert config.mask_secret("short") == "****"
    masked = config.mask_secret("rf_secret_token_987654")
    assert masked == "rf_s****7654"
    assert "secret_token" not in masked


def test_extract_roboflow_slug() -> None:
    """Roboflow URLs and trailing slashes should normalize to clean slugs."""
    assert config.extract_roboflow_slug("https://app.roboflow.com/my-ws/my-proj/") == "my-proj"
    assert config.extract_roboflow_slug("  my-workspace  ") == "my-workspace"
    assert config.extract_roboflow_slug(None) == ""


def test_save_and_load_env_isolated(tmp_path: Path, monkeypatch) -> None:
    """save_env_variable should write to isolated global config without leaking."""
    fake_dir = tmp_path / "global_cfg"
    fake_env = fake_dir / ".env"
    monkeypatch.setattr(config, "GLOBAL_CONFIG_DIR", fake_dir)
    monkeypatch.setattr(config, "GLOBAL_ENV_FILE", fake_env)
    monkeypatch.delenv("GEOCHIP_TEST_KEY", raising=False)

    saved_path = config.save_env_variable("GEOCHIP_TEST_KEY", "abc123")
    assert saved_path == fake_env
    assert "GEOCHIP_TEST_KEY=abc123" in fake_env.read_text(encoding="utf-8")
    assert os.environ["GEOCHIP_TEST_KEY"] == "abc123"
