"""users and profile owners

Revision ID: c4e1a7d2f9b0
Revises: 9b1c957139b3
Create Date: 2026-10-09 08:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e1a7d2f9b0"
down_revision: str | None = "9b1c957139b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("google_sub", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("google_sub"),
    )
    op.add_column("profiles", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_profiles_owner_id"), "profiles", ["owner_id"], unique=False)
    op.create_foreign_key(
        "profiles_owner_id_fkey", "profiles", "users", ["owner_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint("profiles_owner_id_fkey", "profiles", type_="foreignkey")
    op.drop_index(op.f("ix_profiles_owner_id"), table_name="profiles")
    op.drop_column("profiles", "owner_id")
    op.drop_table("users")
