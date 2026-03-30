"""Migration executor: dry-run preview and live transactional execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

from agent_migrate.exceptions import DangerousMigrationError
from agent_migrate.types import RiskLevel

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from agent_migrate.types import MigrationPlan


class MigrationExecutor:
    """Execute a MigrationPlan against a live PostgreSQL database.

    Usage::

        executor = MigrationExecutor()

        # Preview only — no DB changes
        sql_list = executor.dry_run(plan)

        # Apply for real (requires --force for DANGER steps)
        executor.execute(engine, plan, force=True)
    """

    def dry_run(self, plan: MigrationPlan) -> list[str]:
        """Return the SQL statements that *would* be executed, without touching the DB."""
        return [step.sql for step in plan.steps]

    def execute(
        self,
        engine: Engine,
        plan: MigrationPlan,
        *,
        force: bool = False,
    ) -> None:
        """Apply all migration steps inside a single transaction.

        Args:
            engine: SQLAlchemy engine connected to the target database.
            plan: The MigrationPlan to execute.
            force: Must be True to allow DANGER-level steps to run.

        Raises:
            DangerousMigrationError: If the plan contains DANGER steps and *force* is False.
        """
        if plan.overall_risk == RiskLevel.DANGER and not force:
            danger_steps = [s for s in plan.steps if s.risk == RiskLevel.DANGER]
            descriptions = "; ".join(s.description for s in danger_steps)
            raise DangerousMigrationError(
                f"Plan contains DANGER-level steps: {descriptions}. "
                "Re-run with --force to proceed."
            )

        with engine.begin() as conn:
            for step in plan.steps:
                conn.execute(text(step.sql))
