"""Type mapping between SQLAlchemy Python types and PostgreSQL data types."""

from __future__ import annotations

# Maps SQLAlchemy type names to sets of equivalent PostgreSQL data_type strings
TYPE_MAP: dict[str, set[str]] = {
    "Integer": {"integer", "int4"},
    "BigInteger": {"bigint", "int8"},
    "SmallInteger": {"smallint", "int2"},
    "String": {"character varying", "varchar", "text"},
    "Text": {"text"},
    "Boolean": {"boolean", "bool"},
    "DateTime": {"timestamp without time zone", "timestamp with time zone"},
    "Date": {"date"},
    "Float": {"double precision", "float8", "real", "float4"},
    "Numeric": {"numeric", "decimal"},
    "JSON": {"json", "jsonb"},
    "UUID": {"uuid"},
    "LargeBinary": {"bytea"},
    "Enum": {"user-defined"},
    "Time": {"time without time zone", "time"},
    "Interval": {"interval"},
    "ARRAY": {"array", "ARRAY"},
}


class TypeMapper:
    """Maps between SQLAlchemy type names and PostgreSQL data types."""

    def __init__(self) -> None:
        self._map = TYPE_MAP

    def is_compatible(self, python_type: str, pg_type: str) -> bool:
        """Return True if the SQLAlchemy type is compatible with the PostgreSQL type."""
        compatible = self._map.get(python_type)
        if compatible is None:
            # Unknown type — assume compatible to avoid false-positive diffs
            return True
        return pg_type.lower() in compatible
