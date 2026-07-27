from __future__ import annotations

import mimetypes
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Asset, Generation
from app.utils import file_security, utils


def sync_task_outputs(db: Session, generation: Generation, task: dict) -> list[Asset]:
    outputs = [
        ("video", path) for path in task.get("videos", [])
    ] + [("combined_video", path) for path in task.get("combined_videos", [])]
    task_directory = utils.task_dir()
    for kind, raw_path in outputs:
        if not isinstance(raw_path, str) or raw_path.startswith(("http://", "https://")):
            continue
        try:
            path = file_security.resolve_path_within_directory(task_directory, raw_path)
        except ValueError:
            continue
        if not os.path.isfile(path):
            continue
        storage_key = os.path.relpath(path, task_directory).replace("\\", "/")
        existing = db.scalar(
            select(Asset).where(
                Asset.workspace_id == generation.workspace_id,
                Asset.storage_key == storage_key,
            )
        )
        if existing is not None:
            continue
        mime_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        db.add(
            Asset(
                workspace_id=generation.workspace_id,
                project_id=generation.project_id,
                generation_id=generation.id,
                kind=kind,
                storage_key=storage_key,
                original_filename=os.path.basename(path),
                mime_type=mime_type,
                size_bytes=os.path.getsize(path),
            )
        )
    db.flush()
    return list(
        db.scalars(
            select(Asset).where(Asset.generation_id == generation.id).order_by(Asset.created_at)
        )
    )
