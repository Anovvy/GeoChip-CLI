"""
AGY SDK Senior DevOps PR Reviewer.
Runs after deterministic CI checks pass and reviews the pull request using the
Gemini API Free Tier with automatic 4-tier model fallback on high demand or quota limits.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import requests

MODEL_FALLBACK_CHAIN: tuple[str, ...] = (
    "gemini-4-hydrogen",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
)

COMMENT_MARKER = "<!-- agy-devops-review -->"

RETRYABLE_ERROR_MARKERS = (
    "429",
    "500",
    "503",
    "504",
    "resource_exhausted",
    "unavailable",
    "overloaded",
    "quota",
    "rate limit",
    "rate_limit",
    "too many requests",
    "deadline_exceeded",
    "timed out",
    "timeout",
    "high demand",
    "queue",
    "capacity",
    "connection",
)


def is_retryable_model_error(exc: Exception) -> bool:
    """Return True when an exception indicates API demand, quota exhaustion, or transient failure."""
    msg = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in msg for marker in RETRYABLE_ERROR_MARKERS)


def build_review_prompt(
    diff_text: str,
    agents_md: str,
    pr_title: str,
    pr_body: str,
    changed_files: list[str],
) -> str:
    """Build a project-aware Senior DevOps PR review prompt."""
    files_list = "\n".join(f"- `{f}`" for f in changed_files[:80]) or "- (no files listed)"
    trimmed_diff = diff_text[:40000]
    if len(diff_text) > 40000:
        trimmed_diff += "\n\n... [diff truncated for context budget] ..."

    return f"""You are a Senior DevOps & Geospatial Platform Engineer reviewing a Pull Request for GeoChip CLI.
Deterministic CI checks (lint, unit/integration tests, build, Bandit SAST, CodeQL, pip-audit) have already passed.

Focus your review on high-signal risks relevant to this repository:
1. Repository Governance (`AGENTS.md`):
   - Simple, direct, professional English in code, comments, and docs.
   - Documentation (`README.md`) aligned with feature/CLI/dependency changes.
   - No secrets, tokens, or credentials committed.
2. Geospatial & Earth Engine Reliability:
   - CRS normalization/reprojection safety (projected vs WGS84 coordinates).
   - Safe Earth Engine quota/payload limits and clear user error messages.
3. Packaging, CLI UX & CI/CD Security:
   - `pyproject.toml` dependency hygiene and `GeoChip` entrypoint integrity.
   - Least-privilege GitHub Actions permissions, safe subprocess/network calls, timeout handling.
   - Meaningful test coverage for new or fixed behavior.

## Repository Standards (`AGENTS.md`)
```markdown
{agents_md[:8000]}
```

## Pull Request Metadata
- **Title**: {pr_title}
- **Description**:
{pr_body or "(empty)"}

## Changed Files
{files_list}

## Pull Request Diff
```diff
{trimmed_diff}
```

