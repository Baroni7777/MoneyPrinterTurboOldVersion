from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.controllers.v2 import (
    admin,
    api_keys,
    assets,
    auth,
    automation,
    creative,
    editorial_formats,
    projects,
)
from app.database.base import Base
from app.database.models import User, UserSession, Workspace, WorkspaceMembership
from app.database.session import (
    create_database_engine,
    create_session_factory,
    get_db_session,
)
from app.services import platform_auth

ADMIN_PASSWORD = "Admin-password-123"
USER_PASSWORD = "User-password-123"


@pytest.fixture()
def auth_context(tmp_path, monkeypatch):
    monkeypatch.setenv("MPT_AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("MPT_AUTH_PASSWORD_MIN_LENGTH", "12")
    engine = create_database_engine(
        f"sqlite:///{(tmp_path / 'auth.db').as_posix()}"
    )
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory.begin() as db:
        platform_auth.create_user_with_workspace(
            db,
            email="admin@example.com",
            password=ADMIN_PASSWORD,
            display_name="Administrator",
            system_role="admin",
        )
        platform_auth.create_user_with_workspace(
            db,
            email="user@example.com",
            password=USER_PASSWORD,
            display_name="Regular User",
        )

    application = FastAPI()
    application.include_router(auth.router)
    application.include_router(admin.router)
    application.include_router(projects.router)
    application.include_router(editorial_formats.router)
    application.include_router(creative.router)
    application.include_router(api_keys.router)
    application.include_router(automation.router)
    application.include_router(assets.router)

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    application.dependency_overrides[get_db_session] = override_db
    with TestClient(application) as client:
        yield client, session_factory
    engine.dispose()


def login(client: TestClient, email: str, password: str):
    return client.post(
        "/api/v2/auth/login",
        json={"email": email, "password": password},
    )


def test_login_me_and_logout(auth_context):
    client, session_factory = auth_context

    response = login(client, "ADMIN@EXAMPLE.COM", ADMIN_PASSWORD)
    assert response.status_code == 200
    assert response.json()["user"]["system_role"] == "admin"
    assert "mpt_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]

    me_response = client.get("/api/v2/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "admin@example.com"

    logout_response = client.post("/api/v2/auth/logout")
    assert logout_response.status_code == 204
    assert client.get("/api/v2/auth/me").status_code == 401

    with session_factory() as db:
        assert db.scalar(
            select(func.count())
            .select_from(UserSession)
            .where(UserSession.revoked_at.is_not(None))
        ) == 1


def test_invalid_login_does_not_create_session(auth_context):
    client, session_factory = auth_context

    response = login(client, "admin@example.com", "incorrect-password")

    assert response.status_code == 401
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(UserSession)) == 0

    unknown_response = login(
        client, "unknown@example.com", "incorrect-password"
    )
    assert unknown_response.status_code == 401


def test_regular_user_cannot_access_admin_api(auth_context):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200

    response = client.get("/api/v2/admin/users")

    assert response.status_code == 403


def test_admin_creates_user_and_personal_workspace(auth_context):
    client, session_factory = auth_context
    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200

    response = client.post(
        "/api/v2/admin/users",
        json={
            "email": "creator@example.com",
            "display_name": "Video Creator",
            "password": "Creator-password-123",
            "system_role": "user",
        },
    )

    assert response.status_code == 201
    user_id = response.json()["id"]
    with session_factory() as db:
        membership = db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.user_id == user_id
            )
        )
        assert membership is not None
        assert membership.role == "owner"
        assert db.get(Workspace, membership.workspace_id) is not None


def test_change_password_revokes_session(auth_context):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200

    response = client.post(
        "/api/v2/auth/change-password",
        json={
            "current_password": USER_PASSWORD,
            "new_password": "Changed-password-123",
        },
    )

    assert response.status_code == 204
    assert client.get("/api/v2/auth/me").status_code == 401
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 401
    assert (
        login(client, "user@example.com", "Changed-password-123").status_code
        == 200
    )


def test_suspending_user_revokes_access(auth_context):
    client, session_factory = auth_context
    with session_factory() as db:
        regular_user = db.scalar(
            select(User).where(User.email == "user@example.com")
        )
        user_id = regular_user.id

    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200
    response = client.patch(
        f"/api/v2/admin/users/{user_id}",
        json={"status": "suspended"},
    )
    assert response.status_code == 200

    client.cookies.clear()
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 401


def test_admin_cannot_remove_own_access(auth_context):
    client, session_factory = auth_context
    with session_factory() as db:
        admin_user = db.scalar(
            select(User).where(User.email == "admin@example.com")
        )
        admin_id = admin_user.id

    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200

    response = client.patch(
        f"/api/v2/admin/users/{admin_id}",
        json={"system_role": "user"},
    )

    assert response.status_code == 400


def test_admin_overview_requires_admin_and_reports_counts(auth_context):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    assert client.get("/api/v2/admin/overview").status_code == 403

    client.cookies.clear()
    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200
    overview = client.get("/api/v2/admin/overview")
    assert overview.status_code == 200
    assert overview.json()["users"] == 2
    assert overview.json()["active_projects"] == 0
