from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.database.settings import (
    ensure_sqlite_parent,
    get_database_url,
    sqlite_connect_args,
)


def create_database_engine(database_url: str | None = None) -> Engine:
    resolved_url = database_url or get_database_url()
    ensure_sqlite_parent(resolved_url)
    database_engine = create_engine(
        resolved_url,
        connect_args=sqlite_connect_args(resolved_url),
        pool_pre_ping=True,
    )
    if database_engine.dialect.name == "sqlite":

        @event.listens_for(database_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
            del connection_record
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return database_engine


def create_session_factory(
    database_engine: Engine,
) -> sessionmaker[Session]:
    return sessionmaker(
        bind=database_engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


engine = create_database_engine()
SessionLocal = create_session_factory(engine)


def get_db_session() -> Generator[Session, None, None]:
    """Yield one SQLAlchemy session for a FastAPI request."""

    with SessionLocal() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
