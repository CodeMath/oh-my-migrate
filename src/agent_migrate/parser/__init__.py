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

    Args:
        paths: Python files to scan for SQLAlchemy model classes.

    Returns:
        Flat list of ModelSchema instances from all files, in file order.
    """
    parser = SQLAlchemyParser()
    models: list[ModelSchema] = []
    for path in paths:
        models.extend(parser.parse_file(path))
    return models
