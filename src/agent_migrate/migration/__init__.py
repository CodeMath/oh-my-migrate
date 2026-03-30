"""Migration planning and execution package.

Exports plan_migration() as the primary entry point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_migrate.migration.planner import MigrationPlanner

if TYPE_CHECKING:
    from agent_migrate.types import DiffItem, MigrationPlan, ModelSchema

__all__ = ["plan_migration", "MigrationPlanner"]


def plan_migration(
    diffs: list[DiffItem],
    models: list[ModelSchema] | None = None,
) -> MigrationPlan:
    """Convert DiffItems to a MigrationPlan.

    Args:
        diffs: Output from DiffEngine.compute_diff() (optionally enriched by RiskAnalyzer).
        models: Optional ModelSchema list for full CREATE TABLE DDL generation.

    Returns:
        MigrationPlan with ordered steps and overall risk level.
    """
    return MigrationPlanner().plan(diffs, models)
