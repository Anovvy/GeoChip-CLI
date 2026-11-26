# Engineering & Agent Governance (`AGENTS.md`)

All contributors, automated CI agents, Lead Agents, and Sub-Agents operating on **GeoChip CLI** must follow these 10 standards.

---

## 1. Approval for Improvisations
- Do **not** improvise unilaterally when encountering errors, blockers, missing tools, or requirements outside the Project Owner's instructions.
- Stop immediately and report:
  1. The exact technical issue or blocker.
  2. Proposed options/solutions and their impact.
- Wait for explicit Project Owner confirmation before proceeding.

## 2. Initial Multi-Agent Planning Only
- Defining the Sub-Agent roster, job descriptions, and collaboration workflow diagram is performed **once during initial project planning** (not repeated in daily workflows).
- For **GeoChip CLI**, the established team structure is:
  - **Project Owner (Human)**: Approves plans, improvisations, and `git push`; manages sensitive assets (API keys, OAuth, GitHub Secrets, environment approvals, repository settings); performs manual testing; **sole authority to merge PRs into `main`**.
  - **Lead Agent (Coordinator)**: Evaluates tasks, coordinates Sub-Agents, enforces standards, opens PRs.
  - **Sub-Agents**: `geospatial-engineer` (CRS, GEE, datasets, tiler), `cli-ux-engineer` (CLI, UI, auth, packaging, installers), `devops-ci-engineer` (CI/CD, SAST/SCA, AGY SDK PR reviewer), `qa-docs-engineer` (tests, README, CHANGELOG, English audit).

## 3. Smart Delegation & Single Point of Contact
- On every prompt from the Project Owner, the **Lead Agent** evaluates whether to handle the task directly or delegate it to one or more Sub-Agents according to their initial job descriptions.
- **Only the Lead Agent communicates with the Project Owner.** Sub-Agents report strictly to the Lead Agent.
- Sensitive operations (API keys, authentication, secrets, manual testing, production approvals) are always escalated by the Lead Agent to the Project Owner.

## 4. Simple, Direct & Professional English Policy
- All source code, docstrings, comments, commit messages, Pull Request titles/descriptions, issues, `README.md`, `CHANGELOG.md`, `AGENTS.md`, and CI/CD bot comments pushed to GitHub must be written in **simple, direct, and professional English**.

## 5. Atomic Commits & Push Governance
- Every commit must represent **one atomic, logical change**.
- Use Conventional Commits (`<type>(<scope>): <concise summary>`) in the subject line (`feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `ci`, `chore`).
- Every commit body must use **bullet points** covering:
  - Summary of changes
  - Motivation / context
  - Affected components / files
- Agents may create atomic `git commit`s on working branches.
- Agents **must ask the Project Owner for confirmation before running `git push`**.
- **Direct pushes to `main` or `master` are strictly forbidden.**

## 6. Branching & Merge Governance
- All changes must be developed on dedicated branches (`feat/*`, `fix/*`, `refactor/*`, `ci/*`, `docs/*`) and submitted as Pull Requests targeting `main`.
- **ONLY the Project Owner** may merge Pull Requests into `main` or `master`.

## 7. Semantic Versioning (`vMAJOR.MINOR.PATCH`) & Automated `CHANGELOG.md`
- Releases must strictly follow Semantic Versioning (`vMAJOR.MINOR.PATCH`):
  - `MAJOR`: incompatible breaking changes
  - `MINOR`: backward-compatible new features
  - `PATCH`: backward-compatible bug fixes
- Package versions in `pyproject.toml` and `geochip/__init__.py` must match the release tag.
- `CHANGELOG.md` follows Keep a Changelog and is updated automatically on every release tag via `git-cliff` (`cliff.toml`).

## 8. CI Pipeline Standards (PR Trigger)
- Triggered automatically when a Pull Request targeting `main` is opened or updated.
- Required deterministic stages (tailored per project stack):
  1. Linting & formatting (`ruff check`, `ruff format --check`)
  2. Unit & integration tests (`pytest` across supported Python versions)
  3. Test build & CLI smoke test (`python -m build`, `twine check`, entrypoint check)
  4. SAST (`bandit`, CodeQL)
  5. Dependency vulnerability scanning (`pip-audit`)
  6. Container linting & scanning (*conditional — only when the project uses containers*)
- **AGY SDK Senior DevOps PR Reviewer** (runs **only after** all deterministic stages pass):
  - Uses `google-antigravity` SDK with the Gemini API Free Tier (`GEMINI_API_KEY`).
  - Automatic fallback chain when a model errors, queues, hits rate limits, or runs out of capacity/quota:
    1. `gemini-4-hydrogen`
    2. `gemini-3.8-flash`
    3. `gemini-3.6-flash`
    4. `gemini-3.5-flash-lite`
  - Dynamically evaluates project-specific DevOps, security, architecture, and code quality risks, then posts a structured review comment on the Pull Request.

## 9. CD Pipeline Standards (Release Tag Trigger)
- Triggered automatically on every new SemVer release tag (`v*.*.*`):
  1. Validate SemVer tag & version alignment, build `dist/` bundle + SHA256 checksums, and generate `CHANGELOG.md` release notes.
  2. Deploy **Canary** (GitHub Pre-Release + optional TestPyPI for CLI packages; or Canary URL for web apps).
  3. Pause for **Manual Review & Approval** by the Project Owner (`environment: production`).
  4. Promote the verified build to **Production** (GitHub Production Release + optional PyPI) and open a PR updating `CHANGELOG.md`.

## 10. Documentation Alignment
- Whenever features, CLI commands, architecture, dependencies, workflows, or repository structure change, update `README.md` and related documentation in the same Pull Request so documentation always stays accurate.
