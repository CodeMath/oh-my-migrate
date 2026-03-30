"""JSON formatters for agent-consumable output. No ANSI, compact keys."""

from __future__ import annotations

import json
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_migrate.formatter.ref import RefMap
    from agent_migrate.types import (
        DBRLSPolicy,
        DBRLSStatus,
        DBRoleInfo,
        DiffItem,
        MigrationPlan,
        ModelSchema,
    )


def _ser(obj: Any) -> Any:
    """Custom serializer: Enum→value, tuple→list."""
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(f"Cannot serialize {type(obj)}")


def _compact_model(m: ModelSchema, ref_map: RefMap | None = None) -> dict[str, Any]:
    ref = ref_map.get_ref(m) if ref_map else None
    cols = [
        {"name": c.name, "type": c.python_type, "nullable": c.nullable, "pk": c.primary_key}
        for c in m.columns
    ]
    d: dict[str, Any] = {
        "name": m.name,
        "tbl": m.tablename,
        "cols": cols,
    }
    if ref:
        d["ref"] = ref
    if m.rls_policies:
        d["rls"] = [
            {"name": p.name, "cmd": p.command.value, "expr": p.using_expr}
            for p in m.rls_policies
        ]
    if m.rls_opt_out:
        d["rls_opt_out"] = True
    return d


def _compact_diff(d: DiffItem, ref_map: RefMap | None = None) -> dict[str, Any]:
    r: dict[str, Any] = {
        "type": d.diff_type.value,
        "tbl": d.table_name,
        "risk": d.risk.value,
    }
    if d.column_name:
        r["col"] = d.column_name
    if d.description:
        r["desc"] = d.description
    if d.model_value:
        r["model_val"] = d.model_value
    if d.db_value:
        r["db_val"] = d.db_value
    if d.affected_rows is not None:
        r["rows"] = d.affected_rows
    return r


def _compact_step(s: Any) -> dict[str, Any]:
    return {
        "sql": s.sql,
        "risk": s.risk.value,
        "desc": s.description,
        "rollback": s.rollback_sql,
    }


def json_snapshot(
    models: list[ModelSchema],
    tables: list[Any],
    diffs: list[DiffItem],
    ref_map: Any,
    db_name: str,
) -> str:
    """JSON snapshot output."""
    data = {
        "v": 1,
        "cmd": "snapshot",
        "db": db_name,
        "models": [_compact_model(m, ref_map) for m in models],
        "tables": [
            {
                "name": t.name,
                "schema": t.schema_name,
                "cols": len(t.columns),
                "rows": t.row_count,
                "ref": ref_map.get_ref(t) if ref_map else None,
            }
            for t in tables
        ],
        "diffs": [_compact_diff(d, ref_map) for d in diffs],
        "drift_count": len(diffs),
    }
    return json.dumps(data, default=_ser, ensure_ascii=False)


def json_diff(diffs: list[DiffItem], ref_map: Any) -> str:
    """JSON diff output."""
    data = {
        "v": 1,
        "cmd": "diff",
        "diffs": [_compact_diff(d, ref_map) for d in diffs],
        "count": len(diffs),
    }
    return json.dumps(data, default=_ser, ensure_ascii=False)


def json_plan(plan: MigrationPlan, ref_map: Any) -> str:
    """JSON migration plan output."""
    data = {
        "v": 1,
        "cmd": "plan",
        "steps": [_compact_step(s) for s in plan.steps],
        "overall_risk": plan.overall_risk.value,
        "step_count": len(plan.steps),
    }
    return json.dumps(data, default=_ser, ensure_ascii=False)


def json_rls(
    rls_statuses: list[DBRLSStatus],
    rls_policies: list[DBRLSPolicy],
    roles: list[DBRoleInfo],
) -> str:
    """JSON RLS status output."""
    from collections import defaultdict

    policies_by_table: dict[str, list[str]] = defaultdict(list)
    for p in rls_policies:
        policies_by_table[p.table_name].append(p.policy_name)

    tables = []
    for s in rls_statuses:
        tables.append({
            "tbl": s.table_name,
            "rls": s.rls_enabled,
            "forced": s.rls_forced,
            "policies": policies_by_table.get(s.table_name, []),
        })

    data = {
        "v": 1,
        "cmd": "rls",
        "tables": tables,
        "roles": [
            {"name": r.role_name, "super": r.is_superuser, "login": r.can_login}
            for r in roles
        ],
    }
    return json.dumps(data, default=_ser, ensure_ascii=False)


def json_auto(
    models: list[ModelSchema],
    tables: list[Any],
    diffs: list[DiffItem],
    plan: MigrationPlan | None,
    ref_map: Any,
    db_name: str,
    generated_file: str | None = None,
    applied: bool = False,
) -> str:
    """JSON auto (combined) output."""
    data: dict[str, Any] = {
        "v": 1,
        "cmd": "auto",
        "db": db_name,
        "drift_count": len(diffs),
        "in_sync": len(diffs) == 0,
        "diffs": [_compact_diff(d, ref_map) for d in diffs],
    }
    if plan and plan.steps:
        data["plan"] = {
            "steps": [_compact_step(s) for s in plan.steps],
            "overall_risk": plan.overall_risk.value,
            "step_count": len(plan.steps),
        }
    if generated_file:
        data["generated"] = generated_file
    if applied:
        data["applied"] = True
    return json.dumps(data, default=_ser, ensure_ascii=False)
