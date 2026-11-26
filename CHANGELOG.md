# Changelog

All notable changes to GeoChip CLI are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [3.0.0] - 2026-11-26

### Bug Fixes

- keep SHA256SUMS outside dist/ for PyPI and scope changelog PR path (9380e13)
- add per-model timeout, fail-fast fallback, and finish policy for AGY PR reviewer (749a934)
- resolve CodeQL URL parsing and clear-text secret logging alerts (71174e9)
- handle ESRI WKT1 WGS84 equivalence and affine matmul (d3c431a)
- auto-reproject AOI CRS, support GeoJSON, and optimize GEE queries (4156975)

### CI/CD

- isolate pip-audit in clean Python 3.12 venv with --skip-editable (2e70b76)
- add PR security gates, AGY SDK DevOps reviewer, and SemVer CD workflow (1b73559)

### Documentation

- remove unnecessary overview and highlight lines (1ab228c)
- add AGENTS.md, CHANGELOG.md, hero banner GIF, and v3.0.0 README (e0eaba4)

### Features

- rebrand to GeoChip CLI v3.0.0 with native entrypoints and beginner UX (3dedd47)
- add automated Docker runner, in-place UI re-rendering, robust auth handling, and server-side GEE compositing (6d1155a)
- add Docker containerization, CI/CD, interactive terminal auth setup, and internationalize to English (ae82ba7)
- refactor pipeline to multi-satellite ingestion, single-raster chipping, and interactive CLI v2.0 (8c72b7e)
- initial commit for GeoChip satellite ingestion and paired chipping pipeline (a692691)

### Refactoring

- remove Docker runtime and legacy root wrapper scripts (d9bb7ae)

### Testing

- add offline unit and regression tests for GeoChip CLI (ecaef92)

### Build

- bump actions/download-artifact from 4 to 8 (928b0fd)
- bump actions/upload-artifact from 4 to 7 (fba87ae)
- bump actions/setup-python from 5 to 7 (7717f69)
- bump peter-evans/create-pull-request from 7 to 8 (f9d9abb)
- bump softprops/action-gh-release from 2 to 3 (6e50950)

### Style

- apply Ruff formatting across CLI, downloader, and CI scripts (b0524dc)

