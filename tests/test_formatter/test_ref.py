"""Tests for RefEngine and RefMap."""

from __future__ import annotations

import pytest

from agent_migrate.formatter.ref import RefEngine
from agent_migrate.types import ColumnSchema, DBColumnSchema, DBTableSchema, ModelSchema


@pytest.fixture
def two_models() -> list[ModelSchema]:
    return [
        ModelSchema("User", "users", columns=(ColumnSchema("id", "Integer"),)),
        ModelSchema("Product", "products", columns=(ColumnSchema("id", "Integer"),)),
    ]


@pytest.fixture
def two_tables() -> list[DBTableSchema]:
    return [
        DBTableSchema("users", "public", columns=(DBColumnSchema("id", "integer", False),)),
        DBTableSchema("products", "public", columns=(DBColumnSchema("id", "integer", False),)),
    ]


# ── 1. Model ref assignment order ────────────────────────────────────────────

def test_model_ref_assignment_order(
    two_models: list[ModelSchema], two_tables: list[DBTableSchema]
) -> None:
    ref_map = RefEngine().assign(two_models, two_tables)
    assert ref_map.get_ref(two_models[0]) == "@m1"
    assert ref_map.get_ref(two_models[1]) == "@m2"


# ── 2. Table ref assignment order ────────────────────────────────────────────

def test_table_ref_assignment_order(
    two_models: list[ModelSchema], two_tables: list[DBTableSchema]
) -> None:
    ref_map = RefEngine().assign(two_models, two_tables)
    assert ref_map.get_ref(two_tables[0]) == "@d1"
    assert ref_map.get_ref(two_tables[1]) == "@d2"


# ── 3. resolve() — forward lookup ────────────────────────────────────────────

def test_resolve_model_ref(
    two_models: list[ModelSchema], two_tables: list[DBTableSchema]
) -> None:
    ref_map = RefEngine().assign(two_models, two_tables)
    assert ref_map.resolve("@m1") is two_models[0]
    assert ref_map.resolve("@m2") is two_models[1]


# ── 4. resolve() — table forward lookup ──────────────────────────────────────

def test_resolve_table_ref(
    two_models: list[ModelSchema], two_tables: list[DBTableSchema]
) -> None:
    ref_map = RefEngine().assign(two_models, two_tables)
    assert ref_map.resolve("@d1") is two_tables[0]
    assert ref_map.resolve("@d2") is two_tables[1]


# ── 5. Unknown ref returns None ───────────────────────────────────────────────

def test_unknown_ref_returns_none(
    two_models: list[ModelSchema], two_tables: list[DBTableSchema]
) -> None:
    ref_map = RefEngine().assign(two_models, two_tables)
    assert ref_map.resolve("@m99") is None
    assert ref_map.get_ref(object()) is None


# ── 6. find_model_ref by tablename ────────────────────────────────────────────

def test_find_model_ref_by_tablename(
    two_models: list[ModelSchema], two_tables: list[DBTableSchema]
) -> None:
    ref_map = RefEngine().assign(two_models, two_tables)
    assert ref_map.find_model_ref("users") == "@m1"
    assert ref_map.find_model_ref("products") == "@m2"
    assert ref_map.find_model_ref("nonexistent") is None


# ── 7. find_table_ref by name ─────────────────────────────────────────────────

def test_find_table_ref_by_name(
    two_models: list[ModelSchema], two_tables: list[DBTableSchema]
) -> None:
    ref_map = RefEngine().assign(two_models, two_tables)
    assert ref_map.find_table_ref("users") == "@d1"
    assert ref_map.find_table_ref("products") == "@d2"
    assert ref_map.find_table_ref("nonexistent") is None
