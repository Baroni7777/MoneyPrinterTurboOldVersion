"""Database infrastructure for the multi-user platform.

The legacy API does not import this package, so introducing the platform
database does not change the current v1 runtime. Session objects are kept in
``app.database.session`` and are intentionally not imported here, avoiding
engine creation as a side effect of importing model metadata or Alembic.
"""

from app.database.base import Base

__all__ = ["Base"]
