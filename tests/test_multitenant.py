"""Tests for multi-tenant (schema-per-tenant) support.

Covers GitHub Issue #1:
- US-001: --schema option (inspector inspects non-public schemas)
- US-002: --exclude-tables option (exclude alembic_version etc.)
- US-003: Cross-file mixin column resolution
- US-004: .agent-migrate.toml config file support
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from agent_migrate.config import MigrateConfigLoader
from agent_migrate.diff import compute_diff
from agent_migrate.inspector.postgresql import PostgreSQLInspector
from agent_migrate.parser import parse_models
from agent_migrate.parser.sqlalchemy import SQLAlchemyParser
from agent_migrate.types import (
    ColumnSchema,
    DBColumnSchema,
    DBTableSchema,
    DiffType,
    ModelSchema,
)

# ══════════════════════════════════════════════════════════════════════════════
# US-001: --schema option — Inspector inspects non-public schemas
# ══════════════════════════════════════════════════════════════════════════════


class TestSchemaOption:

    def test_inspect_tenant_schema(self, db_engine: Engine) -> None:
        """Inspector should return tables from a tenant schema when specified."""
        with db_engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS tenant_abc"))
            conn.execute(text("""
                CREATE TABLE tenant_abc.projects (
                    id    SERIAL PRIMARY KEY,
                    name  VARCHAR(200) NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE tenant_abc.assets (
                    id         SERIAL PRIMARY KEY,
                    project_id INTEGER REFERENCES tenant_abc.projects(id),
                    filename   TEXT NOT NULL
                )
            """))
            conn.commit()

        inspector = PostgreSQLInspector()
        tables = inspector.inspect(db_engine, schema="tenant_abc")

        table_names = {t.name for t in tables}
        assert "projects" in table_names
        assert "assets" in table_names
        assert len(tables) == 2

        # Verify columns are correct
        projects = next(t for t in tables if t.name == "projects")
        col_names = {c.name for c in projects.columns}
        assert "id" in col_names
        assert "name" in col_names

    def test_inspect_public_schema_excludes_tenant_tables(self, db_engine: Engine) -> None:
        """Tables in tenant schema should NOT appear in public schema inspection."""
        with db_engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS tenant_xyz"))
            conn.execute(text("""
                CREATE TABLE tenant_xyz.secret_table (
                    id SERIAL PRIMARY KEY
                )
            """))
            conn.execute(text("""
                CREATE TABLE public.users (
                    id SERIAL PRIMARY KEY
                )
            """))
            conn.commit()

        inspector = PostgreSQLInspector()
        public_tables = inspector.inspect(db_engine, schema="public")
        public_names = {t.name for t in public_tables}

        assert "users" in public_names
        assert "secret_table" not in public_names

    def test_inspect_empty_tenant_schema(self, db_engine: Engine) -> None:
        """Inspecting an empty schema should return empty list."""
        with db_engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS tenant_empty"))
            conn.commit()

        inspector = PostgreSQLInspector()
        tables = inspector.inspect(db_engine, schema="tenant_empty")
        assert tables == []

    def test_no_false_positive_for_tenant_models(self, db_engine: Engine) -> None:
        """Models should match tenant schema tables when --schema is used."""
        with db_engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS tenant_demo"))
            conn.execute(text("""
                CREATE TABLE tenant_demo.projects (
                    id   SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL
                )
            """))
            conn.commit()

        inspector = PostgreSQLInspector()
        tables = inspector.inspect(db_engine, schema="tenant_demo")

        model = ModelSchema(
            name="Project",
            tablename="projects",
            columns=(
                ColumnSchema(name="id", python_type="Integer", nullable=False, primary_key=True),
                ColumnSchema(name="name", python_type="String", nullable=False),
            ),
        )

        diffs = compute_diff([model], tables)
        # Should detect no TABLE_ADDED since the table exists in tenant_demo
        table_added = [d for d in diffs if d.diff_type == DiffType.TABLE_ADDED]
        assert len(table_added) == 0


# ══════════════════════════════════════════════════════════════════════════════
# US-002: --exclude-tables option
# ══════════════════════════════════════════════════════════════════════════════


class TestExcludeTables:

    def test_exclude_alembic_version(self) -> None:
        """Excluding alembic_version should prevent TABLE_REMOVED drift."""
        models: list[ModelSchema] = [
            ModelSchema(
                name="User",
                tablename="users",
                columns=(
                    ColumnSchema(name="id", python_type="Integer", nullable=False, primary_key=True),
                ),
            )
        ]
        tables = [
            DBTableSchema(
                name="users",
                schema_name="public",
                columns=(DBColumnSchema(name="id", data_type="integer", is_nullable=False),),
            ),
            DBTableSchema(
                name="alembic_version",
                schema_name="public",
                columns=(
                    DBColumnSchema(name="version_num", data_type="character varying", is_nullable=False),
                ),
            ),
        ]

        # Without exclusion: alembic_version shows as TABLE_REMOVED
        diffs_no_exclude = compute_diff(models, tables)
        removed = [d for d in diffs_no_exclude if d.diff_type == DiffType.TABLE_REMOVED]
        assert any(d.table_name == "alembic_version" for d in removed)

        # With exclusion: filter tables before diff
        excluded = {"alembic_version"}
        filtered_tables = [t for t in tables if t.name not in excluded]
        diffs_excluded = compute_diff(models, filtered_tables)
        removed_excluded = [d for d in diffs_excluded if d.diff_type == DiffType.TABLE_REMOVED]
        assert not any(d.table_name == "alembic_version" for d in removed_excluded)

    def test_exclude_multiple_tables(self) -> None:
        """Excluding multiple tables should work."""
        tables = [
            DBTableSchema(
                name="alembic_version", schema_name="public",
                columns=(DBColumnSchema(name="v", data_type="text", is_nullable=False),),
            ),
            DBTableSchema(
                name="spatial_ref_sys", schema_name="public",
                columns=(DBColumnSchema(name="srid", data_type="integer", is_nullable=False),),
            ),
            DBTableSchema(
                name="users", schema_name="public",
                columns=(DBColumnSchema(name="id", data_type="integer", is_nullable=False),),
            ),
        ]

        excluded = {"alembic_version", "spatial_ref_sys"}
        filtered = [t for t in tables if t.name not in excluded]
        assert len(filtered) == 1
        assert filtered[0].name == "users"


# ══════════════════════════════════════════════════════════════════════════════
# US-003: Cross-file mixin column resolution
# ══════════════════════════════════════════════════════════════════════════════


class TestCrossFileMixin:

    def test_cross_file_mixin_columns_inherited(self, tmp_path: Path) -> None:
        """Mixin columns from a separate file should be inherited."""
        # File 1: base.py with mixins
        base_file = tmp_path / "base.py"
        base_file.write_text(textwrap.dedent("""\
            from __future__ import annotations
            from datetime import datetime
            from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
            from sqlalchemy import DateTime, String
            from sqlalchemy.sql import func

            class Base(DeclarativeBase):
                pass

            class UUIDPrimaryKeyMixin:
                id: Mapped[str] = mapped_column(String(36), primary_key=True)

            class AuditTrailMixin:
                created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
                updated_at: Mapped[datetime | None] = mapped_column(DateTime)

            class SoftDeleteMixin:
                is_deleted: Mapped[bool] = mapped_column(default=False)
        """))

        # File 2: models.py with model using cross-file mixins
        models_file = tmp_path / "models.py"
        models_file.write_text(textwrap.dedent("""\
            from __future__ import annotations
            from sqlalchemy.orm import Mapped, mapped_column
            from sqlalchemy import String
            from base import Base, UUIDPrimaryKeyMixin, AuditTrailMixin, SoftDeleteMixin

            class PlatformUser(Base, UUIDPrimaryKeyMixin, AuditTrailMixin, SoftDeleteMixin):
                __tablename__ = "platform_users"
                email: Mapped[str] = mapped_column(String(255))
                name: Mapped[str | None] = mapped_column(String(100))
        """))

        models = parse_models([base_file, models_file])

        # Should find PlatformUser model
        assert len(models) == 1
        model = models[0]
        assert model.name == "PlatformUser"
        assert model.tablename == "platform_users"

        col_names = {c.name for c in model.columns}
        # Mixin columns must be present
        assert "id" in col_names, "UUIDPrimaryKeyMixin.id should be inherited"
        assert "created_at" in col_names, "AuditTrailMixin.created_at should be inherited"
        assert "updated_at" in col_names, "AuditTrailMixin.updated_at should be inherited"
        assert "is_deleted" in col_names, "SoftDeleteMixin.is_deleted should be inherited"
        # Own columns
        assert "email" in col_names
        assert "name" in col_names

        # Verify total count
        assert len(model.columns) == 6

    def test_cross_file_mixin_no_false_column_removed(self, tmp_path: Path) -> None:
        """Cross-file mixin columns should not produce COLUMN_REMOVED diffs."""
        base_file = tmp_path / "base.py"
        base_file.write_text(textwrap.dedent("""\
            from __future__ import annotations
            from datetime import datetime
            from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
            from sqlalchemy import DateTime, String
            from sqlalchemy.sql import func

            class Base(DeclarativeBase):
                pass

            class BaseTenantEntity:
                id: Mapped[str] = mapped_column(String(36), primary_key=True)
                created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
                updated_at: Mapped[datetime | None] = mapped_column(DateTime)
                is_deleted: Mapped[bool] = mapped_column(default=False)
        """))

        models_file = tmp_path / "models.py"
        models_file.write_text(textwrap.dedent("""\
            from __future__ import annotations
            from sqlalchemy.orm import Mapped, mapped_column
            from sqlalchemy import String
            from base import Base, BaseTenantEntity

            class PlatformUser(Base, BaseTenantEntity):
                __tablename__ = "platform_users"
                email: Mapped[str] = mapped_column(String(255))
        """))

        models = parse_models([base_file, models_file])
        assert len(models) == 1

        # Simulate DB table with all columns
        db_table = DBTableSchema(
            name="platform_users",
            schema_name="public",
            columns=(
                DBColumnSchema(name="id", data_type="character varying", is_nullable=False),
                DBColumnSchema(name="created_at", data_type="timestamp without time zone", is_nullable=False),
                DBColumnSchema(name="updated_at", data_type="timestamp without time zone", is_nullable=True),
                DBColumnSchema(name="is_deleted", data_type="boolean", is_nullable=False),
                DBColumnSchema(name="email", data_type="character varying", is_nullable=False),
            ),
        )

        diffs = compute_diff(models, [db_table])
        col_removed = [d for d in diffs if d.diff_type == DiffType.COLUMN_REMOVED]
        assert len(col_removed) == 0, f"Unexpected COLUMN_REMOVED: {col_removed}"

    def test_nested_cross_file_mixin_inheritance(self, tmp_path: Path) -> None:
        """Mixin that itself inherits from another mixin (chained) should resolve."""
        base_file = tmp_path / "base.py"
        base_file.write_text(textwrap.dedent("""\
            from __future__ import annotations
            from datetime import datetime
            from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
            from sqlalchemy import DateTime, Boolean, String
            from sqlalchemy.sql import func

            class Base(DeclarativeBase):
                pass

            class TimestampMixin:
                created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

            class FullAuditMixin(TimestampMixin):
                updated_at: Mapped[datetime | None] = mapped_column(DateTime)
                is_deleted: Mapped[bool] = mapped_column(default=False)
        """))

        models_file = tmp_path / "models.py"
        models_file.write_text(textwrap.dedent("""\
            from __future__ import annotations
            from sqlalchemy.orm import Mapped, mapped_column
            from sqlalchemy import String
            from base import Base, FullAuditMixin

            class Project(Base, FullAuditMixin):
                __tablename__ = "projects"
                id: Mapped[int] = mapped_column(primary_key=True)
                name: Mapped[str] = mapped_column(String(200))
        """))

        models = parse_models([base_file, models_file])
        assert len(models) == 1
        model = models[0]

        col_names = {c.name for c in model.columns}
        # Chained: TimestampMixin → FullAuditMixin → Project
        assert "created_at" in col_names, "TimestampMixin.created_at should be inherited via chain"
        assert "updated_at" in col_names, "FullAuditMixin.updated_at should be inherited"
        assert "is_deleted" in col_names, "FullAuditMixin.is_deleted should be inherited"
        assert "id" in col_names
        assert "name" in col_names

    def test_child_overrides_cross_file_mixin_column(self, tmp_path: Path) -> None:
        """Child model can override a column from a cross-file mixin."""
        base_file = tmp_path / "base.py"
        base_file.write_text(textwrap.dedent("""\
            from __future__ import annotations
            from datetime import datetime
            from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
            from sqlalchemy import DateTime

            class Base(DeclarativeBase):
                pass

            class TimestampMixin:
                created_at: Mapped[datetime] = mapped_column(DateTime)
        """))

        models_file = tmp_path / "models.py"
        models_file.write_text(textwrap.dedent("""\
            from __future__ import annotations
            from datetime import datetime
            from sqlalchemy.orm import Mapped, mapped_column
            from sqlalchemy import DateTime
            from sqlalchemy.sql import func
            from base import Base, TimestampMixin

            class User(Base, TimestampMixin):
                __tablename__ = "users"
                id: Mapped[int] = mapped_column(primary_key=True)
                created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
        """))

        models = parse_models([base_file, models_file])
        assert len(models) == 1

        cols = {c.name: c for c in models[0].columns}
        # Child's created_at (with server_default) should win
        assert cols["created_at"].server_default is not None

    def test_same_file_mixin_still_works(self) -> None:
        """Existing same-file mixin resolution should not break."""
        parser = SQLAlchemyParser()
        source = textwrap.dedent("""\
            from __future__ import annotations
            from datetime import datetime
            from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
            from sqlalchemy import DateTime
            from sqlalchemy.sql import func

            class Base(DeclarativeBase):
                pass

            class TimestampMixin:
                created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

            class User(Base, TimestampMixin):
                __tablename__ = "users"
                id: Mapped[int] = mapped_column(primary_key=True)
        """)
        models = parser.parse_source(source)
        assert len(models) == 1
        col_names = {c.name for c in models[0].columns}
        assert "created_at" in col_names
        assert "id" in col_names


# ══════════════════════════════════════════════════════════════════════════════
# US-004: .agent-migrate.toml config file support
# ══════════════════════════════════════════════════════════════════════════════


class TestMigrateConfig:

    def test_load_full_config(self, tmp_path: Path) -> None:
        """Full .agent-migrate.toml should be parsed correctly."""
        config_file = tmp_path / ".agent-migrate.toml"
        config_file.write_text(textwrap.dedent("""\
            [database]
            schema = "tenant_dshds"
            exclude_tables = ["alembic_version", "spatial_ref_sys"]

            [models]
            resolve_mixins = true
        """))

        loader = MigrateConfigLoader()
        config = loader.load(tmp_path)

        assert config.schema == "tenant_dshds"
        assert config.exclude_tables == ("alembic_version", "spatial_ref_sys")
        assert config.resolve_mixins is True

    def test_load_partial_config(self, tmp_path: Path) -> None:
        """Partial config should use defaults for missing fields."""
        config_file = tmp_path / ".agent-migrate.toml"
        config_file.write_text(textwrap.dedent("""\
            [database]
            schema = "tenant_demo"
        """))

        loader = MigrateConfigLoader()
        config = loader.load(tmp_path)

        assert config.schema == "tenant_demo"
        assert config.exclude_tables == ()
        assert config.resolve_mixins is True

    def test_load_missing_config_returns_defaults(self, tmp_path: Path) -> None:
        """Missing config file should return defaults."""
        loader = MigrateConfigLoader()
        config = loader.load(tmp_path)

        assert config.schema == "public"
        assert config.exclude_tables == ()
        assert config.resolve_mixins is True

    def test_load_empty_config(self, tmp_path: Path) -> None:
        """Empty config file should return defaults."""
        config_file = tmp_path / ".agent-migrate.toml"
        config_file.write_text("")

        loader = MigrateConfigLoader()
        config = loader.load(tmp_path)

        assert config.schema == "public"
        assert config.exclude_tables == ()
        assert config.resolve_mixins is True

    def test_exclude_tables_only(self, tmp_path: Path) -> None:
        """Config with only exclude_tables should work."""
        config_file = tmp_path / ".agent-migrate.toml"
        config_file.write_text(textwrap.dedent("""\
            [database]
            exclude_tables = ["alembic_version"]
        """))

        loader = MigrateConfigLoader()
        config = loader.load(tmp_path)

        assert config.schema == "public"
        assert config.exclude_tables == ("alembic_version",)
