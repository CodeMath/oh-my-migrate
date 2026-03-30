"""Version tracking table for Path B (raw SQL) migrations.

Manages the _agent_migrate_versions table that records applied migrations.
All SQL uses sqlalchemy.text() with bound parameters — no f-string SQL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy import Connection

# DDL uses a hardcoded table name (not user-controlled), defined once here.
_CREATE_SQL = text(
    "CREATE TABLE IF NOT EXISTS _agent_migrate_versions ("
    "    id SERIAL PRIMARY KEY,"
    "    version VARCHAR(255) NOT NULL UNIQUE,"
    "    applied_at TIMESTAMP NOT NULL,"
    "    checksum VARCHAR(64) NOT NULL,"
    "    description TEXT"
    ")"
)

_INSERT_SQL = text(
    "INSERT INTO _agent_migrate_versions (version, applied_at, checksum, description)"
    " VALUES (:version, :applied_at, :checksum, :description)"
)

_SELECT_VERSIONS_SQL = text(
    "SELECT version FROM _agent_migrate_versions ORDER BY applied_at"
)

_SELECT_CHECKSUM_SQL = text(
    "SELECT checksum FROM _agent_migrate_versions WHERE version = :version"
)


class VersionTable:
    """Manage the ``_agent_migrate_versions`` tracking table.

    All methods accept an open ``sqlalchemy.Connection``.  The caller is
    responsible for committing or rolling back the surrounding transaction.
    """

    def ensure_table(self, conn: Connection) -> None:
        """Create the version table if it does not already exist."""
        conn.execute(_CREATE_SQL)

    def record_applied(
        self,
        conn: Connection,
        version: str,
        checksum: str,
        description: str = "",
    ) -> None:
        """Insert a row recording a successfully applied migration."""
        conn.execute(
            _INSERT_SQL,
            {
                "version": version,
                "applied_at": datetime.now(tz=UTC),
                "checksum": checksum,
                "description": description,
            },
        )

    def get_applied_versions(self, conn: Connection) -> list[str]:
        """Return all applied version IDs in chronological order."""
        result = conn.execute(_SELECT_VERSIONS_SQL)
        return [row[0] for row in result]

    def verify_checksum(self, conn: Connection, version: str, checksum: str) -> bool:
        """Return True if the stored checksum for *version* matches *checksum*."""
        result = conn.execute(_SELECT_CHECKSUM_SQL, {"version": version})
        row = result.fetchone()
        return row is not None and row[0] == checksum
