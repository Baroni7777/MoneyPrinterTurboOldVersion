import hashlib
import mimetypes
import os

from fastapi import Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.controllers.v2.base import get_current_user, new_router
from app.database.models import Asset, Generation, User
from app.database.session import get_db_session
from app.models.platform_schema import AssetResponse
from app.services import platform_projects
from app.utils import file_security, utils

router = new_router(["V2 Assets"])

ALLOWED_UPLOAD_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024


def _asset_response(asset: Asset) -> dict:
    return {
        "id": asset.id,
        "generation_id": asset.generation_id,
        "kind": asset.kind,
        "original_filename": asset.original_filename,
        "mime_type": asset.mime_type,
        "size_bytes": asset.size_bytes,
        "created_at": asset.created_at,
        "download_url": (
            f"/api/v2/projects/{asset.project_id}/assets/{asset.id}/download"
        ),
    }


@router.get("/projects/{project_id}/assets", response_model=list[AssetResponse])
def list_project_assets(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    platform_projects.get_project_access(db, user, project_id)
    assets = db.scalars(
        select(Asset)
        .where(Asset.project_id == project_id, Asset.kind == "source_video")
        .order_by(Asset.created_at.desc())
    )
    return [_asset_response(asset) for asset in assets]


@router.post(
    "/projects/{project_id}/assets",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_project_asset(
    project_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    project = platform_projects.get_project_access(db, user, project_id, write=True)
    content_type = file.content_type or ""
    if content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=415, detail="unsupported video format")

    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in {".mp4", ".mov", ".webm", ".mkv"}:
        extension = mimetypes.guess_extension(content_type) or ".mp4"
    relative_dir = f"project-assets/{project.id}"
    target_dir = utils.task_dir(relative_dir)
    filename = f"{utils.get_uuid()}{extension}"
    target_path = file_security.resolve_path_within_directory(
        target_dir, filename, require_file=False
    )
    digest = hashlib.sha256()
    size = 0
    try:
        with open(target_path, "wb") as output:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413, detail="video exceeds 500 MB"
                    )
                digest.update(chunk)
                output.write(chunk)
    except Exception:
        if os.path.exists(target_path):
            os.remove(target_path)
        raise
    finally:
        file.file.close()

    asset = Asset(
        workspace_id=project.workspace_id,
        project_id=project.id,
        kind="source_video",
        storage_key=f"{relative_dir}/{filename}",
        original_filename=file.filename or filename,
        mime_type=content_type,
        size_bytes=size,
        checksum=digest.hexdigest(),
        source_provider="upload",
        license_metadata={"ownership_confirmed_by": user.id},
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _asset_response(asset)


@router.get(
    "/projects/{project_id}/generations/{generation_id}/assets",
    response_model=list[AssetResponse],
)
def list_generation_assets(
    project_id: str,
    generation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    platform_projects.get_project_access(db, user, project_id)
    generation = db.get(Generation, generation_id)
    if generation is None or generation.project_id != project_id:
        raise HTTPException(status_code=404, detail="generation not found")
    assets = list(
        db.scalars(
            select(Asset).where(Asset.generation_id == generation.id).order_by(Asset.created_at)
        )
    )
    return [_asset_response(asset) for asset in assets]


@router.get("/projects/{project_id}/assets/{asset_id}/download")
def download_asset(
    project_id: str,
    asset_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    platform_projects.get_project_access(db, user, project_id)
    asset = db.get(Asset, asset_id)
    if asset is None or asset.project_id != project_id:
        raise HTTPException(status_code=404, detail="asset not found")
    try:
        path = file_security.resolve_path_within_directory(utils.task_dir(), asset.storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="asset file not found") from exc
    return FileResponse(path, media_type=asset.mime_type, filename=asset.original_filename)
