"""Inspector module — inspect DB schema into DBTableSchema list."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_migrate.inspector.postgresql import PostgreSQLInspector

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from agent_migrate.types import DBTableSchema

_inspector = PostgreSQLInspector()


def inspect_db(engine: Engine, schema: str = "public") -> list[DBTableSchema]:
    """Inspect the DB and return all user tables as DBTableSchema list."""
    return _inspector.inspect(engine, schema)


__all__ = ["inspect_db", "PostgreSQLInspector"]
