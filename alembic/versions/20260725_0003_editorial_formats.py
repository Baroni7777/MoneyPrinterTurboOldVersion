"""Add project editorial video formats.

Revision ID: 20260725_0003
Revises: 20260724_0002
Create Date: 2026-07-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260725_0003"
down_revision: str | None = "20260724_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "editorial_formats",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("format_type", sa.String(length=64), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "name", name="uq_editorial_formats_name"
        ),
    )
    op.create_index(
        "ix_editorial_formats_project_default",
        "editorial_formats",
        ["project_id", "is_default"],
    )
    with op.batch_alter_table("generations") as batch_op:
        batch_op.add_column(
            sa.Column("editorial_format_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "editorial_format_snapshot",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.create_foreign_key(
            "fk_generations_editorial_format_id",
            "editorial_formats",
            ["editorial_format_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("generations") as batch_op:
        batch_op.drop_constraint(
            "fk_generations_editorial_format_id", type_="foreignkey"
        )
        batch_op.drop_column("editorial_format_snapshot")
        batch_op.drop_column("editorial_format_id")
    op.drop_index(
        "ix_editorial_formats_project_default",
        table_name="editorial_formats",
    )
    op.drop_table("editorial_formats")
