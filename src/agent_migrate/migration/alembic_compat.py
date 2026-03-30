"""Alembic-based migration generator (Path A).

Strategy:
1. Snapshot existing files in versions/ directory.
2. Call alembic.command.revision() to create an empty revision.
3. Detect the new file by comparing before/after snapshot.
4. Inject upgrade() and downgrade() SQL bodies via regex substitution.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from agent_migrate.config import AlembicConfig
    from agent_migrate.types import MigrationPlan


class AlembicGenerator:
    """Path A: generate an Alembic revision file with SQL injected from a MigrationPlan."""

    def __init__(self, alembic_config: AlembicConfig) -> None:
        self._config = alembic_config

    def generate(self, plan: MigrationPlan, message: str) -> Path:
        """Generate an Alembic revision file with SQL from *plan*.

        Args:
            plan: MigrationPlan produced by MigrationPlanner.
            message: Human-readable message used as the revision description.

        Returns:
            Path to the newly created revision file.

        Raises:
            MigrationError: If Alembic fails to create the revision file.
        """
        from alembic import command as alembic_command
        from alembic.config import Config as AlembicCfgLoader

        from agent_migrate.exceptions import MigrationError

        versions_dir = self._config.version_locations
        before: set[str] = set()
        if versions_dir.exists():
            before = {f.name for f in versions_dir.iterdir() if f.suffix == ".py"}

        alembic_cfg = AlembicCfgLoader(str(self._config.ini_path))
        alembic_command.revision(alembic_cfg, message=message, autogenerate=False)

        after: set[str] = set()
        if versions_dir.exists():
            after = {f.name for f in versions_dir.iterdir() if f.suffix == ".py"}

        new_files = after - before
        if not new_files:
            raise MigrationError("Alembic did not create a new revision file.")

        new_file = versions_dir / sorted(new_files)[-1]
        _inject_sql(new_file, plan)
        return new_file


# ── Injection helpers ──────────────────────────────────────────────────────────


def _inject_sql(path: Path, plan: MigrationPlan) -> None:
    """Overwrite the upgrade/downgrade bodies in an Alembic revision file."""
    upgrade_body = _build_body(
        [step.sql for step in plan.steps]
    )
    downgrade_body = _build_body(
        [step.rollback_sql for step in reversed(plan.steps) if step.rollback_sql]
    )

    source = path.read_text(encoding="utf-8")
    source = _replace_body(source, "upgrade", upgrade_body)
    source = _replace_body(source, "downgrade", downgrade_body)
    path.write_text(source, encoding="utf-8")


def _build_body(sql_statements: list[str]) -> str:
    """Return an indented function body of op.execute(text(...)) calls."""
    if not sql_statements:
        return "    pass"
    lines = ["    from sqlalchemy import text", ""]
    for sql in sql_statements:
        lines.append(f"    op.execute(text({repr(sql)}))")
    return "\n".join(lines)


def _replace_body(source: str, func_name: str, body: str) -> str:
    """Replace the body of *func_name*() that currently contains only 'pass'."""
    pattern = rf"(def {re.escape(func_name)}\([^)]*\)[^:]*:)\s*\n[ \t]*pass"
    replacement = rf"\1\n{body}"
    return re.sub(pattern, replacement, source)
