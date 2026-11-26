"""
Offline tests for geochip.datasets and geochip.downloader.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from geochip.datasets import COMPOSITE_METHODS, DATASETS
from geochip.downloader import (
    build_composite_image,
    fetch_scenes_list,
    validate_date_range,
    validate_date_str,
)


def test_datasets_registry_integrity() -> None:
    """Verify required dataset keys, fields, and is_collection flag for dem-srtm."""
    for key in ("sentinel-2", "landsat-9", "landsat-8", "sentinel-1", "modis", "dem-srtm"):
        assert key in DATASETS
        ds = DATASETS[key]
        assert "id" in ds
        assert "scale" in ds
        assert "default_bands" in ds
        assert "is_collection" in ds

    assert DATASETS["dem-srtm"]["is_collection"] is False
    assert DATASETS["sentinel-2"]["is_collection"] is True

    comp_ids = [m["id"] for m in COMPOSITE_METHODS]
    assert comp_ids == ["median", "q25", "mean", "min_cloud"]


def test_date_validation_helpers() -> None:
    """Date validators should accept ISO dates and reject invalid strings or reversed ranges."""
    assert validate_date_str("2025-01-31")[0] is True
    assert validate_date_str("2025-13-40")[0] is False
    assert validate_date_str("31-01-2025")[0] is False

    assert validate_date_range("2025-01-01", "2025-03-31")[0] is True
    assert validate_date_range("2025-04-01", "2025-03-31")[0] is False


def test_fetch_scenes_list_handles_static_dem_and_lightweight_collection(monkeypatch) -> None:
    """dem-srtm uses ee.Image while collections fetch metadata via a single aggregate_array RPC."""
    calls: dict[str, object] = {}

    class FakeCollection:
        def filterBounds(self, geom):
            return self

        def filterDate(self, start, end):
            return self

        def filter(self, filt):
            return self

        def sort(self, prop, asc):
            return self

        def limit(self, n):
            calls["limit"] = n
            return self

        def aggregate_array(self, prop):
            return f"arr:{prop}"

    class FakeDict:
        def __init__(self, payload):
            calls["dict_payload"] = payload

        def getInfo(self):
            return {
                "ids": ["COPERNICUS/S2_SR_HARMONIZED/20250115T030000_T48MYT"],
                "times": [1736910000000],
                "clouds": [4.2],
            }

    fake_ee = SimpleNamespace(
        Image=lambda cid: ("IMAGE", cid),
        ImageCollection=lambda cid: FakeCollection(),
        Filter=SimpleNamespace(lte=lambda p, v: (p, v)),
        Dictionary=FakeDict,
    )
    monkeypatch.setitem(sys.modules, "ee", fake_ee)

    img, dem_scenes = fetch_scenes_list(
        "USGS/SRTMGL1_003", "geom", "2025-01-01", "2025-02-01", is_collection=False
    )
    assert img == ("IMAGE", "USGS/SRTMGL1_003")
    assert len(dem_scenes) == 1
    assert dem_scenes[0]["short_id"] == "SRTMGL1_003"

    _, s2_scenes = fetch_scenes_list(
        "COPERNICUS/S2_SR_HARMONIZED",
        "geom",
        "2025-01-01",
        "2025-02-01",
        cloud_prop="CLOUDY_PIXEL_PERCENTAGE",
        max_cloud=20,
        is_collection=True,
    )
    assert calls["limit"] == 50
    assert s2_scenes[0]["cloud"] == "4.2%"
    assert s2_scenes[0]["short_id"] == "20250115T030000_T48MYT"


def test_build_composite_q25_renames_bands(monkeypatch) -> None:
    """q25 composite must rename percentile output back to dataset default_bands."""
    recorded: dict[str, object] = {}

    class FakeMaskedCol:
        def select(self, bands):
            recorded["selected"] = bands
            return self

        def reduce(self, reducer):
            recorded["reduced"] = reducer
            return self

        def rename(self, bands):
            recorded["renamed"] = bands
            return "FINAL_Q25_IMAGE"

    class FakeCol:
        def map(self, fn):
            return FakeMaskedCol()

    fake_ee = SimpleNamespace(
        Reducer=SimpleNamespace(percentile=lambda pcts: f"p{pcts[0]}"),
    )
    monkeypatch.setitem(sys.modules, "ee", fake_ee)

    out = build_composite_image(FakeCol(), "sentinel-2", "q25")
    assert out == "FINAL_Q25_IMAGE"
    assert recorded["selected"] == ["B4", "B3", "B2"]
    assert recorded["reduced"] == "p25"
    assert recorded["renamed"] == ["B4", "B3", "B2"]
