# Changelog

All notable changes to GeoChip CLI are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

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
