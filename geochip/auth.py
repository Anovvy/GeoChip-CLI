"""
Google Earth Engine & Roboflow Authentication and Credentials Management.
Provides interactive login, connection status checks, and masked credential setup.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import (
    extract_roboflow_slug,
    is_valid_credential_val,
    load_app_env,
    mask_secret,
    save_env_variable,
)
from .ui import (
    print_error,
    print_info,
    print_step,
    print_success,
    print_warning,
    prompt_confirm,
    prompt_input,
    prompt_secret,
    select,
    spinner,
)

load_app_env()


def get_ee_project_id() -> str | None:
    """Retrieve the configured Earth Engine GCP project ID."""
    val = os.getenv("EE_PROJECT_ID", "").strip()
    return val if is_valid_credential_val(val) else None


def get_connection_status() -> dict[str, bool]:
    """Perform a fast local check of Earth Engine and Roboflow credential readiness."""
    ee_creds_file = Path.home() / ".config" / "earthengine" / "credentials"
    gee_ready = ee_creds_file.is_file() or bool(get_ee_project_id())

    rf_key = os.getenv("ROBOFLOW_API_KEY", "").strip()
    rf_ws = os.getenv("ROBOFLOW_WORKSPACE", "").strip()
    rf_proj = os.getenv("ROBOFLOW_PROJECT", "").strip()
    roboflow_ready = (
        is_valid_credential_val(rf_key)
        and is_valid_credential_val(rf_ws)
        and is_valid_credential_val(rf_proj)
    )
    return {"gee": gee_ready, "roboflow": roboflow_ready}


def init_earth_engine(project_id: str | None = None) -> bool:
    """Initialize Google Earth Engine using cached OAuth credentials."""
    import ee

    project_id = project_id or get_ee_project_id()

    try:
        if project_id:
            ee.Initialize(project=project_id)
            print_info(f"Earth Engine initialized (Project: {project_id})")
        else:
            ee.Initialize()
            print_info("Earth Engine initialized (Default Project)")
        return True
    except Exception as exc:
        print_warning(f"Google Earth Engine is not authenticated: {exc}")
        return False


def login_flow(project_id: str | None = None, work_dir: Path | None = None) -> bool:
    """Trigger browser OAuth authentication for Google Earth Engine."""
    import ee

    print_step("Google Earth Engine - Browser OAuth Login")

    try:
        print_info("Opening browser for Google authentication...")
        try:
            ee.Authenticate()
        except Exception:
            print_info("Browser auto-open unavailable. Switching to verification-code flow...")
            ee.Authenticate(auth_mode="notebook")

        print_success("Authentication token saved to local credentials cache.")

        current_proj = project_id if is_valid_credential_val(project_id) else get_ee_project_id()
        print_info("\nEnter the Google Cloud Project ID linked to your Earth Engine account.")
        print_info("Check your Project ID at: https://console.cloud.google.com/welcome\n")
        project_id = prompt_input(
            "GCP Project ID (e.g., my-gee-project-123)",
            default=current_proj,
        ).strip()

        if project_id:
            save_env_variable("EE_PROJECT_ID", project_id, work_dir=work_dir)
            print_success(f"Project ID '{project_id}' saved.")

        with spinner("Verifying Earth Engine initialization..."):
            if project_id:
                ee.Initialize(project=project_id)
            else:
                ee.Initialize()

        print_success("Google Earth Engine is ready to use.")
        return True

    except Exception as exc:
        print_error(f"Login or initialization failed: {exc}")
        err_str = str(exc).lower()
        if "not registered" in err_str and project_id:
            print_warning(f"\nProject '{project_id}' is not registered for Earth Engine yet:")
            print_info(
                f"  1. Open: https://console.cloud.google.com/earth-engine/configuration?project={project_id}"
            )
            print_info(
                "  2. Select 'Unpaid / Noncommercial' (or your appropriate tier) and confirm."
            )
        else:
            print_info(
                f"Verify Earth Engine API is enabled: "
                f"https://console.cloud.google.com/apis/library/earthengine.googleapis.com?project={project_id or ''}"
            )
        return False


def setup_roboflow_credentials(work_dir: Path | None = None) -> None:
    """Interactive Roboflow API credentials setup with masked secret input."""
    load_app_env(work_dir)
    print_step("Roboflow Credentials Setup")

    raw_key = os.getenv("ROBOFLOW_API_KEY", "").strip()
    raw_ws = os.getenv("ROBOFLOW_WORKSPACE", "").strip()
    raw_proj = os.getenv("ROBOFLOW_PROJECT", "").strip()

    current_key = raw_key if is_valid_credential_val(raw_key) else None
    current_ws = raw_ws if is_valid_credential_val(raw_ws) else None
    current_proj = raw_proj if is_valid_credential_val(raw_proj) else None

    print_info("How to find your Roboflow credentials:")
    print_info("  1. Private API Key : app.roboflow.com -> Settings -> Roboflow API")
    print_info("  2. Workspace Slug  : app.roboflow.com/<workspace-slug>")
    print_info("  3. Project ID      : app.roboflow.com/<workspace-slug>/<project-id>\n")

    api_key = prompt_secret("Roboflow Private API Key", existing_value=current_key)
    raw_workspace = prompt_input("Roboflow Workspace ID / Slug", default=current_ws)
    raw_project = prompt_input("Target Roboflow Project ID", default=current_proj)

    workspace = extract_roboflow_slug(raw_workspace)
    project = extract_roboflow_slug(raw_project)

    if raw_workspace and raw_workspace.strip() != workspace:
        print_info(f"Cleaned Workspace URL to slug: '{workspace}'")
    if raw_project and raw_project.strip() != project:
        print_info(f"Cleaned Project URL to slug: '{project}'")

    if api_key:
        save_env_variable("ROBOFLOW_API_KEY", api_key, work_dir=work_dir)
    if workspace:
        save_env_variable("ROBOFLOW_WORKSPACE", workspace, work_dir=work_dir)
    if project:
        save_env_variable("ROBOFLOW_PROJECT", project, work_dir=work_dir)

    print_success(f"Roboflow credentials saved (Key: {mask_secret(api_key)}).")

    if (
        api_key
        and workspace
        and project
        and prompt_confirm("Test Roboflow connection now?", default=True)
    ):
        try:
            with spinner("Connecting to Roboflow..."):
                from roboflow import Roboflow

                rf = Roboflow(api_key=api_key)
                proj_obj = rf.workspace(workspace).project(project)
            print_success(
                f"Connected to Roboflow project '{workspace}/{project}' ({proj_obj.name})."
            )
        except Exception as exc:
            print_error(f"Could not connect to Roboflow: {exc}")
            print_warning("Verify your API key and workspace/project slug.")


def test_all_connections(work_dir: Path | None = None) -> None:
    """Run a live diagnostic test for Google Earth Engine and Roboflow."""
    load_app_env(work_dir)
    print_step("Diagnostic Connection Test")

    print_info("Testing Google Earth Engine...")
    if init_earth_engine():
        try:
            with spinner("Running Earth Engine compute check..."):
                import ee

                test_val = ee.Number(42).getInfo()
            print_success(f"Earth Engine compute check passed (Result: {test_val}).")
        except Exception as exc:
            print_error(f"Earth Engine compute failed: {exc}")
    else:
        print_error("Earth Engine connection failed. Run Google Earth Engine Login.")

    print("\n" + "-" * 40)
    print_info("Testing Roboflow credentials...")
    rf_key = os.getenv("ROBOFLOW_API_KEY", "").strip()
    rf_ws = extract_roboflow_slug(os.getenv("ROBOFLOW_WORKSPACE", ""))
    rf_proj = extract_roboflow_slug(os.getenv("ROBOFLOW_PROJECT", ""))

    if not (is_valid_credential_val(rf_key) and rf_ws and rf_proj):
        print_warning(
            "Roboflow credentials are not configured yet (optional for local-only chipping)."
        )
    else:
        try:
            with spinner("Connecting to Roboflow..."):
                from roboflow import Roboflow

                rf = Roboflow(api_key=rf_key)
                rf.workspace(rf_ws).project(rf_proj)
            print_success(f"Roboflow verified: '{rf_ws}/{rf_proj}' (Key: {mask_secret(rf_key)}).")
        except Exception as exc:
            print_error(f"Roboflow check failed: {exc}")

    print("\n" + "=" * 60)


test_earth_engine_connection = test_all_connections


def interactive_auth_menu(work_dir: Path | None = None) -> None:
    """Interactive authentication and credentials submenu."""
    print_step("Credentials & Authentication Setup")

    auth_choices = [
        {
            "name": "🌐 Google Earth Engine Login (Browser OAuth)",
            "desc": "Sign in with Google via browser and set your GCP Project ID",
            "action": "gee",
        },
        {
            "name": "🤖 Setup Roboflow API Credentials",
            "desc": "Configure Private API Key, Workspace Slug, and Target Project ID",
            "action": "roboflow",
        },
        {
            "name": "🔍 Test Connections & Diagnostic Status",
            "desc": "Verify live connectivity to Google Earth Engine and Roboflow",
            "action": "test",
        },
        {
            "name": "⬅️ Back to Main Menu",
            "desc": "Return to the main GeoChip CLI menu",
            "action": "back",
        },
    ]

    while True:
        idx = select("Select Authentication Action:", auth_choices, default_index=0)
        action = auth_choices[idx]["action"]

        if action == "gee":
            login_flow(work_dir=work_dir)
        elif action == "roboflow":
            setup_roboflow_credentials(work_dir=work_dir)
        elif action == "test":
            test_all_connections(work_dir=work_dir)
        elif action == "back":
            break
        print("\n")
