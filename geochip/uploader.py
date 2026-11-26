"""
GeoChip Roboflow Batch Annotation Uploader.
Uploads task chip folders as distinct annotation batches into Roboflow projects.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import (
    ensure_workspace_dirs,
    extract_roboflow_slug,
    is_valid_credential_val,
    load_app_env,
    resolve_work_dir,
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


def get_roboflow_credentials() -> tuple[str, str, str]:
    """Extract Roboflow credentials from environment variables."""
    api_key = (os.getenv("ROBOFLOW_API_KEY") or "").strip()
    workspace_id = extract_roboflow_slug(os.getenv("ROBOFLOW_WORKSPACE"))
    project_id = extract_roboflow_slug(os.getenv("ROBOFLOW_PROJECT"))
    return api_key, workspace_id, project_id


def save_credentials_to_env(
    api_key: str,
    workspace_id: str,
    project_id: str,
    work_dir: Path | None = None,
) -> None:
    """Persist Roboflow credentials cleanly."""
    save_env_variable("ROBOFLOW_API_KEY", api_key, work_dir=work_dir)
    save_env_variable("ROBOFLOW_WORKSPACE", workspace_id, work_dir=work_dir)
    save_env_variable("ROBOFLOW_PROJECT", project_id, work_dir=work_dir)
    print_success("Roboflow credentials saved.")


def upload_chips_to_roboflow(
    chips_dir: str | Path,
    api_key: str | None = None,
    workspace_id: str | None = None,
    project_id: str | None = None,
    task_name: str = "all",
) -> bool:
    """Push task chip folders into a Roboflow project as annotation batches."""
    chips_path = Path(chips_dir)
    if not chips_path.exists():
        print_error(f"Chips directory '{chips_path}' not found.")
        return False

    env_key, env_ws, env_proj = get_roboflow_credentials()
    api_key = api_key or env_key
    workspace_id = extract_roboflow_slug(workspace_id) or env_ws
    project_id = extract_roboflow_slug(project_id) or env_proj

    if not (is_valid_credential_val(api_key) and workspace_id and project_id):
        print_error("Roboflow credentials are incomplete. Run 'GeoChip auth --roboflow' first.")
        return False

    try:
        with spinner(f"Connecting to Roboflow ({workspace_id}/{project_id})..."):
            from roboflow import Roboflow

            rf = Roboflow(api_key=api_key)
            project = rf.workspace(workspace_id).project(project_id)
        print_success(f"Connected to Roboflow project '{project_id}'.")
    except Exception as exc:
        print_error(f"Failed to connect to Roboflow: {exc}")
        return False

    if task_name == "all":
        task_folders = sorted(
            [f for f in chips_path.iterdir() if f.is_dir() and f.name.startswith("task")]
        )
    else:
        target_folder = chips_path / task_name
        if not target_folder.exists():
            print_error(f"Task folder '{target_folder}' does not exist.")
            return False
        task_folders = [target_folder]

    if not task_folders:
        print_warning(f"No task batch folders found inside '{chips_path}'.")
        return False

    print_info(f"Found {len(task_folders)} task batch folder(s) ready for upload.\n")

    total_uploaded = 0
    total_skipped = 0

    for task_folder in task_folders:
        batch_name = task_folder.name
        img_files = sorted(list(task_folder.glob("*.png")) + list(task_folder.glob("*.jpg")))
        print(f"\n---> Uploading Batch: {batch_name} ({len(img_files)} images)...")

        for img_path in img_files:
            try:
                project.upload(
                    image_path=str(img_path),
                    batch_name=batch_name,
                    num_retry_uploads=3,
                )
                print(f"      [OK] Uploaded: {img_path.name}")
                total_uploaded += 1
            except Exception as exc:
                err_msg = str(exc)
                if "duplicate" in err_msg.lower() or "already exists" in err_msg.lower():
                    print(f"      [SKIP] {img_path.name} (already uploaded)")
                    total_skipped += 1
                else:
                    print(f"      [ERROR] Failed to upload {img_path.name}: {err_msg}")

    print_success(
        f"\nUpload complete! Uploaded {total_uploaded} image(s) (Skipped: {total_skipped})."
    )
    print_info(f"Annotate at: https://app.roboflow.com/{workspace_id}/{project_id}/annotate")
    return True


def interactive_upload_flow(
    chips_dir_path: str | Path | None = None,
    work_dir: Path | None = None,
) -> None:
    """Interactive Roboflow batch upload flow."""
    ws = resolve_work_dir(work_dir)
    load_app_env(ws)
    dirs = ensure_workspace_dirs(ws)

    print_step("Roboflow Batch Uploader")

    if not chips_dir_path:
        base_chips = dirs["chips"]
        candidate_dirs = sorted([d for d in base_chips.iterdir() if d.is_dir()])
        if not candidate_dirs:
            print_error(f"No chip directories found in '{base_chips}'. Run Step 2 first.")
            return

        choices = [{"name": d.name, "desc": f"Path: {d}"} for d in candidate_dirs]
        idx = select("Select Chip Dataset Folder to Upload:", choices)
        chips_dir_path = candidate_dirs[idx]

    chips_dir = Path(chips_dir_path)
    print_info(f"Target folder: {chips_dir}")

    api_key, workspace_id, project_id = get_roboflow_credentials()

    if not is_valid_credential_val(api_key):
        print_info("Roboflow Private API Key is not set.")
        api_key = prompt_secret("Enter Roboflow Private API Key")
    if not is_valid_credential_val(workspace_id):
        workspace_id = extract_roboflow_slug(prompt_input("Enter Roboflow Workspace Slug / ID"))
    if not is_valid_credential_val(project_id):
        project_id = extract_roboflow_slug(prompt_input("Enter Target Roboflow Project ID"))

    print_info(f"Active configuration: Workspace='{workspace_id}' | Project='{project_id}'")
    if prompt_confirm("Use this target project?", default=True):
        target_project = project_id
    else:
        target_project = extract_roboflow_slug(
            prompt_input("Enter alternative Roboflow Project ID", default=project_id)
        )

    save_credentials_to_env(api_key, workspace_id, target_project, work_dir=ws)

    task_options = [
        {"name": "📦 Upload All Task Batches Simultaneously", "action": "all"},
        {"name": "🎯 Select a Specific Task Batch", "action": "specific"},
    ]
    t_idx = select("Select Upload Scope:", task_options)

    if task_options[t_idx]["action"] == "specific":
        sub_tasks = sorted(
            [f.name for f in chips_dir.iterdir() if f.is_dir() and f.name.startswith("task")]
        )
        if not sub_tasks:
            print_error(f"No task subfolders found in '{chips_dir}'.")
            return
        st_idx = select("Select Task Batch:", sub_tasks)
        task_name = sub_tasks[st_idx]
    else:
        task_name = "all"

    upload_chips_to_roboflow(
        chips_dir=chips_dir,
        api_key=api_key,
        workspace_id=workspace_id,
        project_id=target_project,
        task_name=task_name,
    )
