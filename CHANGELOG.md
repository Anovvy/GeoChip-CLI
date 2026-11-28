# Changelog

All notable changes to GeoChip CLI are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [3.1.1] - 2026-11-28

### Bug Fixes

- improve zsh/bin-dir detection and isolate major bumps (21e083a)
- exit early on incompatible rasters and guard oversized chip selection (7bce067)
- auto-configure user PATH and install geochip from PyPI (73f9e35)

### Chores

- group GitHub Actions and Python dependency updates (18b7f8c)

### Documentation

- update CHANGELOG.md for v3.0.1 (ab4fdb8)

### Features

- display raster dimensions and chip size compatibility before tiling (3594981)

## [3.0.1] - 2026-11-28

### Bug Fixes

- separate git-cliff OUTPUT path from CHANGELOG prepend target (4ca4996)
- prepend latest release to CHANGELOG and filter style commits (aab0d8f)

## [3.0.0] - 2026-11-26

### Features
- Rebrand product to **GeoChip CLI** (`GeoChip` and `geochip` terminal commands).
- Add native GeoJSON (`.geojson`, `.json`) AOI support alongside ESRI Shapefiles.
- Add automatic CRS detection and reprojection to WGS84 (`EPSG:4326`) via `pyproj`.
- Add Quick Start guided pipeline, live connection status bar, masked secret prompts, and live spinners.
- Add one-command installers (`scripts/install.ps1` and `scripts/install.sh`).
- Add AGY SDK Senior DevOps PR Reviewer with 4-tier Gemini free-tier fallback and SemVer Canary-to-Production CD pipeline.

### Bug Fixes
- Fix slow loading / global scan hang on projected UTM shapefiles (such as UTM Zone 48S) by auto-reprojecting coordinates before Earth Engine queries.
- Fix `q25` percentile composite band renaming before visual GeoTIFF export.
- Fix static `ee.Image` handling for `dem-srtm` (`USGS/SRTMGL1_003`).
- Optimize Earth Engine scene metadata queries using single-RPC `aggregate_array`.
- Transform projected GeoTIFF chip bounding boxes to WGS84 in `manifest.json`.

### Breaking Changes
- Remove Docker runtime (`Dockerfile`, `docker-compose.yml`) and legacy `python main.py` / root wrapper scripts in favor of native `GeoChip` CLI execution.

## [2.0.0] - 2026-10-15

### Features
- Multi-satellite Earth Observation ingestion, single-raster chipping, Roboflow batch upload, and interactive CLI v2.0.
