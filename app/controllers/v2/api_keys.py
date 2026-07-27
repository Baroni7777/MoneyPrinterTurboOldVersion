from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.controllers.v2.base import get_current_user, new_router
from app.database.models import ApiKey, User
from app.database.session import get_db_session
from app.models.platform_schema import ApiKeyCreatedResponse, ApiKeyCreateRequest, ApiKeyResponse
from app.services import platform_api_keys, platform_auth, platform_projects

router = new_router(["V2 API Keys"])


@router.get("/api-keys", response_model=list[ApiKeyResponse])
def list_api_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    if user.system_role == "admin":
        return list(db.scalars(select(ApiKey).order_by(ApiKey.created_at.desc())))
    return list(db.scalars(select(ApiKey).where(ApiKey.created_by == user.id).order_by(ApiKey.created_at.desc())))


@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(body: ApiKeyCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    if body.project_id:
        project = platform_projects.get_project_access(db, user, body.project_id, write=True)
        workspace_id = project.workspace_id
    else:
        workspace = platform_projects.get_default_workspace(db, user)
        workspace_id = workspace.id
    try:
        raw_key, key = platform_api_keys.create_key(
            db,
            workspace_id=workspace_id,
            project_id=body.project_id,
            name=body.name,
            scopes=body.scopes,
            created_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    platform_auth.audit(db, "api_key.created", "api_key", key.id, user.id, workspace_id)
    db.commit()
    db.refresh(key)
    return {**ApiKeyResponse.model_validate(key).model_dump(), "key": raw_key}


@router.delete("/api-keys/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(api_key_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    key = db.get(ApiKey, api_key_id)
    if key is None or (user.system_role != "admin" and key.created_by != user.id):
        raise HTTPException(status_code=404, detail="API key not found")
    key.revoked_at = datetime.now(timezone.utc)
    platform_auth.audit(db, "api_key.revoked", "api_key", key.id, user.id, key.workspace_id)
    db.commit()
