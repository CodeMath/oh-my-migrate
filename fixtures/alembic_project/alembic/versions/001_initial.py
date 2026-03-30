"""Initial schema.

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text('CREATE TABLE "users" ("id" SERIAL PRIMARY KEY, "email" VARCHAR(255) NOT NULL);'))


def downgrade() -> None:
    op.execute(text('DROP TABLE "users";'))
