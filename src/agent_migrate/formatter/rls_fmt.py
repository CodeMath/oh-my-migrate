"""format_rls() — RLS policy status output (<200 tokens)."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_migrate.types import DBRLSPolicy, DBRLSStatus, DBRoleInfo


def format_rls(
    rls_statuses: list[DBRLSStatus],
    rls_policies: list[DBRLSPolicy],
    roles: list[DBRoleInfo],
) -> str:
    """Format RLS status as human+agent readable text. Target: <200 tokens."""
    if not rls_statuses:
        return "No tables found."

    policies_by_table: dict[str, list[str]] = defaultdict(list)
    for p in rls_policies:
        policies_by_table[p.table_name].append(p.policy_name)

    lines: list[str] = [f"RLS Status ({len(rls_statuses)} tables):"]
    for s in sorted(rls_statuses, key=lambda x: x.table_name):
        status = "RLS:ON " if s.rls_enabled else "RLS:OFF"
        forced = " (forced)" if s.rls_forced else ""
        pols = policies_by_table.get(s.table_name, [])
        pol_str = f"  {len(pols)} {'policy' if len(pols) == 1 else 'policies'}"
        if pols:
            pol_str += f" ({', '.join(pols[:3])})"
            if len(pols) > 3:
                pol_str += f" +{len(pols) - 3} more"
        lines.append(f"  {s.table_name:<16} {status}{forced}{pol_str}")

    lines.append("")
    if roles:
        role_names = ", ".join(r.role_name for r in sorted(roles, key=lambda x: x.role_name))
        lines.append(f"Roles: {role_names} ({len(roles)} found)")
    else:
        lines.append("Roles: none found")

    return "\n".join(lines)
