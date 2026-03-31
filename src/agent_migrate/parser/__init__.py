"""SQLAlchemy model parser package.

Exports parse_models() as the primary entry point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_migrate.parser.sqlalchemy import SQLAlchemyParser

if TYPE_CHECKING:
    from pathlib import Path

    from agent_migrate.types import ModelSchema

__all__ = ["parse_models", "SQLAlchemyParser"]


def parse_models(paths: list[Path]) -> list[ModelSchema]:
    """Parse SQLAlchemy models from a list of Python files.

    Uses a two-pass approach:
    1. First pass: collect all class definitions from all files (builds cross-file registry)
    2. Second pass: parse models using the full class registry for mixin resolution

    This enables cross-file mixin inheritance (e.g., BaseTenantEntity in base.py
    used by models in other files).

    Args:
        paths: Python files to scan for SQLAlchemy model classes.

    Returns:
        Flat list of ModelSchema instances from all files, in file order.
    """
    parser = SQLAlchemyParser()

    # Pass 1: collect all class definitions across all files
    parser.collect_cross_file_classes(paths)

    # Pass 2: parse models using the cross-file registry
    models: list[ModelSchema] = []
    for path in paths:
        models.extend(parser.parse_file(path))
    return models
