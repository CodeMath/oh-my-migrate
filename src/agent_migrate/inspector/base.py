"""DBInspector Protocol definition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from agent_migrate.types import DBTableSchema


class DBInspector(Protocol):
    def inspect(self, engine: Engine, schema: str = "public") -> list[DBTableSchema]: ...
    def get_row_count(self, engine: Engine, table_name: str) -> int: ...
    def get_column_values(self, engine: Engine, table_name: str, column_name: str) -> list[str]: ...
