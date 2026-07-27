from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database.models import User
from app.database.session import get_db_session
from app.platform.settings import get_auth_settings
from app.services import platform_api_keys, platform_auth


def new_router(tags: list[str]) -> APIRouter:
    return APIRouter(prefix="/api/v2", tags=tags)


def get_current_user(
    request: Request, db: Session = Depends(get_db_session)
) -> User:
    settings = get_auth_settings()
    user = platform_auth.resolve_session(
        db, request.cookies.get(settings.cookie_name)
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    db.commit()
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.system_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="administrator access required",
        )
    return user


def get_api_key_actor(
    request: Request, db: Session = Depends(get_db_session)
) -> platform_api_keys.ApiKeyActor:
    actor = platform_api_keys.get_api_key_actor(request, db)
    platform_api_keys.enforce_rate_limit(actor)
    db.commit()
    return actor
