"""Tests for RiskAnalyzer.

Uses testcontainers PostgreSQL for DB-dependent risk checks (NULL counts, row counts).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from agent_migrate.diff.risk import RiskAnalyzer
from agent_migrate.types import (
    DiffItem,
    DiffType,
    RiskLevel,
)


def _col_added(
    table: str,
    col: str,
    *,
    nullable: bool = True,
    has_default: bool = False,
) -> DiffItem:
    is_not_null_no_default = not nullable and not has_default
    description = (
        f"Column {col!r} exists in model but not in DB [not_null_no_default]"
        if is_not_null_no_default
        else f"Column {col!r} exists in model but not in DB"
    )
    return DiffItem(
        diff_type=DiffType.COLUMN_ADDED,
        table_name=table,
        column_name=col,
        description=description,
        model_value="Integer",
    )


# ── No-DB risk tests ──


def test_nullable_column_add_is_safe() -> None:
    diff = _col_added("users", "age", nullable=True)
    analyzer = RiskAnalyzer(engine=None)
    result = analyzer.analyze([diff])
    assert result[0].risk == RiskLevel.SAFE


def test_not_null_no_default_column_add_is_caution() -> None:
    diff = _col_added("users", "score", nullable=False, has_default=False)
    analyzer = RiskAnalyzer(engine=None)
    result = analyzer.analyze([diff])
    assert result[0].risk == RiskLevel.CAUTION


def test_column_remove_is_danger() -> None:
    diff = DiffItem(
        diff_type=DiffType.COLUMN_REMOVED,
        table_name="users",
        column_name="email",
        description="Column removed",
    )
    analyzer = RiskAnalyzer(engine=None)
    result = analyzer.analyze([diff])
    assert result[0].risk == RiskLevel.DANGER


def test_table_remove_is_danger() -> None:
    diff = DiffItem(
        diff_type=DiffType.TABLE_REMOVED,
        table_name="old_table",
        description="Table removed",
    )
    analyzer = RiskAnalyzer(engine=None)
    result = analyzer.analyze([diff])
    assert result[0].risk == RiskLevel.DANGER


# ── DB-dependent risk tests ──


def test_nullable_to_not_null_with_nulls_is_danger(db_engine: Engine) -> None:
    """nullable→not-null with existing NULLs → DANGER."""
    with db_engine.connect() as conn:
        conn.execute(text("CREATE TABLE users (id SERIAL PRIMARY KEY, bio TEXT)"))
        conn.execute(text("INSERT INTO users (bio) VALUES (NULL)"))
        conn.commit()

    diff = DiffItem(
        diff_type=DiffType.COLUMN_NULLABLE_CHANGED,
        table_name="users",
        column_name="bio",
        description="nullable mismatch",
        model_value="False",  # model wants NOT NULL
        db_value="True",      # DB currently nullable
    )
    analyzer = RiskAnalyzer(engine=db_engine)
    result = analyzer.analyze([diff])
    assert result[0].risk == RiskLevel.DANGER
    assert result[0].affected_rows is not None and result[0].affected_rows > 0


def test_empty_table_column_remove_danger_zero_rows(db_engine: Engine) -> None:
    """Column removal on empty table → DANGER with affected_rows=0."""
    with db_engine.connect() as conn:
        conn.execute(text("CREATE TABLE products (id SERIAL PRIMARY KEY, sku TEXT)"))
        conn.commit()

    diff = DiffItem(
        diff_type=DiffType.COLUMN_REMOVED,
        table_name="products",
        column_name="sku",
        description="Column removed",
    )
    analyzer = RiskAnalyzer(engine=db_engine)
    result = analyzer.analyze([diff])
    assert result[0].risk == RiskLevel.DANGER
    assert result[0].affected_rows == 0


def test_reserved_word_table_order_query_works(db_engine: Engine) -> None:
    """Table named 'order' (reserved word) must be quoted correctly."""
    with db_engine.connect() as conn:
        conn.execute(
            text('CREATE TABLE "order" (id SERIAL PRIMARY KEY, status TEXT)')
        )
        conn.execute(text('INSERT INTO "order" (status) VALUES (\'pending\')'))
        conn.commit()

    diff = DiffItem(
        diff_type=DiffType.COLUMN_REMOVED,
        table_name="order",
        column_name="status",
        description="Column removed",
    )
    analyzer = RiskAnalyzer(engine=db_engine)
    result = analyzer.analyze([diff])
    # Should not raise; quoted_name handles the reserved word
    assert result[0].risk == RiskLevel.DANGER
    assert result[0].affected_rows == 1
