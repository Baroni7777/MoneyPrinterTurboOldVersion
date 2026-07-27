from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.controllers.v2.base import new_router, require_admin
from app.database.models import Asset, Generation, Project, User
from app.database.session import get_db_session
from app.models.platform_schema import (
    AdminOverviewResponse,
    GenerationResponse,
    PasswordResetRequest,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.services import platform_auth

router = new_router(["V2 Admin"])


@router.get("/admin/overview", response_model=AdminOverviewResponse)
def get_overview(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
):
    del admin
    generation_counts = dict(
        db.execute(
            select(Generation.status, func.count()).group_by(Generation.status)
        ).all()
    )
    return {
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "active_projects": db.scalar(
            select(func.count()).select_from(Project).where(Project.status == "active")
        ) or 0,
        "queued_generations": generation_counts.get("queued", 0),
        "processing_generations": generation_counts.get("processing", 0),
        "failed_generations": generation_counts.get("failed", 0),
        "completed_generations": generation_counts.get("completed", 0),
        "stored_asset_bytes": db.scalar(
            select(func.coalesce(func.sum(Asset.size_bytes), 0))
        )
        or 0,
    }


@router.get("/admin/generations", response_model=list[GenerationResponse])
def list_all_generations(
    limit: int = Query(default=100, ge=1, le=500),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
):
    del admin
    return list(
        db.scalars(
            select(Generation).order_by(Generation.created_at.desc()).limit(limit)
        )
    )


@router.get("/admin/users", response_model=list[UserResponse])
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
):
    del admin
    return list(db.scalars(select(User).order_by(User.created_at.desc())))


@router.post(
    "/admin/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    body: UserCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
):
    try:
        user = platform_auth.create_user_with_workspace(
            db,
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            system_role=body.system_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    platform_auth.audit(db, "admin.user_created", "user", user.id, admin.id)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/admin/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    body: UserUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    changes = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (
        changes.get("status") == "suspended"
        or changes.get("system_role") == "user"
    ):
        raise HTTPException(
            status_code=400,
            detail="cannot remove your own administrator access",
        )
    for field, value in changes.items():
        setattr(user, field, value)
    if user.status != "active":
        platform_auth.revoke_all_user_sessions(db, user.id)
    platform_auth.audit(db, "admin.user_updated", "user", user.id, admin.id)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/admin/users/{user_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
def reset_password(
    user_id: str,
    body: PasswordResetRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    try:
        user.password_hash = platform_auth.hash_password(body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user.status = "active"
    platform_auth.revoke_all_user_sessions(db, user.id)
    platform_auth.audit(
        db, "admin.password_reset", "user", user.id, admin.id
    )
    db.commit()
