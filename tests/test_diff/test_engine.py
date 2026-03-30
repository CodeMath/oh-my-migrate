"""Tests for DiffEngine."""

from __future__ import annotations

from agent_migrate.diff import compute_diff
from agent_migrate.diff.engine import DiffEngine
from agent_migrate.types import (
    ColumnSchema,
    DBColumnSchema,
    DBTableSchema,
    DiffType,
    IndexSchema,
    ModelSchema,
    RiskLevel,
)


def _make_model(
    name: str,
    tablename: str,
    columns: list[ColumnSchema],
    indexes: list[IndexSchema] | None = None,
) -> ModelSchema:
    return ModelSchema(
        name=name,
        tablename=tablename,
        columns=tuple(columns),
        indexes=tuple(indexes or []),
    )


def _make_table(
    name: str,
    columns: list[DBColumnSchema],
) -> DBTableSchema:
    return DBTableSchema(name=name, schema_name="public", columns=tuple(columns))


def _make_int_col(name: str, nullable: bool = False, pk: bool = False) -> ColumnSchema:
    return ColumnSchema(name=name, python_type="Integer", nullable=nullable, primary_key=pk)


def _make_db_int_col(name: str, nullable: bool = False) -> DBColumnSchema:
    return DBColumnSchema(name=name, data_type="integer", is_nullable=nullable)


# ── TABLE_ADDED ──


def test_table_added() -> None:
    model = _make_model("User", "users", [_make_int_col("id", pk=True)])
    diffs = compute_diff([model], [])
    assert len(diffs) == 1
    assert diffs[0].diff_type == DiffType.TABLE_ADDED
    assert diffs[0].table_name == "users"


# ── TABLE_REMOVED ──


def test_table_removed() -> None:
    table = _make_table("orphan_table", [_make_db_int_col("id")])
    diffs = compute_diff([], [table])
    assert len(diffs) == 1
    assert diffs[0].diff_type == DiffType.TABLE_REMOVED
    assert diffs[0].table_name == "orphan_table"
    assert diffs[0].risk == RiskLevel.DANGER


# ── COLUMN_ADDED ──


def test_column_added() -> None:
    model = _make_model(
        "User",
        "users",
        [_make_int_col("id", pk=True), _make_int_col("age", nullable=True)],
    )
    table = _make_table("users", [_make_db_int_col("id")])
    diffs = compute_diff([model], [table])
    col_diffs = [d for d in diffs if d.diff_type == DiffType.COLUMN_ADDED]
    assert len(col_diffs) == 1
    assert col_diffs[0].column_name == "age"


# ── COLUMN_REMOVED ──


def test_column_removed() -> None:
    model = _make_model("User", "users", [_make_int_col("id", pk=True)])
    table = _make_table(
        "users", [_make_db_int_col("id"), _make_db_int_col("old_col")]
    )
    diffs = compute_diff([model], [table])
    col_diffs = [d for d in diffs if d.diff_type == DiffType.COLUMN_REMOVED]
    assert len(col_diffs) == 1
    assert col_diffs[0].column_name == "old_col"


# ── COLUMN_TYPE_CHANGED ──


def test_column_type_changed() -> None:
    model = _make_model(
        "User",
        "users",
        [ColumnSchema(name="id", python_type="Integer", nullable=False, primary_key=True)],
    )
    # DB has text where model expects integer
    table = _make_table(
        "users",
        [DBColumnSchema(name="id", data_type="text", is_nullable=False)],
    )
    diffs = compute_diff([model], [table])
    type_diffs = [d for d in diffs if d.diff_type == DiffType.COLUMN_TYPE_CHANGED]
    assert len(type_diffs) == 1
    assert type_diffs[0].column_name == "id"
    assert type_diffs[0].model_value == "Integer"
    assert type_diffs[0].db_value == "text"


# ── Compatible types → no diff ──


