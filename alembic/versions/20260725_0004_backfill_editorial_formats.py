"""Create a default ranking format for existing projects.

Revision ID: 20260725_0004
Revises: 20260725_0003
Create Date: 2026-07-25
"""

from collections.abc import Sequence
from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa

revision: str = "20260725_0004"
down_revision: str | None = "20260725_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_CONFIGURATION = {
    "ranking_size": 5,
    "aspect_ratio": "9:16",
    "order": "countdown",
    "title_template": "RANKING BEST {{topic}}",
    "font_family": "Anton",
    "title_color": "#ffffff",
    "accent_color": "#ff3344",
    "secondary_color": "#ffd43b",
    "outline_color": "#000000",
    "title_size": 54,
    "item_size": 42,
    "outline_width": 3,
    "title_position": {"x": 50, "y": 7},
    "ranking_position": {"x": 8, "y": 24},
    "clip_duration": 7,
    "transition": "cut",
    "show_full_ranking": True,
    "show_watermark": False,
    "watermark_text": "",
    "source_audio": True,
}


def upgrade() -> None:
    connection = op.get_bind()
    projects = sa.table(
        "projects",
        sa.column("id", sa.String),
        sa.column("created_by", sa.String),
    )
    formats = sa.table(
        "editorial_formats",
        sa.column("id", sa.String),
        sa.column("project_id", sa.String),
        sa.column("name", sa.String),
        sa.column("format_type", sa.String),
        sa.column("configuration", sa.JSON),
        sa.column("is_default", sa.Boolean),
        sa.column("created_by", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    existing_projects = {
        row[0] for row in connection.execute(sa.select(formats.c.project_id))
    }
    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "name": "Ranking Top 5",
            "format_type": "ranking",
            "configuration": DEFAULT_CONFIGURATION,
            "is_default": True,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
        for project_id, created_by in connection.execute(
            sa.select(projects.c.id, projects.c.created_by)
        )
        if project_id not in existing_projects
    ]
    if rows:
        op.bulk_insert(formats, rows)


def downgrade() -> None:
    # Keep user-visible formats on downgrade; deleting by name could remove a
    # format that the user already customized after the migration.
    pass
