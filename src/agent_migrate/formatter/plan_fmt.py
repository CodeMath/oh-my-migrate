"""format_plan() — token-efficient migration plan output (<300 tokens)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_migrate.types import MigrationPlan, MigrationStep, RiskLevel

if TYPE_CHECKING:
    from agent_migrate.formatter.ref import RefMap

_RISK_LABEL: dict[RiskLevel, str] = {
    RiskLevel.SAFE:    "SAFE",
    RiskLevel.CAUTION: "CAUTION",
    RiskLevel.DANGER:  "DANGER",
}


def format_plan(plan: MigrationPlan, ref_map: RefMap) -> str:
    """Format a MigrationPlan as human+agent readable text.  Target: <300 tokens.

    Format:
      Plan: N steps

      1. [SAFE] ALTER TABLE products ADD COLUMN description TEXT;
         Impact: 0 rows, additive change

      2. [DANGER] ALTER TABLE orders DROP COLUMN old_col;
         ⚠️  Warning: drop column - data loss
         Impact: 5 rows affected

      Overall: DANGER risk
    """
    n = len(plan.steps)
    lines: list[str] = [f"Plan: {n} step{'s' if n != 1 else ''}", ""]

    for i, step in enumerate(plan.steps, start=1):
        risk_label = _RISK_LABEL[step.risk]
        # Trim SQL to one logical line (strip leading/trailing whitespace)
        sql_line = step.sql.strip().rstrip(";") + ";"
        lines.append(f"{i}. [{risk_label}] {sql_line}")

        impact = _impact_line(step)
        lines.append(f"   Impact: {impact}")

        if step.risk == RiskLevel.DANGER:
            lines.append(f"   \u26a0\ufe0f  Warning: {step.description}")

        if step.risk != RiskLevel.SAFE and step.rollback_sql:
            lines.append(f"   Rollback: {step.rollback_sql.strip()}")

        lines.append("")

    overall = _RISK_LABEL[plan.overall_risk]
    lines.append(f"Overall: {overall} risk")

    return "\n".join(lines)


def _impact_line(step: MigrationStep) -> str:
    if step.affected_rows is not None:
        if step.affected_rows == 0:
            return "0 rows, no data change"
        return f"{step.affected_rows} rows affected"
    if step.risk == RiskLevel.SAFE:
        return "additive change, no data loss"
    return "estimated — inspect before applying"
