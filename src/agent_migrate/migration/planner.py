"""Migration planner: converts DiffItems into ordered MigrationSteps with SQL."""

from __future__ import annotations

from agent_migrate.types import (
    DiffItem,
    DiffType,
    MigrationPlan,
    MigrationStep,
    ModelSchema,
    RiskLevel,
    RLSPolicySchema,
)

# Safe execution order: additive/non-destructive first, destructive last
_STEP_ORDER: dict[DiffType, int] = {
    DiffType.TABLE_ADDED: 0,
    DiffType.COLUMN_ADDED: 1,
    DiffType.COLUMN_TYPE_CHANGED: 2,
    DiffType.COLUMN_NULLABLE_CHANGED: 3,
    DiffType.COLUMN_DEFAULT_CHANGED: 4,
    DiffType.ENUM_VALUES_CHANGED: 5,
    DiffType.FK_ADDED: 6,
    DiffType.INDEX_ADDED: 7,
    DiffType.FK_REMOVED: 8,
    DiffType.INDEX_REMOVED: 9,
    DiffType.COLUMN_REMOVED: 10,
    DiffType.TABLE_REMOVED: 11,
    DiffType.RLS_ENABLED_CHANGED: 12,
    DiffType.RLS_POLICY_ADDED: 13,
    DiffType.RLS_POLICY_CHANGED: 14,
    DiffType.RLS_POLICY_REMOVED: 15,
    DiffType.RLS_POLICY_UNTRACKED: -1,  # informational only, no migration step
    DiffType.ROLE_MISSING: 16,
    DiffType.GRANT_ADDED: 17,
    DiffType.GRANT_REMOVED: 18,
}

# SQLAlchemy python_type → SQL type name for DDL generation
_PYTHON_TO_SQL: dict[str, str] = {
    "Integer": "INTEGER",
    "BigInteger": "BIGINT",
    "SmallInteger": "SMALLINT",
    "String": "VARCHAR(255)",
    "Text": "TEXT",
    "Boolean": "BOOLEAN",
    "Float": "FLOAT",
    "Numeric": "NUMERIC",
    "DateTime": "TIMESTAMP",
    "Date": "DATE",
    "LargeBinary": "BYTEA",
    "UUID": "UUID",
    "JSON": "JSONB",
    "Enum": "VARCHAR(255)",
}

# SQLAlchemy class name (as stored in sql_type) → canonical DDL type base
# Used to normalize names like "DateTime" → "TIMESTAMP" in generated SQL.
_SQLA_CLASS_TO_DDL: dict[str, str] = {
    **_PYTHON_TO_SQL,
    "Decimal": "NUMERIC",
    "JSONB": "JSONB",
    "VARCHAR": "VARCHAR",
    "CHAR": "CHAR",
    "TIMESTAMP": "TIMESTAMP",
    "SERIAL": "SERIAL",
    "Time": "TIME",
}


def _qi(name: str) -> str:
    """Double-quote a SQL identifier, escaping internal double quotes."""
    return '"' + name.replace('"', '""') + '"'


def _ql(value: str) -> str:
    """Single-quote a SQL string literal, escaping single quotes."""
    return "'" + value.replace("'", "''") + "'"


def _to_sql_type(
    python_type: str,
    sql_type: str | None = None,
    max_length: int | None = None,
) -> str:
    """Resolve the SQL DDL type string from parser output.

    Normalizes SQLAlchemy class names (e.g. ``DateTime``, ``String(100)``)
    to their PostgreSQL DDL equivalents (e.g. ``TIMESTAMP``, ``VARCHAR(100)``).
    """
    if sql_type:
        base = sql_type.split("(")[0]
        # String(N) / VARCHAR(N) → VARCHAR(N)
        if base in ("String", "VARCHAR") and "(" in sql_type:
            return "VARCHAR" + sql_type[len(base):]
        # Normalize SQLAlchemy class names → DDL (DateTime → TIMESTAMP, etc.)
        if base in _SQLA_CLASS_TO_DDL:
            ddl_base = _SQLA_CLASS_TO_DDL[base]
            suffix = sql_type[len(base):]  # preserves args e.g. "(10, 2)"
            return ddl_base + suffix if suffix else ddl_base
        return sql_type  # already a raw DDL type string
    if python_type == "String" and max_length:
        return f"VARCHAR({max_length})"
    return _PYTHON_TO_SQL.get(python_type, "TEXT")