def test_compatible_types_no_diff() -> None:
    """varchar in DB is compatible with String in model — no TYPE_CHANGED."""
    model = _make_model(
        "User",
        "users",
        [ColumnSchema(name="email", python_type="String", nullable=True)],
    )
    table = _make_table(
        "users",
        [DBColumnSchema(name="email", data_type="character varying", is_nullable=True)],
    )
    diffs = compute_diff([model], [table])
    type_diffs = [d for d in diffs if d.diff_type == DiffType.COLUMN_TYPE_CHANGED]
    assert len(type_diffs) == 0


def test_bigint_compatible_with_biginteger() -> None:
    model = _make_model(
        "Log",
        "logs",
        [ColumnSchema(name="id", python_type="BigInteger", nullable=False, primary_key=True)],
    )
    table = _make_table(
        "logs",
        [DBColumnSchema(name="id", data_type="bigint", is_nullable=False)],
    )
    diffs = compute_diff([model], [table])
    type_diffs = [d for d in diffs if d.diff_type == DiffType.COLUMN_TYPE_CHANGED]
    assert len(type_diffs) == 0


# ── NULLABLE_CHANGED ──


def test_nullable_changed() -> None:
    model = _make_model(
        "User",
        "users",
        [ColumnSchema(name="bio", python_type="Text", nullable=False)],
    )
    table = _make_table(
        "users",
        [DBColumnSchema(name="bio", data_type="text", is_nullable=True)],
    )
    diffs = compute_diff([model], [table])
    null_diffs = [d for d in diffs if d.diff_type == DiffType.COLUMN_NULLABLE_CHANGED]
    assert len(null_diffs) == 1
    assert null_diffs[0].column_name == "bio"


# ── FK_ADDED / FK_REMOVED ──


def test_fk_added() -> None:
    model = _make_model(
        "Order",
        "orders",
        [ColumnSchema(name="user_id", python_type="Integer", nullable=False, foreign_key="users.id")],
    )
    table = _make_table(
        "orders",
        [DBColumnSchema(name="user_id", data_type="integer", is_nullable=False)],
    )
    diffs = compute_diff([model], [table])
    fk_diffs = [d for d in diffs if d.diff_type == DiffType.FK_ADDED]
    assert len(fk_diffs) == 1
    assert fk_diffs[0].column_name == "user_id"


def test_fk_removed() -> None:
    model = _make_model(
        "Order",
        "orders",
        [ColumnSchema(name="user_id", python_type="Integer", nullable=False)],
    )
    table = _make_table(
        "orders",
        [DBColumnSchema(
            name="user_id",
            data_type="integer",
            is_nullable=False,
            foreign_table="users",
            foreign_column="id",
        )],
    )
    diffs = compute_diff([model], [table])
    fk_diffs = [d for d in diffs if d.diff_type == DiffType.FK_REMOVED]
    assert len(fk_diffs) == 1
    assert fk_diffs[0].column_name == "user_id"


# ── Identical schema → empty diff ──


def test_identical_schema_empty_diff() -> None:
    model = _make_model(
        "User",
        "users",
        [
            ColumnSchema(name="id", python_type="Integer", nullable=False, primary_key=True),
            ColumnSchema(name="email", python_type="String", nullable=False),
        ],
    )
    table = _make_table(
        "users",
        [
            DBColumnSchema(name="id", data_type="integer", is_nullable=False),
            DBColumnSchema(name="email", data_type="character varying", is_nullable=False),
        ],
    )
    diffs = compute_diff([model], [table])
    assert diffs == []


def test_compute_diff_function_alias() -> None:
    """compute_diff() is a module-level alias for DiffEngine().compute_diff()."""
    engine = DiffEngine()
    model = _make_model("X", "xs", [_make_int_col("id", pk=True)])
    result_fn = compute_diff([model], [])
    result_engine = engine.compute_diff([model], [])
    assert result_fn == result_engine
