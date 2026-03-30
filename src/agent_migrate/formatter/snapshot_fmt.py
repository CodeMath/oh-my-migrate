"""format_snapshot() — token-efficient snapshot output (<500 tokens)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_migrate.types import (
    ColumnSchema,
    DBColumnSchema,
    DBTableSchema,
    DiffItem,
    DiffType,
    ModelSchema,
)

if TYPE_CHECKING:
    from agent_migrate.formatter.ref import RefMap

# ── Type display maps ──────────────────────────────────────────────────────────

_MODEL_TYPE: dict[str, str] = {
    "Integer": "int",
    "BigInteger": "bigint",
    "SmallInteger": "smallint",
    "String": "str",
    "Text": "text",
    "Boolean": "bool",
    "DateTime": "datetime",
    "Date": "date",
    "Time": "time",
    "Float": "float",
    "Numeric": "decimal",
    "UUID": "uuid",
    "LargeBinary": "bytes",
    "Enum": "enum",
    "JSON": "json",
    "JSONB": "jsonb",
}

_DB_TYPE: dict[str, str] = {
    "integer": "int4",
    "bigint": "int8",
    "smallint": "int2",
    "character varying": "varchar",
    "character": "char",
    "text": "text",
    "boolean": "bool",
    "timestamp without time zone": "timestamp",
    "timestamp with time zone": "timestamptz",
    "date": "date",
    "time without time zone": "time",
    "numeric": "numeric",
    "double precision": "float8",
    "real": "float4",
    "bytea": "bytea",
    "uuid": "uuid",
    "json": "json",
    "jsonb": "jsonb",
    "user-defined": "enum",
    "ARRAY": "array",
}

_MAX_COLS = 8   # truncate if more than this
_SHOW_COLS = 6  # show this many before "... +N more"


def _fmt_model_col(col: ColumnSchema, ref_map: RefMap) -> str:
    if col.foreign_key:
        ref_tablename = col.foreign_key.split(".")[0]
        fk_ref = ref_map.find_model_ref(ref_tablename) or "?"
        return f"{col.name}\u2192{fk_ref}"
    type_str = _MODEL_TYPE.get(col.python_type, col.python_type.lower())
    suffix = "?" if col.nullable and not col.primary_key else ""
    return f"{col.name}:{type_str}{suffix}"


def _fmt_db_col(col: DBColumnSchema, ref_map: RefMap) -> str:
    if col.foreign_table:
        fk_ref = ref_map.find_table_ref(col.foreign_table) or "?"
        return f"{col.name}\u2192{fk_ref}"
    type_str = _DB_TYPE.get(col.data_type, col.data_type)
    suffix = "?" if col.is_nullable and not col.is_primary_key else ""
    return f"{col.name}:{type_str}{suffix}"


def _cols_str(parts: list[str], total: int) -> str:
    """Format column list with optional truncation."""
    if total > _MAX_COLS:
        shown = parts[:_SHOW_COLS]
        shown.append(f"... +{total - _SHOW_COLS} more")
        return ", ".join(shown)
    return ", ".join(parts)


def format_snapshot(
    models: list[ModelSchema],
    tables: list[DBTableSchema],
    diffs: list[DiffItem],
    ref_map: RefMap,
    db_name: str,
    *,
    applied_count: int = 0,
    pending_count: int = 0,
) -> str:
    """Format a snapshot of models + DB tables.  Target: <500 tokens."""
    lines: list[str] = []

    # ── Models ──
    lines.append(f"Models ({len(models)} found):")
    for model in models:
        ref = ref_map.get_ref(model) or "?"
        col_parts = [_fmt_model_col(c, ref_map) for c in model.columns]
        cols = _cols_str(col_parts, len(model.columns))
        rls_tag = ""
        if model.rls_opt_out:
            rls_tag = "  RLS:opt-out"
        elif model.rls_policies:
            presets = {p.name.rsplit("_", 1)[-1] for p in model.rls_policies}
            rls_tag = f"  RLS:{','.join(sorted(presets))}"
        lines.append(f"  {ref} {model.name:<12} ({cols}){rls_tag}")

    lines.append("")

    # ── Database ──
    lines.append(f"Database ({db_name}):")
    for table in tables:
        ref = ref_map.get_ref(table) or "?"
        col_parts = [_fmt_db_col(c, ref_map) for c in table.columns]
        cols = _cols_str(col_parts, len(table.columns))
        row_info = f"  {table.row_count} rows" if table.row_count > 0 else ""
        lines.append(f"  {ref} {table.name:<12} ({cols}){row_info}")

    lines.append("")

    # ── Drift ──
    lines.append(f"Drift: {len(diffs)} difference{'s' if len(diffs) != 1 else ''}")
    for diff in diffs:
        lines.append(f"  {_fmt_drift_line(diff, ref_map)}")

    lines.append("")

    # ── Migrations ──
    lines.append(f"Migrations: {applied_count} applied, {pending_count} pending")

    return "\n".join(lines)


def _fmt_drift_line(diff: DiffItem, ref_map: RefMap) -> str:
    """One-line drift summary for a DiffItem."""
    # Choose model ref or table ref depending on which side "owns" the diff
    if diff.diff_type in (
        DiffType.TABLE_REMOVED,
        DiffType.COLUMN_REMOVED,
        DiffType.FK_REMOVED,
        DiffType.RLS_POLICY_REMOVED,
        DiffType.RLS_POLICY_UNTRACKED,
        DiffType.GRANT_REMOVED,
    ):
        ref = ref_map.find_table_ref(diff.table_name) or "?"
    else:
        ref = ref_map.find_model_ref(diff.table_name) or "?"

    target = f"{ref}.{diff.column_name}" if diff.column_name else ref

    if diff.diff_type == DiffType.COLUMN_ADDED:
        return f"{target}  model has, DB missing"
    elif diff.diff_type == DiffType.COLUMN_REMOVED:
        return f"{target}  DB has, model missing"
    elif diff.diff_type == DiffType.COLUMN_TYPE_CHANGED:
        return f"{target}  type mismatch ({diff.model_value} \u2192 {diff.db_value})"
    elif diff.diff_type == DiffType.COLUMN_NULLABLE_CHANGED:
        return f"{target}  nullable mismatch"
    elif diff.diff_type == DiffType.TABLE_ADDED:
        return f"{target}  table in model, not in DB"
    elif diff.diff_type == DiffType.TABLE_REMOVED:
        return f"{target}  table in DB, not in model"
    elif diff.diff_type == DiffType.ENUM_VALUES_CHANGED:
        return f"{target}  enum values changed"
    elif diff.diff_type == DiffType.RLS_ENABLED_CHANGED:
        return f"{target}  RLS defined in model but disabled in DB"
    elif diff.diff_type == DiffType.RLS_POLICY_ADDED:
        return f"{target}  RLS policy in model, not in DB"
    elif diff.diff_type == DiffType.RLS_POLICY_REMOVED:
        return f"{target}  RLS policy in DB, not in model"
    elif diff.diff_type == DiffType.RLS_POLICY_CHANGED:
        return f"{target}  RLS policy mismatch"
    elif diff.diff_type == DiffType.RLS_POLICY_UNTRACKED:
        return f"{target}  RLS policy in DB, untracked by model"
    elif diff.diff_type == DiffType.ROLE_MISSING:
        return f"{target}  required role missing in DB"
    elif diff.diff_type == DiffType.GRANT_ADDED:
        return f"{target}  grant in model, not in DB"
    elif diff.diff_type == DiffType.GRANT_REMOVED:
        return f"{target}  grant in DB, not in model"
    else:
        return f"{target}  {diff.description}"
