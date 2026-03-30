"""Tests for format_snapshot, format_diff, format_plan."""

from __future__ import annotations

from agent_migrate.formatter import format_diff, format_plan, format_snapshot
from agent_migrate.formatter.ref import RefEngine, RefMap
from agent_migrate.types import (
    ColumnSchema,
    DBColumnSchema,
    DBTableSchema,
    DiffItem,
    DiffType,
    MigrationPlan,
    MigrationStep,
    ModelSchema,
    RiskLevel,
)

# ── Helpers / fixtures ────────────────────────────────────────────────────────

def _model(name: str, tablename: str, cols: tuple[ColumnSchema, ...]) -> ModelSchema:
    return ModelSchema(name, tablename, columns=cols)


def _table(name: str, cols: tuple[DBColumnSchema, ...], rows: int = 0) -> DBTableSchema:
    return DBTableSchema(name, "public", columns=cols, row_count=rows)


# ── 1. Snapshot format: token count < 500 (10 models + 10 tables) ────────────

def test_snapshot_token_count_under_500() -> None:
    """Output for 10 models + 10 tables must fit within ~500 tokens."""
    cols_model = (
        ColumnSchema("id", "Integer", nullable=False, primary_key=True),
        ColumnSchema("name", "String", nullable=False),
        ColumnSchema("desc", "Text", nullable=True),
        ColumnSchema("count", "Integer", nullable=False),
        ColumnSchema("created_at", "DateTime", nullable=False),
    )
    cols_db = (
        DBColumnSchema("id", "integer", False, is_primary_key=True),
        DBColumnSchema("name", "character varying", False),
        DBColumnSchema("desc", "text", True),
        DBColumnSchema("count", "integer", False),
        DBColumnSchema("created_at", "timestamp without time zone", False),
    )
    models = [_model(f"Model{i}", f"table{i}", cols_model) for i in range(1, 11)]
    tables = [_table(f"table{i}", cols_db) for i in range(1, 11)]

    ref_map = RefEngine().assign(models, tables)
    output = format_snapshot(models, tables, [], ref_map, "PostgreSQL localhost/test")

    # ~4 chars per token → 500 tokens ≈ 2000 chars
    assert len(output) < 2000, f"Snapshot too long: {len(output)} chars"


# ── 2. Diff [+] for COLUMN_ADDED ─────────────────────────────────────────────

def test_diff_plus_symbol_for_column_added() -> None:
    models = [_model("User", "users", (ColumnSchema("id", "Integer"),))]
    tables = [_table("users", (DBColumnSchema("id", "integer", False),))]
    diffs = [DiffItem(DiffType.COLUMN_ADDED, "users", "phone", RiskLevel.SAFE)]
    ref_map = RefEngine().assign(models, tables)
    output = format_diff(diffs, ref_map)
    assert "[+]" in output
    assert "@m1" in output


# ── 3. Diff [~] for TYPE_CHANGED ─────────────────────────────────────────────

def test_diff_tilde_symbol_for_type_changed() -> None:
    models = [_model("User", "users", (ColumnSchema("id", "Integer"),))]
    tables = [_table("users", (DBColumnSchema("id", "integer", False),))]
    diffs = [DiffItem(DiffType.COLUMN_TYPE_CHANGED, "users", "status", RiskLevel.DANGER)]
    ref_map = RefEngine().assign(models, tables)
    output = format_diff(diffs, ref_map)
    assert "[~]" in output


# ── 4. Diff [-] for COLUMN_REMOVED ───────────────────────────────────────────

def test_diff_minus_symbol_for_column_removed() -> None:
    models = [_model("User", "users", (ColumnSchema("id", "Integer"),))]
    tables = [_table("users", (DBColumnSchema("id", "integer", False),))]
    diffs = [DiffItem(DiffType.COLUMN_REMOVED, "users", "old_col", RiskLevel.DANGER)]
    ref_map = RefEngine().assign(models, tables)
    output = format_diff(diffs, ref_map)
    assert "[-]" in output
    assert "@d1" in output


# ── 5. nullable columns marked with ? ────────────────────────────────────────

def test_snapshot_nullable_col_has_question_mark() -> None:
    models = [_model("User", "users", (
        ColumnSchema("id", "Integer", nullable=False, primary_key=True),
        ColumnSchema("name", "String", nullable=True),
    ))]
    tables: list[DBTableSchema] = []
    ref_map = RefEngine().assign(models, tables)
    output = format_snapshot(models, tables, [], ref_map, "pg")
    assert "name:str?" in output


# ── 6. FK shown as →@m1 ──────────────────────────────────────────────────────

def test_snapshot_fk_arrow_display() -> None:
    user_model = _model("User", "users", (
        ColumnSchema("id", "Integer", nullable=False, primary_key=True),
    ))
    order_model = _model("Order", "orders", (
        ColumnSchema("id", "Integer", nullable=False, primary_key=True),
        ColumnSchema("user_id", "Integer", nullable=False, foreign_key="users.id"),
    ))
    ref_map = RefEngine().assign([user_model, order_model], [])
    output = format_snapshot([user_model, order_model], [], [], ref_map, "pg")
    assert "\u2192@m1" in output  # →@m1


# ── 7. Plan risk level shown in brackets ─────────────────────────────────────

def test_plan_format_risk_brackets() -> None:
    plan = MigrationPlan(
        steps=(
            MigrationStep(
                sql="ALTER TABLE products ADD COLUMN description TEXT",
                risk=RiskLevel.SAFE,
                description="Add nullable column",
            ),
            MigrationStep(
                sql="ALTER TABLE orders DROP COLUMN old_col",
                risk=RiskLevel.DANGER,
                description="Drop column — data loss risk",
            ),
        ),
        overall_risk=RiskLevel.DANGER,
    )
    output = format_plan(plan, RefMap())
    assert "[SAFE]" in output
    assert "[DANGER]" in output
    assert "Overall: DANGER risk" in output


# ── 8. Column truncation for wide tables (>8 cols → +N more) ─────────────────

def test_snapshot_column_truncation() -> None:
    many_cols = tuple(
        ColumnSchema(f"col{i}", "String", nullable=True) for i in range(10)
    )
    models = [_model("Wide", "wide", many_cols)]
    ref_map = RefEngine().assign(models, [])
    output = format_snapshot(models, [], [], ref_map, "pg")
    assert "+4 more" in output  # 10 cols − 6 shown = +4 more


# ── 9. Empty diff list returns no-difference marker ──────────────────────────

def test_diff_empty_list_returns_marker() -> None:
    output = format_diff([], RefMap())
    assert "no differences" in output.lower()


# ── 10. Diff affected_rows shown in output ────────────────────────────────────

def test_diff_affected_rows_shown() -> None:
    models = [_model("Order", "orders", (ColumnSchema("id", "Integer"),))]
    tables = [_table("orders", (DBColumnSchema("id", "integer", False),))]
    diffs = [DiffItem(
        DiffType.COLUMN_TYPE_CHANGED, "orders", "status",
        RiskLevel.DANGER, affected_rows=23
    )]
    ref_map = RefEngine().assign(models, tables)
    output = format_diff(diffs, ref_map)
    assert "23 rows affected" in output
