"""
Offline tests for geochip.tiler.
Covers WGS84 and projected UTM GeoTIFF chipping and manifest.json coordinate normalization.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from geochip.tiler import (
    build_chip_size_choices,
    create_single_raster_chips,
    get_raster_dimensions,
)


def test_offline_wgs84_raster_chipping(tmp_path: Path) -> None:
    """Slice a synthetic 640x640 WGS84 GeoTIFF into 16 chips of 160x160 and verify manifest."""
    test_tif = tmp_path / "synthetic_wgs84.tif"
    chips_out = tmp_path / "chips"

    data = np.full((3, 640, 640), 128, dtype=np.uint8)
    transform = from_origin(106.0, -6.0, 0.0001, 0.0001)

    with rasterio.open(
        str(test_tif),
        "w",
        driver="GTiff",
        height=640,
        width=640,
        count=3,
        dtype=np.uint8,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data)

    out_dir, count = create_single_raster_chips(
        raster_path=test_tif,
        output_base=chips_out,
        chip_size=160,
        chips_per_task=2,
        min_valid_ratio=0.50,
    )

    assert out_dir is not None
    assert count == 16

    manifest = json.loads((Path(out_dir) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["crs"] == "EPSG:4326"
    assert manifest["total_chips"] == 16
    assert manifest["total_tasks"] == 8
    first_chip = manifest["chips"][0]
    assert (Path(out_dir) / first_chip["relative_path"]).is_file()


def test_projected_utm_raster_manifest_transforms_to_wgs84(tmp_path: Path) -> None:
    """Projected UTM GeoTIFF chips must still emit WGS84 lon/lat bounds in manifest.json."""
    test_tif = tmp_path / "synthetic_utm48s.tif"
    chips_out = tmp_path / "chips"

    data = np.full((3, 320, 320), 200, dtype=np.uint8)
    transform = from_origin(803750.0, 9274070.0, 10.0, 10.0)

    with rasterio.open(
        str(test_tif),
        "w",
        driver="GTiff",
        height=320,
        width=320,
        count=3,
        dtype=np.uint8,
        crs="EPSG:32748",
        transform=transform,
    ) as dst:
        dst.write(data)

    out_dir, count = create_single_raster_chips(
        raster_path=test_tif,
        output_base=chips_out,
        chip_size=160,
        chips_per_task=4,
    )

    assert count == 4
    manifest = json.loads((Path(out_dir) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["crs"] == "EPSG:4326"
    assert "32748" in manifest["source_crs"]

    min_lon, min_lat, max_lon, max_lat = manifest["chips"][0]["geo_bbox"]
    assert 107.70 <= min_lon < max_lon <= 107.85
    assert -6.65 <= min_lat < max_lat <= -6.50


def test_build_chip_size_choices_sentinel2_aoi2() -> None:
    """Rasters around Sentinel-2 AOI-2 dimensions fit 160/320 px and flag 640/1280 px."""
    choices, default_idx, has_compatible = build_chip_size_choices(895, 414)

    assert has_compatible is True
    assert default_idx == 1
    assert "~10 max chips (5x2 grid)" in choices[0]["desc"]
    assert "~2 max chips (2x1 grid)" in choices[1]["desc"]
    assert "[Too large for 895x414 px raster]" in choices[2]["desc"]
    assert "[Too large for 895x414 px raster]" in choices[3]["desc"]


def test_build_chip_size_choices_srtm_too_small() -> None:
    """Rasters smaller than 160x160 px flag every chip preset as too large."""
    choices, default_idx, has_compatible = build_chip_size_choices(302, 140)

    assert has_compatible is False
    assert default_idx == 0
    assert all("[Too large for 302x140 px raster]" in c["desc"] for c in choices)


def test_build_chip_size_choices_large_raster_defaults_to_640() -> None:
    """Large rasters that fit all presets keep 640 x 640 px as the default selection."""
    choices, default_idx, has_compatible = build_chip_size_choices(2000, 2000)

    assert has_compatible is True
    assert default_idx == 2
    assert all("[Too large" not in c["desc"] for c in choices)


def test_get_raster_dimensions(tmp_path: Path) -> None:
    """Read (width, height) pixel dimensions directly from a synthetic GeoTIFF."""
    test_tif = tmp_path / "srtm_sample.tif"
    data = np.full((1, 140, 302), 100, dtype=np.uint8)
    transform = from_origin(107.74, -6.55, 0.00027, 0.00027)

    with rasterio.open(
        str(test_tif),
        "w",
        driver="GTiff",
        height=140,
        width=302,
        count=1,
        dtype=np.uint8,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data)

    assert get_raster_dimensions(test_tif) == (302, 140)