Respond in concise, direct, professional English using these exact Markdown sections:
### Verdict
One line: `APPROVE WITH NOTES` or `CHANGES REQUESTED` and a 1-sentence summary.
### Blockers
Bullet list of critical bugs, security risks, or standard violations (or `- None`).
### Warnings
Bullet list of reliability, performance, or maintainability concerns (or `- None`).
### Suggestions
Bullet list of concise, actionable improvements (or `- None`).
"""


async def _default_agy_runner(model_id: str, prompt: str, api_key: str, workspace_dir: str) -> str:
    """Execute one review pass via Google Antigravity SDK with read-only tools."""
    from google.antigravity import Agent, LocalAgentConfig, types
    from google.antigravity.hooks import policy

    config = LocalAgentConfig(
        model=model_id,
        api_key=api_key,
        workspaces=[workspace_dir],
        retry_config=types.RetryConfig(
            api_retry=types.ModelAPIRetryConfig(
                max_retries=1,
                initial_sleep_duration_ms=1000,
                exponential_multiplier=2.0,
                jitter_range=0.1,
            )
        ),
        budget_config=types.BudgetConfig(
            max_model_calls=12,
            max_tool_calls=20,
            max_total_tokens=150_000,
        ),
        policies=[
            policy.deny_all(),
            policy.allow("view_file"),
            policy.allow("list_directory"),
            policy.allow("search_directory"),
            policy.allow("find_file"),
        ],
    )

    async with Agent(config=config) as agent:
        response = await agent.chat(prompt)
        return (await response.text()).strip()


async def run_review_with_fallback(
    prompt: str,
    api_key: str,
    workspace_dir: str,
    models: tuple[str, ...] = MODEL_FALLBACK_CHAIN,
    runner: Callable[[str, str, str, str], Awaitable[str]] | None = None,
) -> tuple[str, str]:
    """Run PR review across the ordered Gemini model fallback chain."""
    exec_fn = runner or _default_agy_runner
    errors: list[str] = []

    for model_id in models:
        try:
            print(f"[AGY DevOps Reviewer] Attempting review with model: {model_id}")
            result = await exec_fn(model_id, prompt, api_key, workspace_dir)
            if result:
                print(f"[AGY DevOps Reviewer] Review completed with model: {model_id}")
                return result, model_id
            errors.append(f"{model_id}: empty response returned")
        except Exception as exc:
            err_summary = f"{model_id}: {type(exc).__name__}: {exc}"
            errors.append(err_summary)
            if is_retryable_model_error(exc):
                print(f"[AGY DevOps Reviewer] Model '{model_id}' unavailable/rate-limited; switching to next model...")
                continue
            print(f"[AGY DevOps Reviewer] Model '{model_id}' failed ({exc}); switching to next model...")
            continue

    raise RuntimeError("All Gemini fallback models failed:\n- " + "\n- ".join(errors))


def fetch_pr_context(repo: str, pr_number: int, token: str) -> tuple[str, str, str, list[str]]:
    """Fetch PR metadata, diff, and changed filenames via GitHub REST API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    pr_resp = requests.get(
        f"https://api.github.com/repos/{repo}/pulls/{pr_number}",
        headers={**headers, "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    pr_resp.raise_for_status()
    pr_data = pr_resp.json()

    diff_resp = requests.get(
        f"https://api.github.com/repos/{repo}/pulls/{pr_number}",
        headers={**headers, "Accept": "application/vnd.github.v3.diff"},
        timeout=30,
    )
    diff_resp.raise_for_status()

    files_resp = requests.get(
        f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files?per_page=100",
        headers={**headers, "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    files_resp.raise_for_status()
    changed_files = [item["filename"] for item in files_resp.json()]

    return (
        pr_data.get("title", ""),
        pr_data.get("body", "") or "",
        diff_resp.text,
        changed_files,
    )


def post_or_update_pr_comment(repo: str, pr_number: int, token: str, body: str) -> None:
    """Create or update the single AGY DevOps review comment on the Pull Request."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    comments_url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"

    resp = requests.get(comments_url, headers=headers, params={"per_page": 100}, timeout=30)
    resp.raise_for_status()

    existing_id = None
    for comment in resp.json():
        if COMMENT_MARKER in (comment.get("body") or ""):
            existing_id = comment["id"]
            break

    if existing_id is not None:
        update_url = f"https://api.github.com/repos/{repo}/issues/comments/{existing_id}"
        patch_resp = requests.patch(update_url, headers=headers, json={"body": body}, timeout=30)
        patch_resp.raise_for_status()
        print(f"[AGY DevOps Reviewer] Updated PR comment #{existing_id}.")
    else:
        post_resp = requests.post(comments_url, headers=headers, json={"body": body}, timeout=30)
        post_resp.raise_for_status()
        print(f"[AGY DevOps Reviewer] Posted new PR comment on PR #{pr_number}.")


def main() -> int:
    """CLI entry point for CI execution."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    pr_raw = os.getenv("PR_NUMBER", "").strip()

    if not api_key:
        print("[AGY DevOps Reviewer] GEMINI_API_KEY secret is not configured. Skipping AI PR review.")
        return 0

    if not (token and repo and pr_raw):
        print("[AGY DevOps Reviewer] Missing GITHUB_TOKEN, GITHUB_REPOSITORY, or PR_NUMBER.", file=sys.stderr)
        return 1

    pr_number = int(pr_raw)
    workspace_dir = str(Path.cwd().resolve())
    agents_path = Path(workspace_dir) / "AGENTS.md"
    agents_md = agents_path.read_text(encoding="utf-8") if agents_path.is_file() else ""

    pr_title, pr_body, diff_text, changed_files = fetch_pr_context(repo, pr_number, token)
    prompt = build_review_prompt(diff_text, agents_md, pr_title, pr_body, changed_files)

    review_md, model_used = asyncio.run(
        run_review_with_fallback(
            prompt=prompt,
            api_key=api_key,
            workspace_dir=workspace_dir,
        )
    )

    comment_body = (
        f"{COMMENT_MARKER}\n"
        f"## AGY SDK Senior DevOps PR Review\n\n"
        f"> Reviewed automatically after all CI checks passed using **`{model_used}`**.\n\n"
        f"{review_md}\n"
    )
    post_or_update_pr_comment(repo, pr_number, token, comment_body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
