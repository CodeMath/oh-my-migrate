"""Tests for MigrationPlanner SQL generation and step ordering."""

from __future__ import annotations

from agent_migrate.migration.planner import MigrationPlanner
from agent_migrate.types import (
    ColumnSchema,
    DiffItem,
    DiffType,
    ModelSchema,
    RiskLevel,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _diff(
    diff_type: DiffType,
    table: str = "users",
    column: str | None = None,
    model_value: str | None = None,
    db_value: str | None = None,
    risk: RiskLevel = RiskLevel.SAFE,
    description: str = "",
) -> DiffItem:
    return DiffItem(
        diff_type=diff_type,
        table_name=table,
        column_name=column,
        model_value=model_value,
        db_value=db_value,
        risk=risk,
        description=description,
    )


def _plan(diffs: list[DiffItem], models: list[ModelSchema] | None = None):
    return MigrationPlanner().plan(diffs, models)


# ── Basic plan tests ──────────────────────────────────────────────────────────


def test_empty_diffs_returns_empty_plan():
    plan = _plan([])
    assert plan.steps == ()
    assert plan.overall_risk == RiskLevel.SAFE


def test_overall_risk_is_highest_of_all_steps():
    diffs = [
        _diff(DiffType.COLUMN_ADDED, column="x", risk=RiskLevel.SAFE),
        _diff(DiffType.COLUMN_REMOVED, column="y", risk=RiskLevel.DANGER),
    ]
    plan = _plan(diffs)
    assert plan.overall_risk == RiskLevel.DANGER


def test_overall_risk_caution_when_no_danger():
    diffs = [
        _diff(DiffType.COLUMN_ADDED, column="x"),
        _diff(DiffType.COLUMN_NULLABLE_CHANGED, column="y", model_value="False"),
    ]
    plan = _plan(diffs)
    assert plan.overall_risk == RiskLevel.CAUTION


# ── Step ordering ─────────────────────────────────────────────────────────────


def test_step_order_additive_before_destructive():
    diffs = [
        _diff(DiffType.TABLE_REMOVED, table="old"),
        _diff(DiffType.TABLE_ADDED, table="new"),
    ]
    plan = _plan(diffs)
    assert len(plan.steps) == 2
    assert "CREATE TABLE" in plan.steps[0].sql
    assert "DROP TABLE" in plan.steps[1].sql


def test_column_added_before_column_removed():
    diffs = [
        _diff(DiffType.COLUMN_REMOVED, column="old_col"),
        _diff(DiffType.COLUMN_ADDED, column="new_col"),
    ]
    plan = _plan(diffs)
    assert "ADD COLUMN" in plan.steps[0].sql
    assert "DROP COLUMN" in plan.steps[1].sql


# ── TABLE_ADDED ───────────────────────────────────────────────────────────────


def test_table_added_without_model_generates_placeholder():
    plan = _plan([_diff(DiffType.TABLE_ADDED, table="orders")])
    assert len(plan.steps) == 1
    sql = plan.steps[0].sql
    assert 'CREATE TABLE "orders"' in sql
    assert "TODO" in sql
    assert plan.steps[0].risk == RiskLevel.SAFE
    assert plan.steps[0].rollback_sql == 'DROP TABLE "orders";'


def test_table_added_with_model_generates_full_ddl():
    model = ModelSchema(
        name="Order",
        tablename="orders",
        columns=(
            ColumnSchema(name="id", python_type="Integer", primary_key=True),
            ColumnSchema(name="name", python_type="String", nullable=False),
        ),
    )
    plan = _plan([_diff(DiffType.TABLE_ADDED, table="orders")], models=[model])
    sql = plan.steps[0].sql
    assert 'CREATE TABLE "orders"' in sql
    assert '"id" SERIAL' in sql
    assert '"name" VARCHAR(255) NOT NULL' in sql
    assert "PRIMARY KEY" in sql


# ── TABLE_REMOVED ─────────────────────────────────────────────────────────────


def test_table_removed_generates_drop_table():
    plan = _plan([_diff(DiffType.TABLE_REMOVED, table="old_table")])
    step = plan.steps[0]
    assert step.sql == 'DROP TABLE "old_table";'
    assert step.risk == RiskLevel.DANGER
    assert step.rollback_sql is None


# ── COLUMN_ADDED ──────────────────────────────────────────────────────────────


def test_column_added_safe_when_nullable():
    plan = _plan([_diff(DiffType.COLUMN_ADDED, column="bio", model_value="String")])
    step = plan.steps[0]
    assert 'ADD COLUMN "bio"' in step.sql
    assert step.risk == RiskLevel.SAFE
    assert 'DROP COLUMN "bio"' in (step.rollback_sql or "")


def test_column_added_caution_when_not_null_and_no_default():
    model = ModelSchema(
        name="User",
        tablename="users",
        columns=(
            ColumnSchema(name="required_field", python_type="String", nullable=False),
        ),
    )
    plan = _plan(
        [_diff(DiffType.COLUMN_ADDED, column="required_field")],
        models=[model],
    )
    step = plan.steps[0]
    assert step.risk == RiskLevel.CAUTION
    assert "NOT NULL" in step.sql


# ── COLUMN_REMOVED ────────────────────────────────────────────────────────────


def test_column_removed_generates_drop_column():
    plan = _plan([_diff(DiffType.COLUMN_REMOVED, column="bio")])
    step = plan.steps[0]
    assert step.sql == 'ALTER TABLE "users" DROP COLUMN "bio";'
    assert step.risk == RiskLevel.DANGER
    assert step.rollback_sql is None


# ── COLUMN_TYPE_CHANGED ───────────────────────────────────────────────────────


def test_column_type_changed_generates_alter_type():
    plan = _plan([
        _diff(
            DiffType.COLUMN_TYPE_CHANGED,
            column="age",
            model_value="BigInteger",
            db_value="integer",
        )
    ])
    step = plan.steps[0]
    assert 'ALTER COLUMN "age" TYPE BIGINT' in step.sql
    assert step.risk == RiskLevel.CAUTION
    assert 'TYPE integer' in (step.rollback_sql or "")


# ── COLUMN_NULLABLE_CHANGED ───────────────────────────────────────────────────


def test_nullable_changed_to_nullable_drops_not_null():
    plan = _plan([
        _diff(DiffType.COLUMN_NULLABLE_CHANGED, column="email", model_value="True")
    ])
    step = plan.steps[0]
    assert "DROP NOT NULL" in step.sql
    assert "SET NOT NULL" in (step.rollback_sql or "")


def test_nullable_changed_to_not_null_sets_not_null():
    plan = _plan([
        _diff(DiffType.COLUMN_NULLABLE_CHANGED, column="email", model_value="False")
    ])
    step = plan.steps[0]
    assert "SET NOT NULL" in step.sql
    assert "DROP NOT NULL" in (step.rollback_sql or "")


# ── FK_ADDED ──────────────────────────────────────────────────────────────────


def test_fk_added_generates_add_constraint():
    plan = _plan([
        _diff(DiffType.FK_ADDED, column="user_id", model_value="users.id")
    ])
    step = plan.steps[0]
    assert "ADD CONSTRAINT" in step.sql
    assert 'FOREIGN KEY ("user_id")' in step.sql
    assert 'REFERENCES "users" ("id")' in step.sql
    assert step.risk == RiskLevel.SAFE
    assert "DROP CONSTRAINT" in (step.rollback_sql or "")


# ── FK_REMOVED ────────────────────────────────────────────────────────────────


def test_fk_removed_generates_drop_constraint():
    plan = _plan([_diff(DiffType.FK_REMOVED, column="user_id")])
    step = plan.steps[0]
    assert "DROP CONSTRAINT" in step.sql
    assert '"fk_users_user_id"' in step.sql
    assert step.risk == RiskLevel.CAUTION


# ── ENUM_VALUES_CHANGED ───────────────────────────────────────────────────────


def test_enum_values_changed_generates_add_value():
    plan = _plan([
        _diff(
            DiffType.ENUM_VALUES_CHANGED,
            column="status",
            model_value="active,inactive,pending",
            db_value="active,inactive",
        )
    ])
    step = plan.steps[0]
    assert "ADD VALUE" in step.sql
    assert "'pending'" in step.sql
    assert step.rollback_sql is None


def test_enum_values_changed_no_new_values_returns_no_step():
    # When model has no new values vs DB, planner returns no step
    plan = _plan([
        _diff(
            DiffType.ENUM_VALUES_CHANGED,
            column="status",
            model_value="active",
            db_value="active,inactive",
        )
    ])
    assert plan.steps == ()


# ── Identifier quoting ────────────────────────────────────────────────────────


def test_identifiers_are_double_quoted():
    plan = _plan([_diff(DiffType.TABLE_REMOVED, table="my table")])
    assert '"my table"' in plan.steps[0].sql


def test_identifier_with_internal_quotes_is_escaped():
    plan = _plan([_diff(DiffType.TABLE_REMOVED, table='say "hi"')])
    assert '"say ""hi"""' in plan.steps[0].sql
