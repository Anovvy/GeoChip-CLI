"""
GeoChip Geometry and AOI Loader.
Supports ESRI Shapefiles (.shp) and GeoJSON (.geojson, .json) with automatic CRS
reprojection to WGS84 (EPSG:4326), geodesic area calculation, and payload estimation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyproj import CRS, Geod, Transformer

SUPPORTED_AOI_EXTENSIONS = {".shp", ".geojson", ".json"}
WGS84_CRS = CRS.from_epsg(4326)
WGS84_GEOD = Geod(ellps="WGS84")


@dataclass
class AOIData:
    """Normalized Area of Interest geometry in WGS84 (EPSG:4326)."""

    path: Path
    name: str
    polygons: list[list[list[list[float]]]]
    bbox: list[float]
    source_crs: str
    reprojected: bool
    area_km2: float


def list_available_aois(aoi_dir: str | Path = "data/aoi") -> list[Path]:
    """Scan and list supported AOI files (.shp, .geojson, .json) sorted by name."""
    dir_path = Path(aoi_dir)
    if not dir_path.exists():
        dir_path.mkdir(parents=True, exist_ok=True)
        return []
    files = [
        p
        for p in dir_path.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_AOI_EXTENSIONS
    ]
    return sorted(files, key=lambda p: p.name.lower())


def _find_prj_file(shp_path: Path) -> Path | None:
    """Locate companion .prj file case-insensitively."""
    direct = shp_path.with_suffix(".prj")
    if direct.is_file():
        return direct
    stem_lower = shp_path.stem.lower()
    for sibling in shp_path.parent.iterdir():
        if (
            sibling.is_file()
            and sibling.stem.lower() == stem_lower
            and sibling.suffix.lower() == ".prj"
        ):
            return sibling
    return None


def _close_ring(ring: list[list[float]]) -> list[list[float]]:
    """Ensure a polygon ring is explicitly closed and uses 2D [x, y] pairs."""
    cleaned = [[float(pt[0]), float(pt[1])] for pt in ring]
    if len(cleaned) >= 3 and cleaned[0] != cleaned[-1]:
        cleaned.append(list(cleaned[0]))
    return cleaned


def _validate_wgs84_bounds(polygons: list[list[list[list[float]]]]) -> list[float]:
    """Validate all coordinates fall within WGS84 ranges and return [min_lon, min_lat, max_lon, max_lat]."""
    lons: list[float] = []
    lats: list[float] = []
    for polygon in polygons:
        for ring in polygon:
            for lon, lat in ring:
                if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                    raise ValueError(
                        f"Coordinate ({lon:.4f}, {lat:.4f}) is outside valid WGS84 lon/lat bounds "
                        "([-180, 180], [-90, 90])."
                    )
                lons.append(lon)
                lats.append(lat)

    if not lons or not lats:
        raise ValueError("AOI geometry contains no valid coordinates.")

    return [min(lons), min(lats), max(lons), max(lats)]


def _compute_area_km2(polygons: list[list[list[list[float]]]]) -> float:
    """Compute true geodesic area in square kilometers across polygon outer rings."""
    total_m2 = 0.0
    for polygon in polygons:
        if not polygon:
            continue
        outer_ring = polygon[0]
        if len(outer_ring) < 4:
            continue
        lons = [pt[0] for pt in outer_ring]
        lats = [pt[1] for pt in outer_ring]
        area_m2, _ = WGS84_GEOD.polygon_area_perimeter(lons, lats)
        total_m2 += abs(area_m2)
    return total_m2 / 1_000_000.0


def _split_shapefile_parts(shape: Any) -> list[list[list[float]]]:
    """Split a pyshp shape into one or more coordinate rings using shape.parts."""
    points = [list(pt[:2]) for pt in shape.points]
    if not points:
        return []
    parts = list(getattr(shape, "parts", [0]) or [0])
    indices = parts + [len(points)]
    rings: list[list[list[float]]] = []
    for start, end in zip(indices[:-1], indices[1:], strict=False):
        ring = points[start:end]
        if len(ring) >= 3:
            rings.append(_close_ring(ring))
    return rings


def _is_wgs84_geographic(crs: CRS) -> bool:
    """Return True if the CRS is already geographic WGS84 (including ESRI WKT1)."""
    if not crs.is_geographic:
        return False
    if crs.equals(WGS84_CRS) or crs.to_epsg() == 4326:
        return True
    name_upper = (crs.name or "").upper()
    return "WGS 84" in name_upper or "WGS_1984" in name_upper


def _load_shapefile_aoi(shp_path: Path) -> AOIData:
    """Load an ESRI Shapefile and reproject it to WGS84 if its .prj uses another CRS."""
    import shapefile

    sf = shapefile.Reader(str(shp_path))
    shapes = sf.shapes()
    if not shapes:
        raise ValueError(f"Shapefile '{shp_path.name}' contains no geometry features.")

    prj_path = _find_prj_file(shp_path)
    transformer: Transformer | None = None
    reprojected = False

    if prj_path is not None:
        wkt_text = prj_path.read_text(encoding="utf-8", errors="ignore").strip()
        if not wkt_text:
            raise ValueError(f"Projection file '{prj_path.name}' is empty.")
        src_crs = CRS.from_wkt(wkt_text)
        source_crs = src_crs.name or str(src_crs)
        if not _is_wgs84_geographic(src_crs):
            transformer = Transformer.from_crs(src_crs, WGS84_CRS, always_xy=True)
            reprojected = True
    else:
        raw_bbox = sf.bbox
        if (
            abs(raw_bbox[0]) > 180.0
            or abs(raw_bbox[2]) > 180.0
            or abs(raw_bbox[1]) > 90.0
            or abs(raw_bbox[3]) > 90.0
        ):
            raise ValueError(
                f"Shapefile '{shp_path.name}' has projected coordinates ({raw_bbox}) but is missing a .prj file. "
                "Include the .prj file or export the AOI as WGS84 GeoJSON."
            )
        source_crs = "WGS 84 (assumed; no .prj found)"

    polygons: list[list[list[list[float]]]] = []
    for shape in shapes:
        rings = _split_shapefile_parts(shape)
        if not rings:
            continue
        transformed_rings: list[list[list[float]]] = []
        for ring in rings:
            if transformer is not None:
                xs = [pt[0] for pt in ring]
                ys = [pt[1] for pt in ring]
                lons, lats = transformer.transform(xs, ys)
                ring = [[float(lon), float(lat)] for lon, lat in zip(lons, lats, strict=False)]
            transformed_rings.append(_close_ring(ring))
        polygons.append(transformed_rings)

    if not polygons:
        raise ValueError(f"Shapefile '{shp_path.name}' contains no valid polygon rings.")

    bbox = _validate_wgs84_bounds(polygons)
    area_km2 = _compute_area_km2(polygons)
    return AOIData(
        path=shp_path,
        name=shp_path.stem,
        polygons=polygons,
        bbox=bbox,
        source_crs=source_crs,
        reprojected=reprojected,
        area_km2=area_km2,
    )


def _extract_geojson_polygons(geometry: dict[str, Any]) -> list[list[list[list[float]]]]:
    """Extract polygon ring lists from a GeoJSON Polygon or MultiPolygon geometry dict."""
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates") or []

    if geom_type == "Polygon":
        rings = [_close_ring(ring) for ring in coords if len(ring) >= 3]
        return [rings] if rings else []

    if geom_type == "MultiPolygon":
        polys: list[list[list[list[float]]]] = []
        for poly_coords in coords:
            rings = [_close_ring(ring) for ring in poly_coords if len(ring) >= 3]
            if rings:
                polys.append(rings)
        return polys

    raise ValueError(
        f"Unsupported GeoJSON geometry type '{geom_type}'. Expected Polygon or MultiPolygon."
    )


def _load_geojson_aoi(geojson_path: Path) -> AOIData:
    """Load a WGS84 GeoJSON AOI (FeatureCollection, Feature, Polygon, or MultiPolygon)."""
    raw = json.loads(geojson_path.read_text(encoding="utf-8"))
    obj_type = raw.get("type")

    polygons: list[list[list[list[float]]]] = []
    if obj_type == "FeatureCollection":
        features = raw.get("features") or []
        for feat in features:
            geom = feat.get("geometry")
            if geom:
                polygons.extend(_extract_geojson_polygons(geom))
    elif obj_type == "Feature":
        geom = raw.get("geometry")
        if geom:
            polygons.extend(_extract_geojson_polygons(geom))
    elif obj_type in {"Polygon", "MultiPolygon"}:
        polygons.extend(_extract_geojson_polygons(raw))
    else:
        raise ValueError(f"Unsupported GeoJSON root type '{obj_type}'.")

    if not polygons:
        raise ValueError(f"GeoJSON '{geojson_path.name}' contains no valid polygon geometry.")

    bbox = _validate_wgs84_bounds(polygons)
    area_km2 = _compute_area_km2(polygons)
    return AOIData(
        path=geojson_path,
        name=geojson_path.stem,
        polygons=polygons,
        bbox=bbox,
        source_crs="EPSG:4326 (GeoJSON WGS84)",
        reprojected=False,
        area_km2=area_km2,
    )


def load_aoi_data(aoi_path: str | Path) -> AOIData:
    """Load an AOI from Shapefile (.shp) or GeoJSON (.geojson/.json) and normalize to WGS84."""
    path = Path(aoi_path)
    if not path.is_file():
        raise FileNotFoundError(f"AOI file '{path}' not found.")

    suffix = path.suffix.lower()
    if suffix == ".shp":
        return _load_shapefile_aoi(path)
    if suffix in {".geojson", ".json"}:
        return _load_geojson_aoi(path)

    raise ValueError(
        f"Unsupported AOI format '{path.suffix}'. Supported formats: .shp, .geojson, .json"
    )


def estimate_download_size_mb(
    bbox: list[float], scale_m: float, bands: int = 3
) -> tuple[int, int, float]:
    """Estimate exported UInt8 GeoTIFF pixel dimensions and uncompressed size in MB."""
    min_lon, min_lat, max_lon, max_lat = bbox
    mid_lat = (min_lat + max_lat) / 2.0
    mid_lon = (min_lon + max_lon) / 2.0

    _, _, width_m = WGS84_GEOD.inv(min_lon, mid_lat, max_lon, mid_lat)
    _, _, height_m = WGS84_GEOD.inv(mid_lon, min_lat, mid_lon, max_lat)

    width_px = max(1, int(round(width_m / scale_m)))
    height_px = max(1, int(round(height_m / scale_m)))
    est_mb = round((width_px * height_px * bands) / (1024 * 1024), 2)
    return width_px, height_px, est_mb


def to_ee_geometry(aoi_data: AOIData) -> Any:
    """Convert normalized AOIData into an ee.Geometry.Polygon or MultiPolygon."""
    import ee

    if len(aoi_data.polygons) == 1:
        return ee.Geometry.Polygon(aoi_data.polygons[0])
    return ee.Geometry.MultiPolygon(aoi_data.polygons)
