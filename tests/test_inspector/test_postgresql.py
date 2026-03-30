"""Tests for PostgreSQLInspector — uses real PostgreSQL via testcontainers."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from agent_migrate.inspector.postgresql import PostgreSQLInspector


@pytest.fixture
def inspector() -> PostgreSQLInspector:
    return PostgreSQLInspector()


# ── 1. Empty DB ───────────────────────────────────────────────────────────────

def test_empty_db_returns_empty_list(db_engine: Engine, inspector: PostgreSQLInspector) -> None:
    result = inspector.inspect(db_engine)
    assert result == []


# ── 2. Single table with columns ─────────────────────────────────────────────

def test_single_table_with_columns(db_engine: Engine, inspector: PostgreSQLInspector) -> None:
    with db_engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id    SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                bio   TEXT
            )
        """))
        conn.commit()

    tables = inspector.inspect(db_engine)
    assert len(tables) == 1

    users = tables[0]
    assert users.name == "users"
    assert users.schema_name == "public"
    assert len(users.columns) == 3
    assert {c.name for c in users.columns} == {"id", "email", "bio"}


# ── 3. Multiple tables + FK relations ────────────────────────────────────────

def test_multiple_tables_with_fk(db_engine: Engine, inspector: PostgreSQLInspector) -> None:
    with db_engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id    SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE orders (
                id      SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                total   NUMERIC(10, 2)
            )
        """))
        conn.commit()

    tables = inspector.inspect(db_engine)
    assert len(tables) == 2

    orders = next(t for t in tables if t.name == "orders")
    user_id_col = next(c for c in orders.columns if c.name == "user_id")
    assert user_id_col.foreign_table == "users"
    assert user_id_col.foreign_column == "id"

    # Non-FK columns have no FK reference
    id_col = next(c for c in orders.columns if c.name == "id")
    assert id_col.foreign_table is None


# ── 4. PK and UNIQUE constraint detection ────────────────────────────────────

def test_pk_and_unique_constraints(db_engine: Engine, inspector: PostgreSQLInspector) -> None:
    with db_engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE products (
                id   SERIAL PRIMARY KEY,
                sku  VARCHAR(50) NOT NULL UNIQUE,
                name TEXT NOT NULL
            )
        """))
        conn.commit()

    tables = inspector.inspect(db_engine)
    products = tables[0]

    id_col = next(c for c in products.columns if c.name == "id")
    sku_col = next(c for c in products.columns if c.name == "sku")
    name_col = next(c for c in products.columns if c.name == "name")

    assert id_col.is_primary_key is True
    assert id_col.is_unique is False  # PK ≠ explicit UNIQUE constraint

    assert sku_col.is_unique is True
    assert sku_col.is_primary_key is False

    assert name_col.is_primary_key is False
    assert name_col.is_unique is False


# ── 5. nullable / not null mapping ───────────────────────────────────────────

def test_nullable_not_null_mapping(db_engine: Engine, inspector: PostgreSQLInspector) -> None:
    with db_engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE items (
                id             SERIAL PRIMARY KEY,
                required_field TEXT NOT NULL,
                optional_field TEXT
            )
        """))
        conn.commit()

    tables = inspector.inspect(db_engine)
    items = tables[0]

    required = next(c for c in items.columns if c.name == "required_field")
    optional = next(c for c in items.columns if c.name == "optional_field")

    assert required.is_nullable is False
    assert optional.is_nullable is True


# ── 6. Approximate row count ─────────────────────────────────────────────────

def test_approximate_row_count(db_engine: Engine, inspector: PostgreSQLInspector) -> None:
    with db_engine.connect() as conn:
        conn.execute(text("CREATE TABLE items (id SERIAL PRIMARY KEY, name TEXT)"))
        conn.execute(text(
            "INSERT INTO items (name) "
            "SELECT 'item' || i FROM generate_series(1, 5) i"
        ))
        conn.execute(text("ANALYZE items"))
        conn.commit()

    tables = inspector.inspect(db_engine)
    items = tables[0]
    # reltuples after ANALYZE should be ≥ 0
    assert items.row_count >= 0


# ── 7. System tables not included ────────────────────────────────────────────

def test_system_tables_excluded(db_engine: Engine, inspector: PostgreSQLInspector) -> None:
    with db_engine.connect() as conn:
        conn.execute(text("CREATE TABLE my_table (id SERIAL PRIMARY KEY)"))
        conn.commit()

    tables = inspector.inspect(db_engine)
    names = {t.name for t in tables}

    assert "my_table" in names
    assert "pg_class" not in names
    assert "columns" not in names       # information_schema.columns
    assert "tables" not in names        # information_schema.tables


# ── 8. Reserved-word table name (`order`) ────────────────────────────────────

def test_reserved_word_table_name(db_engine: Engine, inspector: PostgreSQLInspector) -> None:
    """`order` is a PostgreSQL reserved word — must be quoted when creating/querying."""
    with db_engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE "order" (
                id    SERIAL PRIMARY KEY,
                total NUMERIC(10, 2) NOT NULL
            )
        """))
        conn.commit()

    tables = inspector.inspect(db_engine)
    order_table = next((t for t in tables if t.name == "order"), None)

    assert order_table is not None
    assert len(order_table.columns) == 2

    id_col = next(c for c in order_table.columns if c.name == "id")
    assert id_col.is_primary_key is True

    # get_column_values must handle the reserved-word name via double-quoting
    values = inspector.get_column_values(db_engine, "order", "total")
    assert isinstance(values, list)
