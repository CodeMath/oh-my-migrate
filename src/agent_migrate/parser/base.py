"""ModelParser Protocol definition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from agent_migrate.types import ModelSchema


class ModelParser(Protocol):
    """Protocol for SQLAlchemy/SQLModel model parsers."""

    def parse_file(self, path: Path) -> list[ModelSchema]:
        """Parse all models from a Python file."""
        ...

    def parse_source(self, source: str, filename: str = "<string>") -> list[ModelSchema]:
        """Parse all models from a Python source string."""
        ...
