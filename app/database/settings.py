import os
from pathlib import Path

from sqlalchemy.engine import URL, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "storage" / "moneyprinterturbo.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"


def normalize_database_url(raw_url: str) -> str:
    """Normalize common database URLs to the drivers installed by the project."""

    url = make_url(raw_url.strip())
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


def get_database_url() -> str:
    """Resolve the platform database URL.

    ``MPT_DATABASE_URL`` is preferred. ``DATABASE_URL`` is accepted for
    hosting providers that inject that conventional name. SQLite remains the
    development and single-VPS default.
    """

    raw_url = (
        os.getenv("MPT_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )
    return normalize_database_url(raw_url)


def is_sqlite_url(database_url: str) -> bool:
    return make_url(database_url).get_backend_name() == "sqlite"


def sqlite_connect_args(database_url: str) -> dict[str, bool | int]:
    if not is_sqlite_url(database_url):
        return {}
    return {"check_same_thread": False, "timeout": 30}


def ensure_sqlite_parent(database_url: str) -> None:
    """Create the parent directory for file-backed SQLite databases."""

    url: URL = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return

    database = url.database
    if not database or database == ":memory:":
        return

    database_path = Path(database)
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
