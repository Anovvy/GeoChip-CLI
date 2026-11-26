"""
Offline tests for the AGY SDK Senior DevOps PR Reviewer fallback logic.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

REVIEWER_PATH = (
    Path(__file__).resolve().parent.parent / ".github" / "scripts" / "devops_pr_reviewer.py"
)


def _load_reviewer_module():
    spec = importlib.util.spec_from_file_location("devops_pr_reviewer", REVIEWER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_fallback_model_chain_order() -> None:
    """Fallback order must match AGENTS.md specification exactly."""
    mod = _load_reviewer_module()
    assert mod.MODEL_FALLBACK_CHAIN == (
        "gemini-4-hydrogen",
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
    )


def test_fallback_switches_through_all_tiers_on_high_demand() -> None:
    """Simulate 429, 503, and quota exhaustion until gemini-3.5-flash-lite succeeds."""
    mod = _load_reviewer_module()
    attempted: list[str] = []

    async def fake_runner(model_id: str, prompt: str, api_key: str, workspace_dir: str) -> str:
        attempted.append(model_id)
        if model_id == "gemini-4-hydrogen":
            raise RuntimeError("429 RESOURCE_EXHAUSTED: high demand")
        if model_id == "gemini-3.8-flash":
            raise RuntimeError("503 UNAVAILABLE: queue full")
        if model_id == "gemini-3.6-flash":
            raise RuntimeError("Quota exceeded for free tier")
        return "### Verdict\nAPPROVE WITH NOTES"

    review_md, used_model = asyncio.run(
        mod.run_review_with_fallback(
            prompt="Review diff",
            api_key="test-key",
            workspace_dir=".",
            runner=fake_runner,
        )
    )

    assert attempted == [
        "gemini-4-hydrogen",
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
    ]
    assert used_model == "gemini-3.5-flash-lite"
    assert "APPROVE WITH NOTES" in review_md


def test_fallback_raises_when_all_models_fail() -> None:
    """If every model fails, run_review_with_fallback must raise RuntimeError with details."""
    mod = _load_reviewer_module()

    async def failing_runner(model_id: str, prompt: str, api_key: str, workspace_dir: str) -> str:
        raise RuntimeError(f"503 unavailable on {model_id}")

    with pytest.raises(RuntimeError, match="All Gemini fallback models failed"):
        asyncio.run(
            mod.run_review_with_fallback(
                prompt="Review diff",
                api_key="test-key",
                workspace_dir=".",
                runner=failing_runner,
            )
        )


def test_fallback_switches_on_model_timeout() -> None:
    """If a model hangs past per_model_timeout, switch immediately to the next model."""
    mod = _load_reviewer_module()
    attempted: list[str] = []

    async def slow_first_runner(
        model_id: str, prompt: str, api_key: str, workspace_dir: str
    ) -> str:
        attempted.append(model_id)
        if model_id == "gemini-4-hydrogen":
            await asyncio.sleep(0.5)
        return "### Verdict\nAPPROVE WITH NOTES"

    review_md, used_model = asyncio.run(
        mod.run_review_with_fallback(
            prompt="Review diff",
            api_key="test-key",
            workspace_dir=".",
            runner=slow_first_runner,
            per_model_timeout=0.05,
        )
    )

    assert attempted == ["gemini-4-hydrogen", "gemini-3.8-flash"]
    assert used_model == "gemini-3.8-flash"
    assert "APPROVE WITH NOTES" in review_md
