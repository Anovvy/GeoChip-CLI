"""
GeoChip Satellite Downloader Engine.
Interactive search, cloud filtering, scene listing, compositing, and downloading from Google Earth Engine.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from .auth import init_earth_engine, login_flow
from .config import ensure_workspace_dirs, load_app_env, resolve_work_dir
from .datasets import COMPOSITE_METHODS, DATASETS, mask_clouds, prepare_visual_image
from .geometry import (
    estimate_download_size_mb,
    list_available_aois,
    load_aoi_data,
    to_ee_geometry,
)
from .ui import (
    print_error,
    print_info,
    print_step,
    print_success,
    print_warning,
    prompt_confirm,
    prompt_input,
    prompt_number,
    select,
    spinner,
)


def validate_date_str(value: str) -> tuple[bool, str]:
    """Validate that a date string follows YYYY-MM-DD."""
    try:
        datetime.date.fromisoformat(value.strip())
        return True, ""
    except ValueError:
        return False, "Invalid date. Please use YYYY-MM-DD format (e.g., 2025-01-31)."


def validate_date_range(start_date: str, end_date: str) -> tuple[bool, str]:
    """Validate that both dates are valid ISO dates and start_date <= end_date."""
    ok_start, err_start = validate_date_str(start_date)
    if not ok_start:
        return False, err_start
    ok_end, err_end = validate_date_str(end_date)
    if not ok_end:
        return False, err_end
    if datetime.date.fromisoformat(start_date.strip()) > datetime.date.fromisoformat(end_date.strip()):
        return False, "End date must be on or after start date."
    return True, ""


def load_aoi_geometry(shp_path: str | Path):
    """Load an AOI file (.shp or .geojson), auto-reproject to WGS84, and return EE geometry + metadata."""
    aoi = load_aoi_data(shp_path)
    ee_geom = to_ee_geometry(aoi)
    outer_ring = aoi.polygons[0][0]
    return ee_geom, outer_ring, aoi.bbox, aoi


def download_stream(url: str, target_path: str | Path, desc: str = "Downloading Raster") -> None:
    """Stream download a file with a live progress bar."""
    import requests
    from tqdm import tqdm

    response = requests.get(url, stream=True, timeout=900)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    with (
        open(target_path, "wb") as f,
        tqdm(
            desc=desc,
            total=total_size,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
        ) as bar,
    ):
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                bar.update(len(chunk))


def fetch_scenes_list(
    collection_id: str,
    aoi_geom,
    start_date: str,
    end_date: str,
    cloud_prop: str | None = None,
    max_cloud: float = 100.0,
    is_collection: bool = True,
):
    """Query Earth Engine and return (image_or_collection, scene_metadata_list)."""
    import ee

    if not is_collection:
        static_img = ee.Image(collection_id)
        return static_img, [
            {
                "id": collection_id,
                "short_id": collection_id.split("/")[-1],
                "date": "Static Global Dataset",
                "cloud": "N/A",
                "cloud_num": 0.0,
            }
        ]

    col = (
        ee.ImageCollection(collection_id)
        .filterBounds(aoi_geom)
        .filterDate(start_date, end_date)
    )

    if cloud_prop:
        col = col.filter(ee.Filter.lte(cloud_prop, max_cloud))

    # Fetch lightweight metadata arrays in a single RPC (avoids heavy per-scene property dumps)
    limited = col.sort("system:time_start", False).limit(50)
    meta_dict = {
        "ids": limited.aggregate_array("system:id"),
        "times": limited.aggregate_array("system:time_start"),
    }
    if cloud_prop:
        meta_dict["clouds"] = limited.aggregate_array(cloud_prop)

    info = ee.Dictionary(meta_dict).getInfo() or {}
    ids = info.get("ids") or []
    if not ids:
        return col, []

    times = info.get("times") or []
    clouds = info.get("clouds") or []

    scenes = []
    for idx, scene_id in enumerate(ids):
        time_millis = times[idx] if idx < len(times) else None
        if time_millis:
            date_str = datetime.datetime.fromtimestamp(
                time_millis / 1000.0, tz=datetime.timezone.utc
            ).strftime("%Y-%m-%d %H:%M")
        else:
            date_str = "N/A"

        cloud_val = clouds[idx] if cloud_prop and idx < len(clouds) else None
        scenes.append(
            {
                "id": scene_id,
                "short_id": str(scene_id).split("/")[-1],
                "date": date_str,
                "cloud": f"{cloud_val:.1f}%" if cloud_val is not None else "N/A",
                "cloud_num": float(cloud_val) if cloud_val is not None else 0.0,
            }
        )

    return col, scenes


def build_composite_image(col, dataset_key: str, comp_method: str, cloud_prop: str | None = None):
    """Build a cloud-masked composite EE image preserving original band names."""
    import ee

    ds_info = DATASETS[dataset_key]
    target_bands = ds_info["default_bands"]
    masked_col = col.map(lambda img: mask_clouds(img, dataset_key))

    if comp_method == "q25":
        return (
            masked_col.select(target_bands)
            .reduce(ee.Reducer.percentile([25]))
            .rename(target_bands)
        )
    if comp_method == "mean":
        return masked_col.mean()
    if comp_method == "min_cloud" and cloud_prop:
        return masked_col.sort(cloud_prop, False).mosaic()
    return masked_col.median()


def interactive_download_workflow(work_dir: Path | None = None) -> str | None:
    """Interactive Step 1: Download satellite imagery from Google Earth Engine."""
    ws = resolve_work_dir(work_dir)
    load_app_env(ws)
    dirs = ensure_workspace_dirs(ws)

    print_step("Step 1: Download Satellite Imagery (Earth Engine)")

    # 1. Check Authentication
    if not init_earth_engine():
        print_warning("Earth Engine is not authenticated. Initiating login...")
        if not login_flow(work_dir=ws):
            print_error("Authentication failed. Run 'GeoChip auth --login' to sign in.")
            return None

    import ee

    # 2. Select AOI (.shp or .geojson)
    aoi_dir = dirs["aoi"]
    print_info(f"Scanning AOI files (.shp, .geojson) in '{aoi_dir}'...")
    aoi_files = list_available_aois(aoi_dir)
    if not aoi_files:
        print_error(f"No AOI files found in '{aoi_dir}'.")
        print_info("Place a GeoJSON (.geojson) or ESRI Shapefile (.shp) inside data/aoi/ first.")
        print_info("Tip: Draw an area easily at https://geojson.io and save it into data/aoi/.")
        return None

    aoi_choices = [
        {"name": f.name, "desc": f"Format: {f.suffix.upper()} | Size: {f.stat().st_size} bytes"}
        for f in aoi_files
    ]
    aoi_idx = select("Select Area of Interest (AOI):", aoi_choices)
    selected_aoi_path = aoi_files[aoi_idx]

    print_info(f"Loading geometry from {selected_aoi_path.name}...")
    try:
        aoi_geom, _, bbox, aoi_data = load_aoi_geometry(selected_aoi_path)
    except Exception as exc:
        print_error(f"Failed to load AOI '{selected_aoi_path.name}': {exc}")
        return None

    reproj_note = " -> auto-reprojected to EPSG:4326" if aoi_data.reprojected else ""
    print_success(
        f"AOI '{aoi_data.name}' loaded | CRS: {aoi_data.source_crs}{reproj_note} | "
        f"Area: {aoi_data.area_km2:.2f} km²"
    )
    print_info(f"WGS84 BBox: [{bbox[0]:.5f}, {bbox[1]:.5f}] to [{bbox[2]:.5f}, {bbox[3]:.5f}]")

    # 3. Select Dataset
    ds_keys = list(DATASETS.keys())
    ds_choices = [{"name": DATASETS[k]["name"], "desc": DATASETS[k]["desc"]} for k in ds_keys]
    ds_idx = select("Select Satellite / Earth Observation Dataset:", ds_choices)
    dataset_key = ds_keys[ds_idx]
    ds_info = DATASETS[dataset_key]
    print_success(f"Selected dataset: {ds_info['name']}")

    is_collection = ds_info.get("is_collection", True)

    # 4. Date Range & Cloud Cover Filter
    today = datetime.date.today()
    default_end = today.strftime("%Y-%m-%d")
    default_start = (today - datetime.timedelta(days=90)).strftime("%Y-%m-%d")

    start_date = default_start
    end_date = default_end
    max_cloud = 100.0

    if is_collection:
        while True:
            start_date = prompt_input(
                "Enter Start Date (YYYY-MM-DD)",
                default=default_start,
                validator=validate_date_str,
            )
            end_date = prompt_input(
                "Enter End Date (YYYY-MM-DD)",
                default=default_end,
                validator=validate_date_str,
            )
            ok, err = validate_date_range(start_date, end_date)
            if ok:
                break
            print_error(err)

        if ds_info["type"] == "optical" and ds_info["cloud_prop"]:
            max_cloud = prompt_number(
                "Maximum Cloud Cover Percentage Threshold (%) [0 - 100]",
                default=20.0,
                min_val=0.0,
                max_val=100.0,
                is_float=True,
            )
            print_info(f"Filtering optical scenes with cloud cover <= {max_cloud}%")
        elif ds_info["type"] == "radar":
            print_info("Radar (Sentinel-1 SAR) penetrates clouds. Cloud filter skipped.")
    else:
        print_info("Static global dataset selected. Date and cloud filters skipped.")

    # 5. Query Earth Engine Catalog
    try:
        with spinner(f"Querying Earth Engine catalog ({ds_info['id']})..."):
            col_or_img, scenes = fetch_scenes_list(
                collection_id=ds_info["id"],
                aoi_geom=aoi_geom,
                start_date=start_date,
                end_date=end_date,
                cloud_prop=ds_info["cloud_prop"],
                max_cloud=max_cloud,
                is_collection=is_collection,
            )
    except Exception as exc:
        print_error(f"Failed to query Earth Engine: {exc}")
        return None

    total_scenes = len(scenes)
    if total_scenes == 0:
        print_warning("No scenes found matching the date range and cloud filter in this AOI.")
        print_info("Tip: Expand the date range or increase the cloud cover threshold.")
        return None

    print_success(f"Found {total_scenes} matching scene(s).\n")

    # 6. Scene Listing & Ingestion Mode Selection
    out_dir = dirs["raw"]

    if not is_collection:
        final_img = col_or_img
        output_filename = f"{dataset_key}_{aoi_data.name}.tif"
    else:
        menu_choices = [
            {
                "name": f"✨ COMPOSITE ALL SCENES ({total_scenes} acquisitions merged)",
                "desc": "Merge scenes with a reducer to generate a clean cloud-free mosaic",
                "action": "composite",
            }
        ]
        for idx, s in enumerate(scenes):
            cloud_label = f" | Cloud: {s['cloud']}" if s["cloud"] != "N/A" else ""
            menu_choices.append(
                {
                    "name": f"📷 Scene #{idx + 1}: {s['short_id']} ({s['date']}{cloud_label})",
                    "desc": f"Full ID: {s['id']}",
                    "action": "single",
                    "scene": s,
                }
            )

        choice_idx = select("Select Ingestion Mode (Single Scene or Full Composite):", menu_choices, default_index=0)
        chosen_item = menu_choices[choice_idx]

        if chosen_item["action"] == "composite":
            comp_idx = select(
                "Select Compositing Reducer Method:",
                [{"name": m["name"], "desc": m["desc"]} for m in COMPOSITE_METHODS],
                default_index=0,
            )
            comp_method = COMPOSITE_METHODS[comp_idx]["id"]
            print_info(f"Compositing with method: {COMPOSITE_METHODS[comp_idx]['name']}...")
            final_img = build_composite_image(
                col_or_img,
                dataset_key=dataset_key,
                comp_method=comp_method,
                cloud_prop=ds_info["cloud_prop"],
            )
            output_filename = f"{dataset_key}_{aoi_data.name}_{start_date}_{end_date}_{comp_method}.tif"
        else:
            chosen_scene = chosen_item["scene"]
            scene_id = chosen_scene["id"]
            print_info(f"Processing single scene: {scene_id}...")
            final_img = mask_clouds(ee.Image(scene_id), dataset_key)
            date_clean = chosen_scene["date"].split(" ")[0].replace("-", "")
            output_filename = f"{dataset_key}_{aoi_data.name}_{date_clean}_{chosen_scene['short_id']}.tif"

    output_path = out_dir / output_filename

    # 7. Estimate payload size and guard against GEE direct-download quota
    export_scale = ds_info["scale"]
    w_px, h_px, est_mb = estimate_download_size_mb(bbox, export_scale, bands=3)
    print_info(f"Estimated output raster: ~{w_px} x {h_px} px (~{est_mb:.2f} MB uncompressed)")

    if est_mb > 35.0:
        print_warning(
            f"Estimated size ({est_mb:.1f} MB) is close to Earth Engine's ~48 MB direct download limit."
        )
        if prompt_confirm("Increase pixel scale (meters/px) to avoid download errors?", default=True):
            export_scale = prompt_number(
                "Enter export scale in meters/pixel",
                default=max(export_scale * 2, 20),
                min_val=export_scale,
                max_val=1000,
                is_float=False,
            )

    # 8. Prepare UInt8 RGB image and generate download URL
    print_info("Preparing True Color UInt8 GeoTIFF visualization...")
    vis_img = prepare_visual_image(final_img, dataset_key).clip(aoi_geom)

    try:
        with spinner("Generating direct download URL from Earth Engine..."):
            url = vis_img.getDownloadURL(
                {
                    "scale": export_scale,
                    "crs": "EPSG:4326",
                    "region": aoi_geom,
                    "format": "GEO_TIFF",
                }
            )
    except Exception as exc:
        print_error(f"Failed to generate download URL from Earth Engine: {exc}")
        print_warning("The requested raster may exceed the 48 MB direct download limit. Try a smaller AOI or larger scale.")
        return None

    print_info(f"Saving file to: {output_path}")
    download_stream(url, output_path, desc=f"Downloading {output_filename}")

    print_success(f"Download complete! Saved to: {output_path}")
    print_info(f"File size: {output_path.stat().st_size / (1024 * 1024):.2f} MB")
    return str(output_path)
