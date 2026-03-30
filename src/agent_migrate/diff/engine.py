"""Diff engine: compares model schemas against DB table schemas."""

from __future__ import annotations

import re
from collections import defaultdict

from agent_migrate.diff.type_map import TypeMapper
from agent_migrate.types import (
    DBRLSPolicy,
    DBRLSStatus,
    DBRoleInfo,
    DBTableSchema,
    DiffItem,
    DiffType,
    ModelSchema,
    RiskLevel,
    RoleRequirement,
)

_RE_WHITESPACE = re.compile(r"\s+")


class DiffEngine:
    """Computes structural differences between SQLAlchemy models and DB tables."""

    def __init__(self) -> None:
        self._type_mapper = TypeMapper()

    def compute_diff(
        self,
        models: list[ModelSchema],
        tables: list[DBTableSchema],
    ) -> list[DiffItem]:
        """Compare models against DB tables and return a list of DiffItems."""
        diffs: list[DiffItem] = []

        model_by_table: dict[str, ModelSchema] = {m.tablename: m for m in models}
        table_by_name: dict[str, DBTableSchema] = {t.name: t for t in tables}

        # TABLE_ADDED: model exists but no DB table
        for tablename, model in model_by_table.items():
            if tablename not in table_by_name:
                diffs.append(
                    DiffItem(
                        diff_type=DiffType.TABLE_ADDED,
                        table_name=tablename,
                        description=f"Model {model.name!r} has no corresponding DB table",
                    )
                )

        # TABLE_REMOVED: DB table exists but no model
        for tablename in table_by_name:
            if tablename not in model_by_table:
                diffs.append(
                    DiffItem(
                        diff_type=DiffType.TABLE_REMOVED,
                        table_name=tablename,
                        description=f"DB table {tablename!r} has no corresponding model",
                        risk=RiskLevel.DANGER,
                    )
                )

        # Column / FK / Index diffs for matched tables
        for tablename, model in model_by_table.items():
            if tablename not in table_by_name:
                continue
            table = table_by_name[tablename]
            diffs.extend(self._diff_columns(model, table))
            diffs.extend(self._diff_fks(model, table))
            diffs.extend(self._diff_indexes(model, table))

        return diffs

    def _diff_columns(
        self, model: ModelSchema, table: DBTableSchema
    ) -> list[DiffItem]:
        diffs: list[DiffItem] = []
        model_cols = {c.name: c for c in model.columns}
        db_cols = {c.name: c for c in table.columns}

        # COLUMN_ADDED
        for col_name, model_col in model_cols.items():
            if col_name not in db_cols:
                has_default = (
                    model_col.default is not None or model_col.server_default is not None
                )
                is_not_null_no_default = not model_col.nullable and not has_default
                description = (
                    f"Column {col_name!r} exists in model but not in DB "
                    f"[not_null_no_default]"
                    if is_not_null_no_default
                    else f"Column {col_name!r} exists in model but not in DB"
                )
                diffs.append(
                    DiffItem(
                        diff_type=DiffType.COLUMN_ADDED,
                        table_name=model.tablename,
                        column_name=col_name,
                        description=description,
                        model_value=model_col.python_type,
                    )
                )

        # COLUMN_REMOVED
        for col_name in db_cols:
            if col_name not in model_cols:
                diffs.append(
                    DiffItem(
                        diff_type=DiffType.COLUMN_REMOVED,
                        table_name=model.tablename,
                        column_name=col_name,
                        description=(
                            f"Column {col_name!r} exists in DB but not in model"
                        ),
                        db_value=db_cols[col_name].data_type,
                    )
                )

        # Per-column comparison
        for col_name, model_col in model_cols.items():
            if col_name not in db_cols:
                continue
            db_col = db_cols[col_name]

            # TYPE_CHANGED
            if not self._type_mapper.is_compatible(model_col.python_type, db_col.data_type):
                diffs.append(
                    DiffItem(
                        diff_type=DiffType.COLUMN_TYPE_CHANGED,
                        table_name=model.tablename,
                        column_name=col_name,
                        description=(
                            f"Type mismatch: model={model_col.python_type!r}, "
                            f"db={db_col.data_type!r}"
                        ),
                        model_value=model_col.python_type,
                        db_value=db_col.data_type,
                    )
                )

            # NULLABLE_CHANGED
            if model_col.nullable != db_col.is_nullable:
                diffs.append(
                    DiffItem(
                        diff_type=DiffType.COLUMN_NULLABLE_CHANGED,
                        table_name=model.tablename,
                        column_name=col_name,
                        description=(
                            f"Nullable mismatch: model={model_col.nullable}, "
                            f"db={db_col.is_nullable}"
                        ),
                        model_value=str(model_col.nullable),
                        db_value=str(db_col.is_nullable),
                    )
                )

            # DEFAULT_CHANGED
            model_default = model_col.server_default or model_col.default
            db_default = db_col.column_default
            if _defaults_differ(model_default, db_default):
                diffs.append(
                    DiffItem(
                        diff_type=DiffType.COLUMN_DEFAULT_CHANGED,
                        table_name=model.tablename,
                        column_name=col_name,
                        description=(
                            f"Default mismatch: model={model_default!r}, "
                            f"db={db_default!r}"
                        ),
                        model_value=model_default,
                        db_value=db_default,
                    )
                )

            # ENUM_VALUES_CHANGED — Phase 1 limitation:
            # Enum value comparison requires querying pg_enum for the DB's actual
            # enum values, which is not yet implemented in the inspector.
            # This will be implemented in Phase 1.5 alongside SQLModel support.
            # For now, enum type mismatches are caught by COLUMN_TYPE_CHANGED above.

        return diffs

    def _diff_fks(self, model: ModelSchema, table: DBTableSchema) -> list[DiffItem]:
        diffs: list[DiffItem] = []
        model_fks = {
            c.name: c.foreign_key
            for c in model.columns
            if c.foreign_key is not None
        }
        db_fks = {
            c.name: f"{c.foreign_table}.{c.foreign_column}"
            for c in table.columns
            if c.foreign_table is not None
        }

        for col_name, fk_target in model_fks.items():
            if col_name not in db_fks:
                diffs.append(
                    DiffItem(
                        diff_type=DiffType.FK_ADDED,
                        table_name=model.tablename,
                        column_name=col_name,
                        description=(
                            f"FK {col_name!r} -> {fk_target!r} in model but not in DB"
                        ),
                        model_value=fk_target,
                    )
                )

        for col_name, fk_target in db_fks.items():
            if col_name not in model_fks:
                diffs.append(
                    DiffItem(
                        diff_type=DiffType.FK_REMOVED,
                        table_name=model.tablename,
                        column_name=col_name,
                        description=(
                            f"FK {col_name!r} -> {fk_target!r} in DB but not in model"
                        ),
                        db_value=fk_target,
                    )
                )

        return diffs

    def _diff_indexes(self, model: ModelSchema, table: DBTableSchema) -> list[DiffItem]:
        # Index diffing is based on model IndexSchema only.
        # DB-side index discovery is not yet included in DBTableSchema.
        # This is a placeholder for future expansion.
        return []

    def compute_rls_diff(
        self,
        models: list[ModelSchema],
        db_rls_statuses: list[DBRLSStatus],
        db_rls_policies: list[DBRLSPolicy],
    ) -> list[DiffItem]:
        """Compare model-defined RLS policies against DB-actual RLS state.

        Bidirectional drift detection:
        - Model has __rls__ + DB missing -> RLS_POLICY_ADDED, RLS_ENABLED_CHANGED
        - DB has policy + Model has no __rls__ -> RLS_POLICY_UNTRACKED (CAUTION)
        - Model has __rls__ = False -> skip entirely (explicit opt-out)
        """
        diffs: list[DiffItem] = []

        model_by_table: dict[str, ModelSchema] = {m.tablename: m for m in models}
        db_status_by_table = {s.table_name: s for s in db_rls_statuses}
        db_policies_by_table: dict[str, list[DBRLSPolicy]] = defaultdict(list)
        for p in db_rls_policies:
            db_policies_by_table[p.table_name].append(p)

        all_tables = set(model_by_table.keys()) | set(db_policies_by_table.keys())

        for tablename in sorted(all_tables):
            model = model_by_table.get(tablename)

            # Skip if model has explicit opt-out (__rls__ = False)
            if model and model.rls_opt_out:
                continue

            has_model_rls = model is not None and len(model.rls_policies) > 0
            has_db_policies = bool(db_policies_by_table.get(tablename))
            db_status = db_status_by_table.get(tablename)

            # DB has policies but model has no __rls__ (untracked)
            if (
                has_db_policies and model is not None
                and not has_model_rls and not model.rls_opt_out
            ):
                for dp in db_policies_by_table[tablename]:
                    diffs.append(
                        DiffItem(
                            diff_type=DiffType.RLS_POLICY_UNTRACKED,
                            table_name=tablename,
                            description=(
                                f"Policy {dp.policy_name!r} exists in DB but table has no "
                                f"__rls__ in model"
                            ),
                            db_value=dp.using_qual,
                        )
                    )
                continue

            # DB has policies but table has no model (DB-only table)
            if has_db_policies and model is None:
                continue

            if not has_model_rls:
                continue

            # Model has __rls__ but DB has RLS disabled
            if db_status and not db_status.rls_enabled:
                diffs.append(
                    DiffItem(
                        diff_type=DiffType.RLS_ENABLED_CHANGED,
                        table_name=tablename,
                        description="Model defines RLS but table has RLS disabled",
                        model_value="enabled",
                        db_value="disabled",
                    )
                )

            # Policy-level comparison
            assert model is not None
            model_policies = {p.name: p for p in model.rls_policies}
            db_policies = {
                p.policy_name: p for p in db_policies_by_table.get(tablename, [])
            }

            for name in sorted(model_policies):
                if name not in db_policies:
                    diffs.append(
                        DiffItem(
                            diff_type=DiffType.RLS_POLICY_ADDED,
                            table_name=tablename,
                            description=f"Policy {name!r} defined in model but not in DB",
                            model_value=name,
                        )
                    )
                else:
                    mp = model_policies[name]
                    dp = db_policies[name]
                    if not self._rls_policies_match(mp, dp):
                        diffs.append(
                            DiffItem(
                                diff_type=DiffType.RLS_POLICY_CHANGED,
                                table_name=tablename,
                                description=f"Policy {name!r} differs between model and DB",
                                model_value=name,
                                db_value=dp.using_qual,
                            )
                        )

            for name in sorted(db_policies):
                if name not in model_policies:
                    diffs.append(
                        DiffItem(
                            diff_type=DiffType.RLS_POLICY_REMOVED,
                            table_name=tablename,
                            description=f"Policy {name!r} exists in DB but not in model",
                            model_value=name,
                            db_value=db_policies[name].using_qual,
                        )
                    )

        return diffs

    def _rls_policies_match(self, model_policy: object, db_policy: DBRLSPolicy) -> bool:
        """Compare model RLS policy against DB policy (normalized)."""
        from agent_migrate.types import RLSPolicySchema

        if not isinstance(model_policy, RLSPolicySchema):
            return False
        model_using = _normalize_sql(model_policy.using_expr)
        db_using = _normalize_sql(db_policy.using_qual or "")
        return model_using == db_using

    def compute_role_diff(
        self,
        role_requirements: list[RoleRequirement],
        db_roles: list[DBRoleInfo],
        db_grants: dict[str, list[tuple[str, str]]],
    ) -> list[DiffItem]:
        """Compare required roles/grants against DB state."""
        diffs: list[DiffItem] = []
        db_role_names = {r.role_name for r in db_roles}

        for req in role_requirements:
            if req.role_name not in db_role_names:
                diffs.append(
                    DiffItem(
                        diff_type=DiffType.ROLE_MISSING,
                        table_name=req.table_name,
                        description=f"Required role {req.role_name!r} not found in DB",
                        model_value=req.role_name,
                    )
                )
                continue

            # Check grants
            table_grants = db_grants.get(req.table_name, [])
            existing_privs = {
                priv for role, priv in table_grants if role == req.role_name
            }
            for grant in req.grants:
                if grant not in existing_privs:
                    diffs.append(
                        DiffItem(
                            diff_type=DiffType.GRANT_ADDED,
                            table_name=req.table_name,
                            description=f"Grant {grant} to {req.role_name!r} on {req.table_name!r}",
                            model_value=f"{req.role_name}:{grant}",
                        )
                    )

        return diffs


def _normalize_sql(expr: str) -> str:
    """Normalize SQL expression for comparison (lowercase, collapse whitespace)."""
    return _RE_WHITESPACE.sub(" ", expr.lower().strip())


def _defaults_differ(model_default: str | None, db_default: str | None) -> bool:
    """Return True if the defaults are meaningfully different."""
    # Normalize: treat empty string same as None
    a = model_default or None
    b = db_default or None
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    # Strip common PostgreSQL casting suffixes, e.g. "'now'::text"
    b_stripped = b.split("::")[0].strip("'\" ")
    a_stripped = a.strip("'\" ")
    return a_stripped != b_stripped
