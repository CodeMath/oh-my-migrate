"""Tests for MigrationExecutor dry-run and live execution (testcontainers)."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from agent_migrate.exceptions import DangerousMigrationError
from agent_migrate.migration.executor import MigrationExecutor
from agent_migrate.types import MigrationPlan, MigrationStep, RiskLevel

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _safe_plan(*sql_stmts: str) -> MigrationPlan:
    steps = tuple(
        MigrationStep(sql=sql, risk=RiskLevel.SAFE, description="test step")
        for sql in sql_stmts
    )
    return MigrationPlan(steps=steps, overall_risk=RiskLevel.SAFE)


def _danger_plan(sql: str) -> MigrationPlan:
    step = MigrationStep(sql=sql, risk=RiskLevel.DANGER, description="danger step")
    return MigrationPlan(steps=(step,), overall_risk=RiskLevel.DANGER)


# ── dry_run ───────────────────────────────────────────────────────────────────


def test_dry_run_returns_sql_list():
    plan = _safe_plan(
        'CREATE TABLE "t1" ("id" SERIAL PRIMARY KEY);',
        'ALTER TABLE "t1" ADD COLUMN "name" VARCHAR(255);',
    )
    result = MigrationExecutor().dry_run(plan)
    assert result == [
        'CREATE TABLE "t1" ("id" SERIAL PRIMARY KEY);',
        'ALTER TABLE "t1" ADD COLUMN "name" VARCHAR(255);',
    ]


def test_dry_run_empty_plan():
    plan = MigrationPlan(steps=(), overall_risk=RiskLevel.SAFE)
    assert MigrationExecutor().dry_run(plan) == []


# ── execute ───────────────────────────────────────────────────────────────────


def test_execute_danger_without_force_raises():
    plan = _danger_plan('DROP TABLE "important";')
    with pytest.raises(DangerousMigrationError, match="DANGER"):
        # Pass a dummy engine — the check happens before any DB call
        MigrationExecutor().execute(None, plan, force=False)  # type: ignore[arg-type]


def test_execute_safe_plan_creates_table(db_engine):
    plan = _safe_plan(
        'CREATE TABLE "exec_test" ("id" SERIAL PRIMARY KEY, "val" TEXT);'
    )
    MigrationExecutor().execute(db_engine, plan)

    inspector = inspect(db_engine)
    assert "exec_test" in inspector.get_table_names()


def test_execute_danger_with_force_drops_table(db_engine):
    # First create a table, then drop it with force=True
    with db_engine.begin() as conn:
        conn.execute(text('CREATE TABLE "force_test" ("id" SERIAL PRIMARY KEY);'))

    plan = _danger_plan('DROP TABLE "force_test";')
    MigrationExecutor().execute(db_engine, plan, force=True)

    inspector = inspect(db_engine)
    assert "force_test" not in inspector.get_table_names()


def test_execute_rolls_back_on_error(db_engine):
    """A bad SQL statement inside the plan leaves no partial changes."""
    plan = _safe_plan(
        'CREATE TABLE "partial_test" ("id" SERIAL PRIMARY KEY);',
        "THIS IS NOT VALID SQL;",
    )
    with pytest.raises(DBAPIError):
        MigrationExecutor().execute(db_engine, plan)

    inspector = inspect(db_engine)
    # Table should NOT exist because the transaction was rolled back
    assert "partial_test" not in inspector.get_table_names()
