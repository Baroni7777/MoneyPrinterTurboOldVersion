from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by every platform model."""


def new_uuid() -> str:
    """Return a portable UUID value stored as a 36-character string."""

    return str(uuid4())


def utc_now() -> datetime:
    """Return an aware UTC timestamp for Python-side defaults."""

    return datetime.now(timezone.utc)
