"""Raw SQL migration generator (Path B).

Writes timestamped .sql files with rollback SQL as comments.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from agent_migrate.types import MigrationPlan


def _slug(message: str) -> str:
    """Convert *message* to a safe filename component (max 50 chars)."""
    return re.sub(r"[^a-z0-9]+", "_", message.lower()).strip("_")[:50]


def _checksum(sql: str) -> str:
    """Return a SHA-256 hex digest of *sql*."""
    return hashlib.sha256(sql.encode()).hexdigest()


class RawSQLGenerator:
    """Path B: write a timestamped .sql file containing upgrade SQL and rollback comments.

    File layout::

        migrations/{timestamp}_{slug}.sql

    Content structure::

        -- Migration: <message>
        -- Generated: <timestamp>
        -- Checksum: <sha256-of-upgrade-sql>

        -- ===== UPGRADE =====
        <SQL statements>

        -- ===== ROLLBACK (run in reverse) =====
        -- <rollback SQL statements, one per line>
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    def generate(self, plan: MigrationPlan, message: str) -> Path:
        """Write a migration SQL file for *plan* and return its path.

        The output directory is created if it does not exist.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{_slug(message)}.sql"
        filepath = self._output_dir / filename
        filepath.write_text(_render(plan, message, timestamp), encoding="utf-8")
        return filepath


# ── Rendering ─────────────────────────────────────────────────────────────────


def _render(plan: MigrationPlan, message: str, timestamp: str) -> str:
    """Return the full file content for the SQL migration."""
    upgrade_sql = "\n".join(step.sql for step in plan.steps)
    lines: list[str] = [
        f"-- Migration: {message}",
        f"-- Generated: {timestamp}",
        f"-- Checksum: {_checksum(upgrade_sql)}",
        "",
        "-- ===== UPGRADE =====",
        upgrade_sql,
        "",
    ]

    rollback_steps = [s for s in reversed(plan.steps) if s.rollback_sql]
    if rollback_steps:
        lines.append("-- ===== ROLLBACK (run in reverse) =====")
        for step in rollback_steps:
            assert step.rollback_sql is not None
            for sql_line in step.rollback_sql.splitlines():
                lines.append(f"-- {sql_line}")
        lines.append("")

    return "\n".join(lines)
