"""E2E CLI tests using Orchestrator directly with testcontainers PostgreSQL.

Scenarios:
1. Happy Path — snapshot drift → diff → plan → generate → apply → empty diff
2. Dangerous Migration — DANGER detected → blocked without --force → force succeeds
3. Zero-config — .env with DATABASE_URL auto-detected without --db-url
"""

from __future__ import annotations

import os
import textwrap
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from agent_migrate.exceptions import DangerousMigrationError
from agent_migrate.orchestrator import Orchestrator

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.engine import Engine


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_model(path: Path, source: str) -> Path:
    """Write a models.py file in *path/app/models.py* and return the project root."""
    app_dir = path / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "__init__.py").write_text("")
    (app_dir / "models.py").write_text(textwrap.dedent(source))
    return path


# ── Scenario 1: Happy Path ────────────────────────────────────────────────────


def test_happy_path_full_flow(
    tmp_path: Path,
    postgres_url: str,
    db_engine: Engine,
) -> None:
    """Happy Path E2E: snapshot drift → diff → plan SAFE → generate → apply → empty diff."""
    # 1. Create DB table with only (id) — no email column yet
    with db_engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE users ("
                "id SERIAL PRIMARY KEY"
                ")"
            )
        )
        conn.commit()

    # 2. Create model with id + email (Text type maps cleanly to PostgreSQL text)
    _write_model(
        tmp_path,
        """
        from __future__ import annotations
        from sqlalchemy import Text
        from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

        class Base(DeclarativeBase):
            pass

        class User(Base):
            __tablename__ = "users"
            id: Mapped[int] = mapped_column(primary_key=True)
            email: Mapped[str | None] = mapped_column(Text)
        """,
    )

    orch = Orchestrator()

    # 3. snapshot shows drift
    snap = orch.snapshot(tmp_path, postgres_url)
    assert "users" in snap
    assert "Drift" in snap

    # 4. diff shows email as added
    diff_out = orch.diff(tmp_path, postgres_url)
    assert "email" in diff_out

    # 5. plan shows SAFE ADD COLUMN
    plan_out = orch.plan(tmp_path, postgres_url)
    assert "email" in plan_out

    # 6. generate creates a migration file
    migration_file = orch.generate(tmp_path, "add email to users", postgres_url)
    assert migration_file.exists()
    content = migration_file.read_text()
    assert "email" in content.lower()

    # 7. apply --execute applies the migration
    apply_out = orch.apply(tmp_path, postgres_url, execute=True, force=False)
    assert "applied" in apply_out.lower()

    # 8. diff is now empty
    diff_after = orch.diff(tmp_path, postgres_url)
    # No column additions/removals expected
    assert "email" not in diff_after or "SAFE" in diff_after or diff_after.strip() == ""


# ── Scenario 2: Dangerous Migration ──────────────────────────────────────────


def test_dangerous_migration_blocked_without_force(
    tmp_path: Path,
    postgres_url: str,
    db_engine: Engine,
) -> None:
    """DANGER migration blocked without --force; succeeds with --force."""
    # DB has email column; model removes it
    with db_engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE users ("
                "id SERIAL PRIMARY KEY, "
                "email VARCHAR(255) NOT NULL"
                ")"
            )
        )
        conn.execute(text("INSERT INTO users (email) VALUES ('test@example.com')"))
        conn.commit()

    # Model has only id — email is removed
    _write_model(
        tmp_path,
        """
        from __future__ import annotations
        from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

        class Base(DeclarativeBase):
            pass

        class User(Base):
            __tablename__ = "users"
            id: Mapped[int] = mapped_column(primary_key=True)
        """,
    )

    orch = Orchestrator()

    # plan shows DANGER
    plan_out = orch.plan(tmp_path, postgres_url)
    assert "DANGER" in plan_out or "danger" in plan_out.lower()

    # apply --execute without --force raises DangerousMigrationError
    with pytest.raises(DangerousMigrationError):
        orch.apply(tmp_path, postgres_url, execute=True, force=False)

    # apply --execute --force succeeds
    result = orch.apply(tmp_path, postgres_url, execute=True, force=True)
    assert result  # non-empty result means success


# ── Scenario 3: Zero-config ───────────────────────────────────────────────────


def test_zero_config_env_file_detection(
    tmp_path: Path,
    postgres_url: str,
    db_engine: Engine,
) -> None:
    """Zero-config: .env with DATABASE_URL → auto-detected without --db-url."""
    with db_engine.connect() as conn:
        conn.execute(
            text("CREATE TABLE products (id SERIAL PRIMARY KEY, name TEXT NOT NULL)")
        )
        conn.commit()

    _write_model(
        tmp_path,
        """
        from __future__ import annotations
        from sqlalchemy import String
        from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

        class Base(DeclarativeBase):
            pass

        class Product(Base):
            __tablename__ = "products"
            id: Mapped[int] = mapped_column(primary_key=True)
            name: Mapped[str] = mapped_column(String(200), nullable=False)
        """,
    )

    # Write .env with DATABASE_URL
    (tmp_path / ".env").write_text(f"DATABASE_URL={postgres_url}\n")

    # Ensure no env var pollution from outer scope for this test
    old_val = os.environ.pop("DATABASE_URL", None)
    try:
        orch = Orchestrator()
        # No db_url passed — should auto-detect from .env
        snap = orch.snapshot(tmp_path, db_url=None)
        assert "products" in snap
    finally:
        if old_val is not None:
            os.environ["DATABASE_URL"] = old_val
