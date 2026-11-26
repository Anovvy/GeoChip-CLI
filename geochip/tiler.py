"""
GeoChip Tiling & Chipping Engine.
Slices GeoTIFF rasters into uniform tiles (160, 320, 640, 1280 px),
organizes tiles into task batches, and generates a WGS84 georeferenced manifest.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .config import ensure_workspace_dirs, resolve_work_dir
from .ui import (
    print_error,
    print_info,
    print_step,
    print_success,
    print_warning,
    prompt_number,
    select,
)

CHIP_SIZES = [
    {"name": "160 x 160 px", "size": 160, "desc": "Small object detection (Sentinel-2 10m / UAV)"},
    {"name": "320 x 320 px", "size": 320, "desc": "Medium-scale models (YOLO / Faster R-CNN)"},
    {"name": "640 x 640 px", "size": 640, "desc": "Standard Roboflow & YOLO resolution"},
    {"name": "1280 x 1280 px", "size": 1280, "desc": "High-resolution / wide spatial context"},
]


def list_available_raw_rasters(raw_dir: str | Path = "data/raw") -> list[Path]:
    """List all GeoTIFF files available in data/raw."""
    dir_path = Path(raw_dir)
    if not dir_path.exists():
        dir_path.mkdir(parents=True, exist_ok=True)
        return []
    return sorted(list(dir_path.glob("*.tif")) + list(dir_path.glob("*.tiff")))


def format_raster_to_rgb(data: np.ndarray) -> np.ndarray:
    """Convert raw raster array (C, H, W) into an (H, W, 3) uint8 RGB image."""
    c, h, w = data.shape
    if c >= 3:
        if data.dtype == np.uint8:
            return np.transpose(data[:3], (1, 2, 0))
        rgb = np.zeros((h, w, 3), dtype=np.uint8)
        for i in range(3):
            band = data[i].astype(np.float32)
            finite_mask = np.isfinite(band)
            if not np.any(finite_mask):
                continue
            p2, p98 = np.percentile(band[finite_mask], (2, 98))
            if p98 > p2:
                norm = np.clip((band - p2) / (p98 - p2) * 255.0, 0, 255).astype(np.uint8)
            else:
                norm = np.clip(band, 0, 255).astype(np.uint8)
            rgb[:, :, i] = norm
        return rgb

    if c == 1:
        band = data[0].astype(np.float32)
        if data.dtype == np.uint8:
            norm = data[0]
        else:
            finite_mask = np.isfinite(band)
            if np.any(finite_mask):
                p2, p98 = np.percentile(band[finite_mask], (2, 98))
                if p98 > p2:
                    norm = np.clip((band - p2) / (p98 - p2) * 255.0, 0, 255).astype(np.uint8)
                else:
                    norm = np.clip(band, 0, 255).astype(np.uint8)
            else:
                norm = np.zeros((h, w), dtype=np.uint8)
        return np.stack([norm, norm, norm], axis=-1)

    if c == 2:
        b1 = data[0].astype(np.float32)
        b2 = data[1].astype(np.float32)
        b3 = (b1 + b2) / 2.0
        return format_raster_to_rgb(np.stack([b1, b2, b3], axis=0))

    raise ValueError(f"Unsupported raster dimensions: {data.shape}")


def create_single_raster_chips(
    raster_path: str | Path,
    output_base: str | Path = "data/chips",
    chip_size: int = 640,
    chips_per_task: int = 5,
    min_valid_ratio: float = 0.70,
) -> tuple[str | None, int]:
    """Slice a satellite GeoTIFF into PNG chips grouped by task with a WGS84 manifest.json."""
    raster_path = Path(raster_path)
    if not raster_path.exists():
        raise FileNotFoundError(f"Raster file '{raster_path}' not found.")

    import rasterio
    from PIL import Image
    from rasterio.warp import transform_bounds

    raster_stem = raster_path.stem
    out_dir = Path(output_base) / raster_stem
    out_dir.mkdir(parents=True, exist_ok=True)

    print_info(f"Opening raster file: {raster_path.name}")
    with rasterio.open(str(raster_path)) as src:
        transform = src.transform
        crs = src.crs
        width = src.width
        height = src.height
        count = src.count
        print_info(f"Raster dimensions: {width} x {height} px ({count} bands) | CRS: {crs}")
        raw_data = src.read()

    print_info("Formatting raster data to RGB...")
    rgb_data = format_raster_to_rgb(raw_data)
    h, w, _ = rgb_data.shape

    n_rows = h // chip_size
    n_cols = w // chip_size
    total_grid = n_rows * n_cols

    if total_grid == 0:
        print_error(f"Raster dimensions ({w}x{h} px) are smaller than chip size ({chip_size}x{chip_size} px).")
        return None, 0

    print_info(f"Tiling grid: {n_rows} rows x {n_cols} cols ({total_grid} potential chips)")

    needs_wgs84_warp = crs is not None and str(crs).upper() != "EPSG:4326"
    manifest = []
    chip_counter = 0

    for r in range(n_rows):
        for c in range(n_cols):
            r_start = r * chip_size
            r_end = r_start + chip_size
            c_start = c * chip_size
            c_end = c_start + chip_size

            chip_crop = rgb_data[r_start:r_end, c_start:c_end, :]

            valid_pixels = np.any(chip_crop > 0, axis=-1)
            valid_ratio = float(np.mean(valid_pixels))
            if valid_ratio < min_valid_ratio:
                continue

            chip_counter += 1
            task_num = ((chip_counter - 1) // chips_per_task) + 1
            task_name = f"task{task_num}-{raster_stem}"
            task_dir = out_dir / task_name
            task_dir.mkdir(parents=True, exist_ok=True)

            chip_filename = f"chip_{chip_counter:04d}.png"
            chip_filepath = task_dir / chip_filename
            Image.fromarray(chip_crop).save(str(chip_filepath), optimize=True)

            x0, y0 = transform * (c_start, r_start)
            x1, y1 = transform * (c_end, r_end)
            left, right = min(x0, x1), max(x0, x1)
            bottom, top = min(y0, y1), max(y0, y1)

            if needs_wgs84_warp:
                min_lon, min_lat, max_lon, max_lat = transform_bounds(
                    crs, "EPSG:4326", left, bottom, right, top
                )
            else:
                min_lon, min_lat, max_lon, max_lat = left, bottom, right, top

            manifest.append(
                {
                    "chip_id": f"chip_{chip_counter:04d}",
                    "task": task_name,
                    "relative_path": f"{task_name}/{chip_filename}",
                    "pixel_bbox": [c_start, r_start, c_end, r_end],
                    "geo_bbox": [min_lon, min_lat, max_lon, max_lat],
                    "dimensions": [chip_size, chip_size],
                    "valid_coverage": round(valid_ratio, 4),
                }
            )

    manifest_path = out_dir / "manifest.json"
    manifest_data = {
        "source_raster": raster_path.name,
        "crs": "EPSG:4326",
        "source_crs": str(crs) if crs else "unknown",
        "chip_size": chip_size,
        "chips_per_task": chips_per_task,
        "total_chips": chip_counter,
        "total_tasks": ((chip_counter - 1) // chips_per_task) + 1 if chip_counter > 0 else 0,
        "chips": manifest,
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    print_success(f"Tiling complete! Generated {chip_counter} chip(s).")
    print_info(f"Output directory: {out_dir}")
    print_info(f"Manifest saved at: {manifest_path}")
    return str(out_dir), chip_counter


def interactive_chipping_workflow(
    work_dir: Path | None = None,
    preselected_raster: str | Path | None = None,
) -> None:
    """Interactive Step 2: Chipping & Upload to Roboflow."""
    ws = resolve_work_dir(work_dir)
    dirs = ensure_workspace_dirs(ws)

    print_step("Step 2: Chipping & Upload to Roboflow")

    if preselected_raster and Path(preselected_raster).is_file():
        selected_raster = Path(preselected_raster)
        print_success(f"Using downloaded raster: {selected_raster.name}")
    else:
        raw_files = list_available_raw_rasters(dirs["raw"])
        if not raw_files:
            print_error(f"No GeoTIFF rasters (.tif) found in '{dirs['raw']}'.")
            print_info("Run Step 1 (Download Satellite Imagery) first, or place a .tif file in data/raw/.")
            return

        raster_choices = [
            {"name": f.name, "desc": f"Size: {f.stat().st_size / (1024 * 1024):.2f} MB"}
            for f in raw_files
        ]
        raster_idx = select("Select Raw Raster to Chip:", raster_choices)
        selected_raster = raw_files[raster_idx]
        print_success(f"Selected raster: {selected_raster.name}")

    size_choices = [{"name": s["name"], "desc": s["desc"]} for s in CHIP_SIZES]
    size_idx = select("Select Chip Tile Size (Pixels):", size_choices, default_index=2)
    selected_chip_size = CHIP_SIZES[size_idx]["size"]
    print_success(f"Chip size: {selected_chip_size} x {selected_chip_size} px")

    chips_per_task = prompt_number(
        "Specify Number of Chips per Task Batch",
        default=5,
        min_val=1,
        max_val=500,
    )
    print_info(f"Batch task size: {chips_per_task} chips per task folder")

    chips_dir, count = create_single_raster_chips(
        raster_path=selected_raster,
        output_base=dirs["chips"],
        chip_size=selected_chip_size,
        chips_per_task=chips_per_task,
    )

    if count == 0 or not chips_dir:
        print_warning("No valid chips were generated (raster may be empty or mostly nodata).")
        return

    print_step("Roboflow Upload Options")
    upload_options = [
        {
            "name": "🚀 Yes, Upload Chip Batches to Roboflow Now",
            "desc": "Send task folders directly to Roboflow as Annotation Batches",
            "action": "upload",
        },
        {
            "name": "💾 Save Locally Only (Skip Upload)",
            "desc": "Keep generated chips stored locally in data/chips/",
            "action": "skip",
        },
    ]
    up_idx = select("Would you like to upload chips to Roboflow?", upload_options, default_index=0)

    if upload_options[up_idx]["action"] == "upload":
        from .uploader import interactive_upload_flow

        interactive_upload_flow(chips_dir_path=chips_dir, work_dir=ws)
    else:
        print_success("Process complete! All chips are saved locally and ready to use.")
