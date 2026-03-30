"""Formatter module — agent-optimized output with @ref system."""

from __future__ import annotations

from agent_migrate.formatter.diff_fmt import format_diff
from agent_migrate.formatter.json_fmt import (
    json_auto,
    json_diff,
    json_plan,
    json_rls,
    json_snapshot,
)
from agent_migrate.formatter.plan_fmt import format_plan
from agent_migrate.formatter.rls_fmt import format_rls
from agent_migrate.formatter.snapshot_fmt import format_snapshot

__all__ = [
    "format_diff",
    "format_plan",
    "format_rls",
    "format_snapshot",
    "json_auto",
    "json_diff",
    "json_plan",
    "json_rls",
    "json_snapshot",
]
