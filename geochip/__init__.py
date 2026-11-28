"""
GeoChip CLI: Interactive Geospatial Earth Observation Pipeline & Roboflow Ingestion.

Download multi-sensor satellite imagery (Sentinel-2, Landsat 8/9, Sentinel-1 SAR, MODIS, SRTM DEM),
generate georeferenced image chips, and upload annotation batches to Roboflow.
"""

__version__ = "3.1.1"

from .auth import init_earth_engine, login_flow, test_all_connections, test_earth_engine_connection
from .datasets import COMPOSITE_METHODS, DATASETS
from .downloader import interactive_download_workflow, load_aoi_geometry
from .geometry import AOIData, estimate_download_size_mb, list_available_aois, load_aoi_data
from .tiler import CHIP_SIZES, create_single_raster_chips, interactive_chipping_workflow
from .uploader import interactive_upload_flow, upload_chips_to_roboflow

__all__ = [
    "__version__",
    "AOIData",
    "CHIP_SIZES",
    "COMPOSITE_METHODS",
    "DATASETS",
    "create_single_raster_chips",
    "estimate_download_size_mb",
    "init_earth_engine",
    "interactive_chipping_workflow",
    "interactive_download_workflow",
    "interactive_upload_flow",
    "list_available_aois",
    "load_aoi_data",
    "load_aoi_geometry",
    "login_flow",
    "test_all_connections",
    "test_earth_engine_connection",
    "upload_chips_to_roboflow",
]
