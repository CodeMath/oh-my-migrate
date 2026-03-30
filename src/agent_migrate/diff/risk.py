"""Risk analyzer: enriches DiffItems with risk assessments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

from agent_migrate.types import DiffItem, DiffType, RiskLevel


def _quote_ident(name: str) -> str:
    """Double-quote a SQL identifier, escaping internal double quotes."""
    return '"' + name.replace('"', '""') + '"'

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


class RiskAnalyzer:
    """Analyzes risk for each DiffItem and returns enriched DiffItems."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine

    def analyze(self, diffs: list[DiffItem]) -> list[DiffItem]:
        """Return diffs with risk field populated."""
        return [self._assess(diff) for diff in diffs]

    def _assess(self, diff: DiffItem) -> DiffItem:
        risk, description, affected_rows = self._compute_risk(diff)
        return DiffItem(
            diff_type=diff.diff_type,
            table_name=diff.table_name,
            column_name=diff.column_name,
            risk=risk,
            description=description or diff.description,
            model_value=diff.model_value,
            db_value=diff.db_value,
            affected_rows=affected_rows,
        )

    def _compute_risk(
        self, diff: DiffItem
    ) -> tuple[RiskLevel, str, int | None]:
        dt = diff.diff_type

        if dt == DiffType.TABLE_REMOVED:
            rows = self._get_row_count(diff.table_name)
            return (
                RiskLevel.DANGER,
                f"Dropping table {diff.table_name!r} ({rows} rows)",
                rows,
            )

        if dt == DiffType.COLUMN_REMOVED:
            rows = self._get_row_count(diff.table_name)
            return (
                RiskLevel.DANGER,
                f"Dropping column {diff.column_name!r} from {diff.table_name!r} ({rows} rows)",
                rows,
            )

        if dt == DiffType.COLUMN_ADDED:
            if "not_null_no_default" in diff.description:
                return (
                    RiskLevel.CAUTION,
                    f"Adding NOT NULL column {diff.column_name!r} "
                    "without default requires backfill",
                    None,
                )
            return (RiskLevel.SAFE, diff.description, None)

        if dt == DiffType.COLUMN_NULLABLE_CHANGED:
            # nullable=True -> False is risky
            model_val = diff.model_value or ""
            db_val = diff.db_value or ""
            if db_val == "True" and model_val == "False":
                # DB is nullable, model wants NOT NULL — check for NULLs
                rows = self._get_null_count(diff.table_name, diff.column_name or "")
                if rows and rows > 0:
                    return (
                        RiskLevel.DANGER,
                        f"Column {diff.column_name!r} has {rows} NULL values; "
                        "cannot set NOT NULL",
                        rows,
                    )
                return (
                    RiskLevel.CAUTION,
                    f"Setting {diff.column_name!r} NOT NULL (no NULLs found)",
                    0,
                )
            return (RiskLevel.SAFE, diff.description, None)

        if dt == DiffType.COLUMN_TYPE_CHANGED:
            return (
                RiskLevel.CAUTION,
                f"Type change on {diff.column_name!r}: {diff.db_value!r} -> "
                f"{diff.model_value!r}; verify data compatibility",
                None,
            )

        if dt == DiffType.ENUM_VALUES_CHANGED:
            model_vals = set((diff.model_value or "").split(","))
            db_vals = set((diff.db_value or "").split(","))
            if db_vals - model_vals:
                # Values removed
                return (
                    RiskLevel.DANGER,
                    f"Enum values removed from {diff.column_name!r}: "
                    f"{db_vals - model_vals}",
                    None,
                )
            return (
                RiskLevel.CAUTION,
                f"Enum values added to {diff.column_name!r}: {model_vals - db_vals}",
                None,
            )

        if dt == DiffType.TABLE_ADDED:
            return (RiskLevel.SAFE, diff.description, None)

        if dt in (DiffType.FK_ADDED, DiffType.INDEX_ADDED):
            return (RiskLevel.SAFE, diff.description, None)

        if dt in (DiffType.FK_REMOVED, DiffType.INDEX_REMOVED):
            return (RiskLevel.CAUTION, diff.description, None)

        if dt == DiffType.RLS_ENABLED_CHANGED:
            return (RiskLevel.DANGER, "RLS disabled in DB but required by model", None)

        if dt == DiffType.RLS_POLICY_ADDED:
            return (RiskLevel.CAUTION, f"New RLS policy: {diff.model_value}", None)

        if dt == DiffType.RLS_POLICY_REMOVED:
            return (RiskLevel.DANGER, f"Removing RLS policy: {diff.model_value}", None)

        if dt == DiffType.RLS_POLICY_CHANGED:
            return (RiskLevel.DANGER, f"Modifying RLS policy: {diff.model_value}", None)

        if dt == DiffType.RLS_POLICY_UNTRACKED:
            return (
                RiskLevel.CAUTION,
                "DB has RLS policy not managed by agent-migrate",
                None,
            )

        if dt == DiffType.ROLE_MISSING:
            return (RiskLevel.DANGER, f"Required role missing: {diff.model_value}", None)

        if dt == DiffType.GRANT_ADDED:
            return (RiskLevel.CAUTION, f"New grant: {diff.model_value}", None)

        if dt == DiffType.GRANT_REMOVED:
            return (RiskLevel.DANGER, f"Revoking grant: {diff.db_value}", None)

        # Fallthrough: unknown DiffType gets CAUTION (security-conservative)
        return (RiskLevel.CAUTION, diff.description, None)

    def _get_row_count(self, table_name: str) -> int:
        if self._engine is None:
            return 0
        with self._engine.connect() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) FROM " + _quote_ident(table_name))  # noqa: S608
            )
            row = result.fetchone()
            return int(row[0]) if row else 0

    def _get_null_count(self, table_name: str, column_name: str) -> int:
        if self._engine is None:
            return 0
        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM "  # noqa: S608
                    + _quote_ident(table_name)
                    + " WHERE "
                    + _quote_ident(column_name)
                    + " IS NULL"
                )
            )
            row = result.fetchone()
            return int(row[0]) if row else 0
