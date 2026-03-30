"""format_diff() — token-efficient diff output (<200 tokens)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_migrate.types import DiffItem, DiffType, RiskLevel

if TYPE_CHECKING:
    from agent_migrate.formatter.ref import RefMap

# DiffType → (symbol, use_table_ref)
# use_table_ref=True  → ref comes from DB table (@d?)
# use_table_ref=False → ref comes from model   (@m?)
_DIFF_STYLE: dict[DiffType, tuple[str, bool]] = {
    DiffType.TABLE_ADDED:             ("[+]", False),
    DiffType.TABLE_REMOVED:           ("[-]", True),
    DiffType.COLUMN_ADDED:            ("[+]", False),
    DiffType.COLUMN_REMOVED:          ("[-]", True),
    DiffType.COLUMN_TYPE_CHANGED:     ("[~]", False),
    DiffType.COLUMN_NULLABLE_CHANGED: ("[~]", False),
    DiffType.COLUMN_DEFAULT_CHANGED:  ("[~]", False),
    DiffType.ENUM_VALUES_CHANGED:     ("[~]", False),
    DiffType.FK_ADDED:                ("[+]", False),
    DiffType.FK_REMOVED:              ("[-]", True),
    DiffType.INDEX_ADDED:             ("[+]", False),
    DiffType.INDEX_REMOVED:           ("[-]", True),
    DiffType.RLS_ENABLED_CHANGED:     ("[R!]", False),
    DiffType.RLS_POLICY_ADDED:        ("[P+]", False),
    DiffType.RLS_POLICY_REMOVED:      ("[P-]", True),
    DiffType.RLS_POLICY_CHANGED:      ("[P~]", False),
    DiffType.RLS_POLICY_UNTRACKED:    ("[P?]", True),
    DiffType.ROLE_MISSING:            ("[R!]", False),
    DiffType.GRANT_ADDED:             ("[G+]", False),
    DiffType.GRANT_REMOVED:           ("[G-]", True),
}

_RISK_LABEL: dict[RiskLevel, str] = {
    RiskLevel.SAFE:    "SAFE",
    RiskLevel.CAUTION: "CAUTION",
    RiskLevel.DANGER:  "DANGER",
}


def format_diff(diffs: list[DiffItem], ref_map: RefMap) -> str:
    """Format diff items as one line each.  Target: <200 tokens.

    Format:
      [+] @m3.description  Text, nullable        SAFE
      [~] @m2.status       Enum→varchar mismatch DANGER (5 rows affected)
      [-] @d1.old_col      DB has, model missing  DANGER
    """
    if not diffs:
        return "(no differences)"

    lines: list[str] = []
    for diff in diffs:
        symbol, use_table_ref = _DIFF_STYLE.get(diff.diff_type, ("[?]", False))

        if use_table_ref:
            ref = ref_map.find_table_ref(diff.table_name) or "?"
        else:
            ref = ref_map.find_model_ref(diff.table_name) or "?"

        target = f"{ref}.{diff.column_name}" if diff.column_name else ref

        desc = _short_desc(diff)
        risk = _RISK_LABEL[diff.risk]

        row_info = ""
        if diff.affected_rows is not None:
            row_info = f" ({diff.affected_rows} rows affected)"

        lines.append(f"{symbol} {target:<20} {desc:<28} {risk}{row_info}")

    return "\n".join(lines)


def _short_desc(diff: DiffItem) -> str:
    """One-word/phrase description for the diff."""
    dt = diff.diff_type
    if dt == DiffType.COLUMN_ADDED:
        return "model has, DB missing"
    elif dt == DiffType.COLUMN_REMOVED:
        return "DB has, model missing"
    elif dt == DiffType.TABLE_ADDED:
        return "table: model has, DB missing"
    elif dt == DiffType.TABLE_REMOVED:
        return "table: DB has, model missing"
    elif dt == DiffType.COLUMN_TYPE_CHANGED:
        if diff.model_value and diff.db_value:
            return f"{diff.model_value}\u2192{diff.db_value} mismatch"
        return "type mismatch"
    elif dt == DiffType.COLUMN_NULLABLE_CHANGED:
        return "nullable mismatch"
    elif dt == DiffType.COLUMN_DEFAULT_CHANGED:
        return "default mismatch"
    elif dt == DiffType.ENUM_VALUES_CHANGED:
        return "enum values changed"
    elif dt == DiffType.FK_ADDED:
        return "FK: model has, DB missing"
    elif dt == DiffType.FK_REMOVED:
        return "FK: DB has, model missing"
    elif dt == DiffType.RLS_ENABLED_CHANGED:
        return "RLS disabled in DB"
    elif dt == DiffType.RLS_POLICY_ADDED:
        return "policy: model has, DB missing"
    elif dt == DiffType.RLS_POLICY_REMOVED:
        return "policy: DB has, model missing"
    elif dt == DiffType.RLS_POLICY_CHANGED:
        return "policy mismatch"
    elif dt == DiffType.RLS_POLICY_UNTRACKED:
        return "policy: DB has, model untracked"
    elif dt == DiffType.ROLE_MISSING:
        return "role missing in DB"
    elif dt == DiffType.GRANT_ADDED:
        return "grant: model has, DB missing"
    elif dt == DiffType.GRANT_REMOVED:
        return "grant: DB has, model missing"
    else:
        return diff.description or str(dt.value)
