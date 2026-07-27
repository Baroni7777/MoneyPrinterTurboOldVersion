import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.database.base import Base
from app.database.models import User, Workspace, WorkspaceMembership
from app.database.session import create_database_engine, create_session_factory
from app.database.settings import (
    get_database_url,
    normalize_database_url,
    sqlite_connect_args,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_default_database_url_uses_persistent_storage(monkeypatch):
    monkeypatch.delenv("MPT_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    database_url = get_database_url()

    assert database_url.startswith("sqlite:///")
    assert database_url.endswith("/storage/moneyprinterturbo.db")


def test_mpt_database_url_has_precedence(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///ignored.db")
    monkeypatch.setenv("MPT_DATABASE_URL", "sqlite:///preferred.db")

    assert get_database_url() == "sqlite:///preferred.db"


def test_postgresql_url_uses_installed_psycopg_driver():
    normalized = normalize_database_url(
        "postgresql://user:password@postgres:5432/moneyprinterturbo"
    )

    assert normalized.startswith("postgresql+psycopg://")
    assert "user:password@postgres:5432/moneyprinterturbo" in normalized
    assert sqlite_connect_args(normalized) == {}


def test_sqlite_engine_enforces_foreign_keys(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'foreign-keys.db').as_posix()}"
    engine = create_database_engine(database_url)

    with engine.connect() as connection:
        enabled = connection.execute(text("PRAGMA foreign_keys")).scalar_one()

    assert enabled == 1
    engine.dispose()


def test_platform_models_round_trip_with_sqlite(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'models.db').as_posix()}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory.begin() as session:
        user = User(
            email="owner@example.com",
            password_hash="not-a-real-password-hash",
            display_name="Owner",
            system_role="user",
            status="active",
        )
        workspace = Workspace(name="Owner workspace", slug="owner-workspace")
        membership = WorkspaceMembership(
            workspace=workspace,
            user=user,
            role="owner",
        )
        session.add(membership)

    with session_factory() as session:
        stored_user = session.scalar(
            select(User).where(User.email == "owner@example.com")
        )
        assert stored_user is not None
        assert stored_user.memberships[0].workspace.slug == "owner-workspace"

    engine.dispose()


def test_workspace_membership_rejects_unknown_user(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'constraints.db').as_posix()}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory.begin() as session:
        workspace = Workspace(name="Workspace", slug="workspace")
        session.add(workspace)

    with pytest.raises(IntegrityError):
        with session_factory.begin() as session:
            session.add(
                WorkspaceMembership(
                    workspace_id=workspace.id,
                    user_id="00000000-0000-0000-0000-000000000000",
                    role="owner",
                )
            )

    engine.dispose()


def test_initial_alembic_migration_upgrades_and_downgrades_sqlite(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "migration.db"
    monkeypatch.setenv(
        "MPT_DATABASE_URL", f"sqlite:///{database_path.as_posix()}"
    )
    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))

    command.upgrade(alembic_config, "head")

    engine = create_database_engine(os.environ["MPT_DATABASE_URL"])
    table_names = set(inspect(engine).get_table_names())
    assert {
        "alembic_version",
        "users",
        "user_sessions",
        "workspaces",
        "workspace_memberships",
        "projects",
        "creative_profiles",
        "generation_presets",
        "editorial_formats",
        "generations",
        "assets",
        "api_keys",
        "audit_logs",
    }.issubset(table_names)
    engine.dispose()

    command.downgrade(alembic_config, "base")

    downgraded_engine = create_database_engine(os.environ["MPT_DATABASE_URL"])
    assert set(inspect(downgraded_engine).get_table_names()) == {
        "alembic_version"
    }
    downgraded_engine.dispose()
