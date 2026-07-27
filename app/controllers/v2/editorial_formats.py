from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.controllers.v2.base import get_current_user, new_router
from app.database.models import EditorialFormat, User
from app.database.session import get_db_session
from app.models.platform_schema import (
    EditorialFormatCreateRequest,
    EditorialFormatResponse,
    EditorialFormatUpdateRequest,
)
from app.services import platform_auth, platform_editorial_formats, platform_projects

router = new_router(["V2 Editorial Formats"])


@router.get(
    "/projects/{project_id}/editorial-formats",
    response_model=list[EditorialFormatResponse],
)
def list_editorial_formats(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    platform_projects.get_project_access(db, user, project_id)
    return list(
        db.scalars(
            select(EditorialFormat)
            .where(EditorialFormat.project_id == project_id)
            .order_by(EditorialFormat.is_default.desc(), EditorialFormat.name)
        )
    )


@router.post(
    "/projects/{project_id}/editorial-formats",
    response_model=EditorialFormatResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_editorial_format(
    project_id: str,
    body: EditorialFormatCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    project = platform_projects.get_project_access(db, user, project_id, write=True)
    if body.format_type != "ranking":
        raise HTTPException(status_code=422, detail="unsupported editorial format")
    editorial_format = EditorialFormat(
        project_id=project.id,
        name=body.name.strip(),
        format_type=body.format_type,
        configuration=platform_editorial_formats.normalized_configuration(
            body.configuration
        ),
        is_default=body.is_default,
        created_by=user.id,
    )
    db.add(editorial_format)
    db.flush()
    if editorial_format.is_default:
        platform_editorial_formats.set_default_format(
            db, project.id, editorial_format.id
        )
    platform_auth.audit(
        db,
        "editorial_format.created",
        "editorial_format",
        editorial_format.id,
        user.id,
        project.workspace_id,
    )
    db.commit()
    db.refresh(editorial_format)
    return editorial_format


@router.patch(
    "/projects/{project_id}/editorial-formats/{format_id}",
    response_model=EditorialFormatResponse,
)
def update_editorial_format(
    project_id: str,
    format_id: str,
    body: EditorialFormatUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    project = platform_projects.get_project_access(db, user, project_id, write=True)
    editorial_format = platform_editorial_formats.get_format(
        db, project.id, format_id
    )
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        editorial_format.name = changes["name"].strip()
    if "configuration" in changes:
        editorial_format.configuration = (
            platform_editorial_formats.normalized_configuration(
                changes["configuration"]
            )
        )
    if changes.get("is_default"):
        platform_editorial_formats.set_default_format(
            db, project.id, editorial_format.id
        )
    elif changes.get("is_default") is False:
        editorial_format.is_default = False
    platform_auth.audit(
        db,
        "editorial_format.updated",
        "editorial_format",
        editorial_format.id,
        user.id,
        project.workspace_id,
    )
    db.commit()
    db.refresh(editorial_format)
    return editorial_format
