from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.controllers.v2.base import get_current_user, new_router
from app.database.models import User
from app.database.session import get_db_session
from app.models.platform_schema import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    UserResponse,
)
from app.platform.settings import get_auth_settings
from app.services import platform_auth

router = new_router(["V2 Auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_auth_settings()
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_auth_settings()
    response.delete_cookie(
        key=settings.cookie_name,
        domain=settings.cookie_domain,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


@router.post("/auth/login", response_model=AuthResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
):
    user = platform_auth.authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
        )
    token, _ = platform_auth.create_user_session(
        db,
        user,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )
    platform_auth.audit(db, "auth.login", "user", user.id, user.id)
    db.commit()
    _set_session_cookie(response, token)
    return {"user": user}


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
):
    settings = get_auth_settings()
    platform_auth.revoke_session(
        db, request.cookies.get(settings.cookie_name)
    )
    db.commit()
    _clear_session_cookie(response)


@router.get("/auth/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    if not platform_auth.verify_password(user.password_hash, body.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="current password is incorrect",
        )
    try:
        user.password_hash = platform_auth.hash_password(body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    platform_auth.revoke_all_user_sessions(db, user.id)
    platform_auth.audit(
        db, "auth.password_changed", "user", user.id, user.id
    )
    db.commit()
    _clear_session_cookie(response)
