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

from geochip.tiler import create_single_raster_chips


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
