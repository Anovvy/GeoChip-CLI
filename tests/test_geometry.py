"""
Offline unit and regression tests for geochip.geometry.
Covers projected UTM shapefiles (AOI-2 regression), WGS84 shapefiles, GeoJSON, and size estimation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import shapefile

from geochip.geometry import (
    estimate_download_size_mb,
    list_available_aois,
    load_aoi_data,
)

UTM_48S_WKT = (
    'PROJCS["WGS_1984_UTM_Zone_48S",'
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
    'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],'
    'PARAMETER["False_Easting",500000.0],'
    'PARAMETER["False_Northing",10000000.0],'
    'PARAMETER["Central_Meridian",105.0],'
    'PARAMETER["Scale_Factor",0.9996],'
    'PARAMETER["Latitude_Of_Origin",0.0],'
    'UNIT["Meter",1.0]]'
)

WGS84_WKT = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
    'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)


def _write_polygon_shapefile(base_path: Path, ring: list[list[float]], prj_wkt: str | None) -> Path:
    """Create a synthetic ESRI Shapefile polygon with optional .prj file."""
    shp_base = str(base_path.with_suffix(""))
    with shapefile.Writer(shp_base) as writer:
        writer.field("name", "C")
        writer.poly([ring])
        writer.record("test")
    if prj_wkt is not None:
        base_path.with_suffix(".prj").write_text(prj_wkt, encoding="utf-8")
    return base_path.with_suffix(".shp")


def test_projected_utm_48s_shapefile_reprojects_to_wgs84(tmp_path: Path) -> None:
    """Regression test for AOI-2: UTM Zone 48S meters must reproject cleanly to WGS84."""
    ring = [
        [803757.08, 9274072.72],
        [812695.33, 9274054.12],
        [812686.58, 9269946.27],
        [803748.99, 9269965.15],
        [803757.08, 9274072.72],
    ]
    shp_path = _write_polygon_shapefile(tmp_path / "AOI-2.shp", ring, UTM_48S_WKT)

    aoi = load_aoi_data(shp_path)
    min_lon, min_lat, max_lon, max_lat = aoi.bbox

    assert aoi.reprojected is True
    assert "48S" in aoi.source_crs
    assert 107.70 <= min_lon <= 107.80
    assert 107.80 <= max_lon <= 107.90
    assert -6.65 <= min_lat <= -6.58
    assert -6.58 <= max_lat <= -6.50
    assert 35.0 <= aoi.area_km2 <= 39.0


def test_wgs84_shapefile_skips_reprojection(tmp_path: Path) -> None:
    """Geographic WGS84 shapefiles should load directly without reprojection."""
    ring = [
        [106.3562, -6.1514],
        [106.3581, -6.2334],
        [106.2615, -6.2356],
        [106.2596, -6.1536],
        [106.3562, -6.1514],
    ]
    shp_path = _write_polygon_shapefile(tmp_path / "AOI-1.shp", ring, WGS84_WKT)

    aoi = load_aoi_data(shp_path)
    assert aoi.reprojected is False
    assert 95.0 <= aoi.area_km2 <= 108.0


def test_projected_shapefile_missing_prj_raises_clear_error(tmp_path: Path) -> None:
    """Projected coordinates without a .prj file must fail fast instead of hitting GEE."""
    ring = [
        [803757.08, 9274072.72],
        [812695.33, 9274054.12],
        [812686.58, 9269946.27],
        [803757.08, 9274072.72],
    ]
    shp_path = _write_polygon_shapefile(tmp_path / "no_prj.shp", ring, None)

    with pytest.raises(ValueError, match=r"\.prj"):
        load_aoi_data(shp_path)


def test_geojson_feature_collection_and_multipolygon(tmp_path: Path) -> None:
    """GeoJSON FeatureCollection and MultiPolygon (with optional Z coordinates) should load cleanly."""
    fc_path = tmp_path / "area.geojson"
    fc_payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "sample"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [106.7, -6.2, 10.0],
                            [106.8, -6.2, 10.0],
                            [106.8, -6.3, 10.0],
                            [106.7, -6.3, 10.0],
                        ]
                    ],
                },
            }
        ],
    }
    fc_path.write_text(json.dumps(fc_payload), encoding="utf-8")

    aoi = load_aoi_data(fc_path)
    assert aoi.reprojected is False
    assert aoi.bbox == [106.7, -6.3, 106.8, -6.2]
    assert len(aoi.polygons[0][0]) == 5  # ring auto-closed and Z stripped

    mp_path = tmp_path / "multi.json"
    mp_payload = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[106.7, -6.2], [106.75, -6.2], [106.75, -6.25], [106.7, -6.25], [106.7, -6.2]]],
            [[[106.8, -6.2], [106.85, -6.2], [106.85, -6.25], [106.8, -6.25], [106.8, -6.2]]],
        ],
    }
    mp_path.write_text(json.dumps(mp_payload), encoding="utf-8")

    mp_aoi = load_aoi_data(mp_path)
    assert len(mp_aoi.polygons) == 2


def test_list_available_aois_filters_extensions(tmp_path: Path) -> None:
    """list_available_aois should include .shp, .geojson, .json and ignore .txt/.prj."""
    (tmp_path / "b.geojson").write_text("{}", encoding="utf-8")
    (tmp_path / "a.shp").write_bytes(b"")
    (tmp_path / "c.json").write_text("{}", encoding="utf-8")
    (tmp_path / "a.prj").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")

    found = [p.name for p in list_available_aois(tmp_path)]
    assert found == ["a.shp", "b.geojson", "c.json"]


def test_estimate_download_size_mb() -> None:
    """Download estimator should return positive pixel dimensions and MB estimate."""
    w_px, h_px, est_mb = estimate_download_size_mb(
        [107.74, -6.60, 107.83, -6.56], scale_m=10, bands=3
    )
    assert w_px > 500
    assert h_px > 300
    assert 0.5 < est_mb < 5.0
