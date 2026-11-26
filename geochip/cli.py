"""
GeoChip CLI Controller.
Provides the interactive GeoChip menu and standard subcommand execution.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .auth import (
    get_connection_status,
    interactive_auth_menu,
    login_flow,
    setup_roboflow_credentials,
)
from .config import ensure_workspace_dirs, load_app_env, resolve_work_dir
from .downloader import interactive_download_workflow
from .tiler import create_single_raster_chips, interactive_chipping_workflow
from .ui import (
    print_banner,
    print_error,
    print_info,
    print_status_bar,
    print_warning,
    select,
)
from .uploader import interactive_upload_flow, upload_chips_to_roboflow


def interactive_main_menu(work_dir: Path | None = None) -> None:
    """Main interactive terminal loop for GeoChip CLI."""
    ws = resolve_work_dir(work_dir)
    load_app_env(ws)
    ensure_workspace_dirs(ws)

    print_banner()

    main_menu_choices = [
        {
            "name": "🚀 Quick Start: Full Pipeline (Download -> Chip -> Upload)",
            "desc": "Guided end-to-end flow from AOI imagery download to Roboflow upload",
            "action": "quickstart",
        },
        {
            "name": "📥 Step 1: Download Satellite Imagery (Earth Engine)",
            "desc": "Select AOI (.shp / .geojson), Dataset, Date Range, Cloud Filter, Single/Composite",
            "action": "download",
        },
        {
            "name": "✂️ Step 2: Chipping & Upload to Roboflow",
            "desc": "Slice Raw Raster into Chips (160/320/640/1280 px), Task Batches, Roboflow Upload",
            "action": "chip",
        },
        {
            "name": "🔑 Setup Credentials & Authentication",
            "desc": "Configure Google Earth Engine OAuth and Roboflow API credentials",
            "action": "auth",
        },
        {
            "name": "❌ Exit",
            "desc": "Exit GeoChip CLI",
            "action": "exit",
        },
    ]

    while True:
        status = get_connection_status()
        print_status_bar(gee_ready=status["gee"], roboflow_ready=status["roboflow"], work_dir=ws)

        idx = select("Select Action to Execute:", main_menu_choices, default_index=0)
        action = main_menu_choices[idx]["action"]

        if action == "quickstart":
            try:
                raster_path = interactive_download_workflow(work_dir=ws)
                if raster_path:
                    interactive_chipping_workflow(work_dir=ws, preselected_raster=raster_path)
            except KeyboardInterrupt:
                print_warning("\nQuick Start pipeline cancelled by user.")
            except Exception as exc:
                print_error(f"\nError during Quick Start pipeline: {exc}")

        elif action == "download":
            try:
                interactive_download_workflow(work_dir=ws)
            except KeyboardInterrupt:
                print_warning("\nDownload workflow cancelled by user.")
            except Exception as exc:
                print_error(f"\nError during download: {exc}")

        elif action == "chip":
            try:
                interactive_chipping_workflow(work_dir=ws)
            except KeyboardInterrupt:
                print_warning("\nChipping workflow cancelled by user.")
            except Exception as exc:
                print_error(f"\nError during chipping: {exc}")

        elif action == "auth":
            try:
                interactive_auth_menu(work_dir=ws)
            except KeyboardInterrupt:
                print_warning("\nAuthentication setup cancelled by user.")
            except Exception as exc:
                print_error(f"\nError during authentication setup: {exc}")

        elif action == "exit":
            print_info("Thank you for using GeoChip CLI. Goodbye!")
            sys.exit(0)

        print("\n" + "-" * 60)


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level ArgumentParser for GeoChip CLI."""
    parser = argparse.ArgumentParser(
        prog="GeoChip",
        description="GeoChip CLI: Interactive satellite imagery ingestion, raster chipping, and Roboflow pipeline.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"GeoChip CLI {__version__}",
    )
    parser.add_argument(
        "--work-dir",
        type=str,
        default=None,
        help="Workspace directory containing data/aoi, data/raw, and data/chips (default: current directory)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    auth_parser = subparsers.add_parser("auth", help="Manage Earth Engine and Roboflow credentials")
    auth_parser.add_argument(
        "--login", action="store_true", help="Launch browser OAuth login for Earth Engine"
    )
    auth_parser.add_argument("--project", type=str, default=None, help="Google Cloud Project ID")
    auth_parser.add_argument(
        "--roboflow", action="store_true", help="Configure Roboflow credentials"
    )

    dl_parser = subparsers.add_parser(
        "download", help="Download satellite rasters from Google Earth Engine"
    )
    dl_parser.add_argument(
        "--interactive", action="store_true", help="Launch interactive download UI"
    )

    chip_parser = subparsers.add_parser(
        "chip", help="Slice GeoTIFF raster into chip tiles & manifest.json"
    )
    chip_parser.add_argument(
        "--raster", type=str, default=None, help="Path to input GeoTIFF raster"
    )
    chip_parser.add_argument(
        "--chip-size",
        type=int,
        default=640,
        choices=[160, 320, 640, 1280],
        help="Chip tile size in pixels",
    )
    chip_parser.add_argument(
        "--chips-per-task", type=int, default=5, help="Number of chips per task batch"
    )
    chip_parser.add_argument(
        "--output-dir", type=str, default=None, help="Output base directory for chips"
    )

    upload_parser = subparsers.add_parser("upload", help="Upload task batches to Roboflow")
    upload_parser.add_argument(
        "--chips-dir", type=str, default=None, help="Directory containing chip tasks"
    )
    upload_parser.add_argument("--api-key", type=str, default=None, help="Roboflow Private API Key")
    upload_parser.add_argument(
        "--workspace", type=str, default=None, help="Roboflow Workspace Slug"
    )
    upload_parser.add_argument("--project", type=str, default=None, help="Roboflow Project ID")
    upload_parser.add_argument("--task", type=str, default="all", help="Task folder name or 'all'")

    return parser


def main() -> None:
    """Main CLI entry point supporting interactive menu and subcommands."""
    parser = build_parser()
    args = parser.parse_args()
    ws = resolve_work_dir(args.work_dir)
    load_app_env(ws)

    if not args.command:
        interactive_main_menu(work_dir=ws)
        return

    if args.command == "auth":
        if args.login:
            login_flow(project_id=args.project, work_dir=ws)
        elif args.roboflow:
            setup_roboflow_credentials(work_dir=ws)
        else:
            interactive_auth_menu(work_dir=ws)

    elif args.command == "download":
        interactive_download_workflow(work_dir=ws)

    elif args.command == "chip":
        if args.raster:
            out_base = args.output_dir or str(ws / "data" / "chips")
            create_single_raster_chips(
                raster_path=args.raster,
                output_base=out_base,
                chip_size=args.chip_size,
                chips_per_task=args.chips_per_task,
            )
        else:
            interactive_chipping_workflow(work_dir=ws)

    elif args.command == "upload":
        if args.chips_dir:
            upload_chips_to_roboflow(
                chips_dir=args.chips_dir,
                api_key=args.api_key,
                workspace_id=args.workspace,
                project_id=args.project,
                task_name=args.task,
            )
        else:
            interactive_upload_flow(work_dir=ws)


if __name__ == "__main__":
    main()
