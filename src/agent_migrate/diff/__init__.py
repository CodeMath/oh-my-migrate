"""Diff engine for agent-migrate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_migrate.diff.engine import DiffEngine

if TYPE_CHECKING:
    from agent_migrate.types import DBTableSchema, DiffItem, ModelSchema

__all__ = ["compute_diff", "DiffEngine"]


def compute_diff(
    models: list[ModelSchema],
    tables: list[DBTableSchema],
) -> list[DiffItem]:
    """Compute structural differences between models and DB tables."""
    return DiffEngine().compute_diff(models, tables)
