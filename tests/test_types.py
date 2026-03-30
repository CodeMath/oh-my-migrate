"""Tests for core types in agent_migrate.types."""

from __future__ import annotations

import pytest

from agent_migrate.types import (
    ColumnSchema,
    DBColumnSchema,
    DBTableSchema,
    DiffItem,
    DiffType,
    IndexSchema,
    MigrationPlan,
    MigrationStep,
    ModelSchema,
    RiskAssessment,
    RiskLevel,
)


def test_column_schema_creation() -> None:
    col = ColumnSchema(name="id", python_type="Integer", nullable=False, primary_key=True)
    assert col.name == "id"
    assert col.python_type == "Integer"
    assert col.nullable is False
    assert col.primary_key is True
    assert col.foreign_key is None


def test_column_schema_frozen() -> None:
    col = ColumnSchema(name="id", python_type="Integer")
    with pytest.raises(Exception):
        col.name = "other"  # type: ignore[misc]


def test_index_schema_tuple_columns() -> None:
    idx = IndexSchema(name="ix_users_email", columns=("email",), unique=True)
    assert isinstance(idx.columns, tuple)
    assert idx.columns == ("email",)


def test_model_schema_creation() -> None:
    col = ColumnSchema(name="id", python_type="Integer", nullable=False, primary_key=True)
    model = ModelSchema(name="User", tablename="users", columns=(col,))
    assert model.name == "User"
    assert model.tablename == "users"
    assert isinstance(model.columns, tuple)
    assert len(model.columns) == 1
    assert model.indexes == ()


def test_model_schema_frozen() -> None:
    model = ModelSchema(name="User", tablename="users", columns=())
    with pytest.raises(Exception):
        model.name = "Other"  # type: ignore[misc]


def test_db_column_schema_creation() -> None:
    col = DBColumnSchema(
        name="id",
        data_type="integer",
        is_nullable=False,
        is_primary_key=True,
    )
    assert col.name == "id"
    assert col.data_type == "integer"
    assert col.is_nullable is False
    assert col.is_primary_key is True


def test_db_table_schema_tuple_columns() -> None:
    col = DBColumnSchema(name="id", data_type="integer", is_nullable=False)
    table = DBTableSchema(name="users", schema_name="public", columns=(col,))
    assert isinstance(table.columns, tuple)
    assert table.row_count == 0


def test_diff_type_enum_values() -> None:
    assert DiffType.TABLE_ADDED.value == "table_added"
    assert DiffType.ENUM_VALUES_CHANGED.value == "enum_values_changed"
    assert DiffType.INDEX_ADDED.value == "index_added"
    assert DiffType.INDEX_REMOVED.value == "index_removed"


def test_risk_level_enum_values() -> None:
    assert RiskLevel.SAFE.value == "safe"
    assert RiskLevel.CAUTION.value == "caution"
    assert RiskLevel.DANGER.value == "danger"


def test_diff_item_creation() -> None:
    item = DiffItem(
        diff_type=DiffType.COLUMN_ADDED,
        table_name="users",
        column_name="email",
        risk=RiskLevel.SAFE,
    )
    assert item.diff_type == DiffType.COLUMN_ADDED
    assert item.table_name == "users"
    assert item.risk == RiskLevel.SAFE


def test_risk_assessment_creation() -> None:
    ra = RiskAssessment(
        risk=RiskLevel.DANGER,
        reason="Column removal drops data",
        affected_rows=100,
        recommendation="Backup first",
    )
    assert ra.risk == RiskLevel.DANGER
    assert ra.affected_rows == 100


def test_migration_plan_tuple_steps() -> None:
    step = MigrationStep(
        sql="ALTER TABLE users ADD COLUMN email VARCHAR(255)",
        risk=RiskLevel.SAFE,
        description="Add email column",
    )
    plan = MigrationPlan(steps=(step,), overall_risk=RiskLevel.SAFE)
    assert isinstance(plan.steps, tuple)
    assert len(plan.steps) == 1
    assert plan.overall_risk == RiskLevel.SAFE


def test_diff_item_equality() -> None:
    a = DiffItem(diff_type=DiffType.TABLE_ADDED, table_name="orders")
    b = DiffItem(diff_type=DiffType.TABLE_ADDED, table_name="orders")
    assert a == b


def test_all_diff_types_present() -> None:
    expected = {
        "TABLE_ADDED", "TABLE_REMOVED", "COLUMN_ADDED", "COLUMN_REMOVED",
        "COLUMN_TYPE_CHANGED", "COLUMN_NULLABLE_CHANGED", "COLUMN_DEFAULT_CHANGED",
        "ENUM_VALUES_CHANGED", "FK_ADDED", "FK_REMOVED", "INDEX_ADDED", "INDEX_REMOVED",
        "RLS_ENABLED_CHANGED", "RLS_POLICY_ADDED", "RLS_POLICY_REMOVED",
        "RLS_POLICY_CHANGED", "RLS_POLICY_UNTRACKED",
        "ROLE_MISSING", "GRANT_ADDED", "GRANT_REMOVED",
    }
    actual = {e.name for e in DiffType}
    assert expected == actual