def _fk_constraint_name(table: str, column: str) -> str:
    """Generate a deterministic FK constraint name."""
    return f"fk_{table}_{column}"


def _overall_risk(steps: list[MigrationStep]) -> RiskLevel:
    """Return the highest risk level across all steps."""
    if any(s.risk == RiskLevel.DANGER for s in steps):
        return RiskLevel.DANGER
    if any(s.risk == RiskLevel.CAUTION for s in steps):
        return RiskLevel.CAUTION
    return RiskLevel.SAFE


class MigrationPlanner:
    """Converts DiffItems into an ordered MigrationPlan with executable SQL.

    SQL generation rules:
    - All identifiers are double-quoted (table names, column names).
    - Execution order: TABLE_ADDED → ADD_COLUMN → ALTER → ADD_FK →
      DROP_FK → DROP_COLUMN → TABLE_REMOVED (safe first, destructive last).
    - When models are provided, TABLE_ADDED generates full CREATE TABLE DDL.
    """

    def plan(
        self,
        diffs: list[DiffItem],
        models: list[ModelSchema] | None = None,
    ) -> MigrationPlan:
        """Convert DiffItems to a MigrationPlan.

        Args:
            diffs: Output from DiffEngine (optionally enriched by RiskAnalyzer).
            models: ModelSchema list; needed for full CREATE TABLE generation.
        """
        model_by_table: dict[str, ModelSchema] = {
            m.tablename: m for m in (models or [])
        }
        ordered = sorted(diffs, key=lambda d: _STEP_ORDER.get(d.diff_type, 99))

        steps: list[MigrationStep] = []
        for diff in ordered:
            step = self._generate_step(diff, model_by_table)
            if step is not None:
                steps.append(step)

        return MigrationPlan(
            steps=tuple(steps),
            overall_risk=_overall_risk(steps),
        )

    # ── Step generators ────────────────────────────────────────────────────────

    def _generate_step(
        self,
        diff: DiffItem,
        model_by_table: dict[str, ModelSchema],
    ) -> MigrationStep | None:
        dt = diff.diff_type

        if dt == DiffType.TABLE_ADDED:
            return self._step_table_added(diff, model_by_table)

        if dt == DiffType.TABLE_REMOVED:
            return MigrationStep(
                sql=f"DROP TABLE {_qi(diff.table_name)};",
                risk=RiskLevel.DANGER,
                description=diff.description,
                rollback_sql=None,
            )

        if dt == DiffType.COLUMN_ADDED:
            return self._step_column_added(diff, model_by_table)

        if dt == DiffType.COLUMN_REMOVED:
            return MigrationStep(
                sql=(
                    f"ALTER TABLE {_qi(diff.table_name)} "
                    f"DROP COLUMN {_qi(diff.column_name or '')};"
                ),
                risk=RiskLevel.DANGER,
                description=diff.description,
                rollback_sql=None,
            )

        if dt == DiffType.COLUMN_TYPE_CHANGED:
            target_type = _PYTHON_TO_SQL.get(diff.model_value or "", "TEXT")
            return MigrationStep(
                sql=(
                    f"ALTER TABLE {_qi(diff.table_name)} "
                    f"ALTER COLUMN {_qi(diff.column_name or '')} TYPE {target_type};"
                ),
                risk=diff.risk if diff.risk != RiskLevel.SAFE else RiskLevel.CAUTION,
                description=diff.description,
                rollback_sql=(
                    f"ALTER TABLE {_qi(diff.table_name)} "
                    f"ALTER COLUMN {_qi(diff.column_name or '')} "
                    f"TYPE {diff.db_value or 'text'};"
                ),
            )

        if dt == DiffType.COLUMN_NULLABLE_CHANGED:
            return self._step_nullable_changed(diff)

        if dt == DiffType.FK_ADDED:
            return self._step_fk_added(diff)

        if dt == DiffType.FK_REMOVED:
            constraint = _fk_constraint_name(diff.table_name, diff.column_name or "")
            return MigrationStep(
                sql=(
                    f"ALTER TABLE {_qi(diff.table_name)} "
                    f"DROP CONSTRAINT {_qi(constraint)};"
                ),
                risk=RiskLevel.CAUTION,
                description=diff.description,
                rollback_sql=None,
            )

        if dt == DiffType.ENUM_VALUES_CHANGED:
            return self._step_enum_values_changed(diff)

        if dt == DiffType.RLS_ENABLED_CHANGED:
            return self._step_rls_enable(diff)

        if dt == DiffType.RLS_POLICY_ADDED:
            return self._step_rls_policy_add(diff, model_by_table)

        if dt == DiffType.RLS_POLICY_REMOVED:
            return self._step_rls_policy_remove(diff)

        if dt == DiffType.RLS_POLICY_CHANGED:
            return self._step_rls_policy_change(diff, model_by_table)

        if dt == DiffType.RLS_POLICY_UNTRACKED:
            return None  # informational only

        if dt == DiffType.ROLE_MISSING:
            return self._step_role_create(diff)

        if dt == DiffType.GRANT_ADDED:
            return self._step_grant_add(diff)

        if dt == DiffType.GRANT_REMOVED:
            return self._step_grant_remove(diff)

        return None

    def _step_table_added(
        self,
        diff: DiffItem,
        model_by_table: dict[str, ModelSchema],
    ) -> MigrationStep:
        model = model_by_table.get(diff.table_name)
        rollback = f"DROP TABLE {_qi(diff.table_name)};"

        if model is None:
            return MigrationStep(
                sql=(
                    f"CREATE TABLE {_qi(diff.table_name)} (\n"
                    f"    -- TODO: add columns from model definition\n"
                    f");"
                ),
                risk=RiskLevel.SAFE,
                description=diff.description,
                rollback_sql=rollback,
            )

        col_defs: list[str] = []
        pk_cols: list[str] = []

        for col in model.columns:
            sql_type = _to_sql_type(col.python_type, col.sql_type, col.max_length)

            if col.primary_key and col.python_type in ("Integer", "BigInteger"):
                col_def = f"    {_qi(col.name)} SERIAL"
                pk_cols.append(_qi(col.name))
            elif col.primary_key:
                col_def = f"    {_qi(col.name)} {sql_type}"
                pk_cols.append(_qi(col.name))
            else:
                col_def = f"    {_qi(col.name)} {sql_type}"
                if not col.nullable:
                    col_def += " NOT NULL"
                if col.server_default:
                    col_def += f" DEFAULT {col.server_default}"
                elif col.default and col.default != "None":
                    col_def += f" DEFAULT {_ql(col.default)}"

            col_defs.append(col_def)

        if pk_cols:
            col_defs.append(f"    PRIMARY KEY ({', '.join(pk_cols)})")

        return MigrationStep(
            sql=(
                f"CREATE TABLE {_qi(diff.table_name)} (\n"
                + ",\n".join(col_defs)
                + "\n);"
            ),
            risk=RiskLevel.SAFE,
            description=diff.description,
            rollback_sql=rollback,
        )

    def _step_column_added(
        self,
        diff: DiffItem,
        model_by_table: dict[str, ModelSchema],
    ) -> MigrationStep:
        col_name = diff.column_name or ""
        model = model_by_table.get(diff.table_name)
        col = None
        if model:
            col = next((c for c in model.columns if c.name == col_name), None)

        if col is not None:
            sql_type = _to_sql_type(col.python_type, col.sql_type, col.max_length)
            nullable = col.nullable
            has_default = col.default is not None or col.server_default is not None
        else:
            sql_type = _PYTHON_TO_SQL.get(diff.model_value or "String", "TEXT")
            nullable = True
            has_default = False

        col_def = f"{_qi(col_name)} {sql_type}"
        if not nullable:
            col_def += " NOT NULL"
        if col and col.server_default:
            col_def += f" DEFAULT {col.server_default}"
        elif col and col.default and col.default != "None":
            col_def += f" DEFAULT {_ql(col.default)}"

        risk = RiskLevel.CAUTION if (not nullable and not has_default) else RiskLevel.SAFE

        return MigrationStep(
            sql=f"ALTER TABLE {_qi(diff.table_name)} ADD COLUMN {col_def};",
            risk=risk,
            description=diff.description,
            rollback_sql=(
                f"ALTER TABLE {_qi(diff.table_name)} DROP COLUMN {_qi(col_name)};"
            ),
        )

    def _step_nullable_changed(self, diff: DiffItem) -> MigrationStep:
        col_name = diff.column_name or ""
        model_nullable = (diff.model_value or "True").lower() == "true"

        if model_nullable:
            sql = (
                f"ALTER TABLE {_qi(diff.table_name)} "
                f"ALTER COLUMN {_qi(col_name)} DROP NOT NULL;"
            )
            rollback = (
                f"ALTER TABLE {_qi(diff.table_name)} "
                f"ALTER COLUMN {_qi(col_name)} SET NOT NULL;"
            )
        else:
            sql = (
                f"ALTER TABLE {_qi(diff.table_name)} "
                f"ALTER COLUMN {_qi(col_name)} SET NOT NULL;"
            )
            rollback = (
                f"ALTER TABLE {_qi(diff.table_name)} "
                f"ALTER COLUMN {_qi(col_name)} DROP NOT NULL;"
            )

        return MigrationStep(
            sql=sql,
            risk=diff.risk if diff.risk != RiskLevel.SAFE else RiskLevel.CAUTION,
            description=diff.description,
            rollback_sql=rollback,
        )

    def _step_fk_added(self, diff: DiffItem) -> MigrationStep:
        col_name = diff.column_name or ""
        fk_target = diff.model_value or ""
        ref_table, _, ref_col = fk_target.partition(".")
        constraint = _fk_constraint_name(diff.table_name, col_name)

        return MigrationStep(
            sql=(
                f"ALTER TABLE {_qi(diff.table_name)} "
                f"ADD CONSTRAINT {_qi(constraint)} "
                f"FOREIGN KEY ({_qi(col_name)}) "
                f"REFERENCES {_qi(ref_table)} ({_qi(ref_col)});"
            ),
            risk=RiskLevel.SAFE,
            description=diff.description,
            rollback_sql=(
                f"ALTER TABLE {_qi(diff.table_name)} "
                f"DROP CONSTRAINT {_qi(constraint)};"
            ),
        )

    def _step_enum_values_changed(self, diff: DiffItem) -> MigrationStep | None:
        model_vals = {v.strip() for v in (diff.model_value or "").split(",") if v.strip()}
        db_vals = {v.strip() for v in (diff.db_value or "").split(",") if v.strip()}
        added = model_vals - db_vals

        if not added:
            return None

        type_name = f"{diff.table_name}_{diff.column_name or 'status'}"
        sql_parts = [
            f"ALTER TYPE {_qi(type_name)} ADD VALUE {_ql(v)};"
            for v in sorted(added)
        ]

        return MigrationStep(
            sql="\n".join(sql_parts),
            risk=diff.risk if diff.risk != RiskLevel.SAFE else RiskLevel.CAUTION,
            description=diff.description,
            rollback_sql=None,
        )

    def _step_rls_enable(self, diff: DiffItem) -> MigrationStep:
        return MigrationStep(
            sql=f"ALTER TABLE {_qi(diff.table_name)} ENABLE ROW LEVEL SECURITY;",
            risk=RiskLevel.CAUTION,
            description=diff.description,
            rollback_sql=f"ALTER TABLE {_qi(diff.table_name)} DISABLE ROW LEVEL SECURITY;",
        )

    def _step_rls_policy_add(
        self, diff: DiffItem, model_by_table: dict[str, ModelSchema]
    ) -> MigrationStep:
        policy_name = diff.model_value or "unknown_policy"
        model = model_by_table.get(diff.table_name)
        policy: RLSPolicySchema | None = None
        if model:
            policy = next(
                (p for p in model.rls_policies if p.name == policy_name), None
            )

        if policy is not None:
            permissive = "PERMISSIVE" if policy.permissive else "RESTRICTIVE"
            parts = [
                f"CREATE POLICY {_qi(policy.name)}",
                f"ON {_qi(policy.table_name)}",
                f"AS {permissive}",
                f"FOR {policy.command.value}",
                f"TO {policy.role}",
                f"USING ({policy.using_expr})",
            ]
            if policy.with_check_expr:
                parts.append(f"WITH CHECK ({policy.with_check_expr})")
            sql = "\n".join(parts) + ";"
        else:
            sql = f"-- TODO: CREATE POLICY {_qi(policy_name)} ON {_qi(diff.table_name)};"

        return MigrationStep(
            sql=sql,
            risk=RiskLevel.CAUTION,
            description=f"Create RLS policy {policy_name!r} on {diff.table_name!r}",
            rollback_sql=f"DROP POLICY {_qi(policy_name)} ON {_qi(diff.table_name)};",
        )

    def _step_rls_policy_remove(self, diff: DiffItem) -> MigrationStep:
        policy_name = diff.model_value
        assert policy_name is not None, (
            "RLS_POLICY_REMOVED diff must have model_value set to policy name"
        )
        return MigrationStep(
            sql=f"DROP POLICY {_qi(policy_name)} ON {_qi(diff.table_name)};",
            risk=RiskLevel.DANGER,
            description=diff.description,
            rollback_sql=None,
        )

    def _step_rls_policy_change(
        self, diff: DiffItem, model_by_table: dict[str, ModelSchema]
    ) -> MigrationStep:
        policy_name = diff.model_value or "unknown_policy"
        # Drop + recreate approach
        drop_sql = f"DROP POLICY IF EXISTS {_qi(policy_name)} ON {_qi(diff.table_name)};"
        model = model_by_table.get(diff.table_name)
        policy: RLSPolicySchema | None = None
        if model:
            policy = next(
                (p for p in model.rls_policies if p.name == policy_name), None
            )

        if policy is not None:
            permissive = "PERMISSIVE" if policy.permissive else "RESTRICTIVE"
            parts = [
                f"CREATE POLICY {_qi(policy.name)}",
                f"ON {_qi(policy.table_name)}",
                f"AS {permissive}",
                f"FOR {policy.command.value}",
                f"TO {policy.role}",
                f"USING ({policy.using_expr})",
            ]
            if policy.with_check_expr:
                parts.append(f"WITH CHECK ({policy.with_check_expr})")
            create_sql = "\n".join(parts) + ";"
        else:
            create_sql = f"-- TODO: CREATE POLICY {_qi(policy_name)} ON {_qi(diff.table_name)};"

        sql = f"{drop_sql}\n{create_sql}"
        return MigrationStep(
            sql=sql,
            risk=RiskLevel.DANGER,
            description=f"Modify RLS policy {policy_name!r} on {diff.table_name!r}",
            rollback_sql=None,
        )

    def _step_role_create(self, diff: DiffItem) -> MigrationStep:
        role_name = diff.model_value or "unknown_role"
        return MigrationStep(
            sql=f"CREATE ROLE {_qi(role_name)};",
            risk=RiskLevel.CAUTION,
            description=diff.description,
            rollback_sql=f"DROP ROLE {_qi(role_name)};",
        )

    def _step_grant_add(self, diff: DiffItem) -> MigrationStep:
        # model_value format: "role:PRIVILEGE"
        parts = (diff.model_value or ":").split(":", 1)
        role = parts[0]
        privilege = parts[1] if len(parts) > 1 else "SELECT"
        return MigrationStep(
            sql=f"GRANT {privilege} ON {_qi(diff.table_name)} TO {_qi(role)};",
            risk=RiskLevel.CAUTION,
            description=diff.description,
            rollback_sql=f"REVOKE {privilege} ON {_qi(diff.table_name)} FROM {_qi(role)};",
        )

    def _step_grant_remove(self, diff: DiffItem) -> MigrationStep:
        parts = (diff.db_value or ":").split(":", 1)
        role = parts[0]
        privilege = parts[1] if len(parts) > 1 else "SELECT"
        return MigrationStep(
            sql=f"REVOKE {privilege} ON {_qi(diff.table_name)} FROM {_qi(role)};",
            risk=RiskLevel.DANGER,
            description=diff.description,
            rollback_sql=f"GRANT {privilege} ON {_qi(diff.table_name)} TO {_qi(role)};",
        )
