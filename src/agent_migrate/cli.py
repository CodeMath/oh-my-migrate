"""CLI entry point for agent-migrate."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from agent_migrate.exceptions import (
    AgentMigrateError,
    ConfigNotFoundError,
    DangerousMigrationError,
    InspectorError,
    ParseError,
)
from agent_migrate.orchestrator import Orchestrator

app = typer.Typer(
    name="agent-migrate",
    help="AI-agent-optimized DB migration CLI for SQLAlchemy + PostgreSQL.",
    no_args_is_help=True,
)

console = Console()
err_console = Console(stderr=True)

_orchestrator = Orchestrator()


def _error_code(exc: Exception) -> str:
    if isinstance(exc, ConfigNotFoundError):
        return "CONFIG_NOT_FOUND"
    if isinstance(exc, ParseError):
        return "PARSE_ERROR"
    if isinstance(exc, InspectorError):
        return "DB_CONNECTION"
    if isinstance(exc, DangerousMigrationError):
        return "DANGEROUS_MIGRATION"
    if isinstance(exc, AgentMigrateError):
        return "AGENT_MIGRATE"
    return "UNEXPECTED"


def _error_hint(exc: Exception) -> str:
    if isinstance(exc, ConfigNotFoundError):
        return "Set DATABASE_URL env var, use --db-url, or add to .env / alembic.ini"
    if isinstance(exc, ParseError):
        return "Check the model file for syntax errors"
    if isinstance(exc, InspectorError):
        return "Verify DB is running and DATABASE_URL is correct"
    if isinstance(exc, DangerousMigrationError):
        return "Use --force to apply dangerous migrations"
    return "Run with --help for usage information"


def _handle_error(exc: Exception, *, use_json: bool = False) -> None:
    """Print a token-efficient error message and exit 1."""
    if use_json:
        print(json.dumps({  # noqa: T201
            "error": _error_code(exc),
            "message": str(exc),
            "hint": _error_hint(exc),
        }))
    else:
        err_console.print(f"Error: [{_error_code(exc)}] {exc}")
        err_console.print(f"Hint: {_error_hint(exc)}")
    raise typer.Exit(code=1)


@app.command()
def snapshot(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Project root path"),
    db_url: str | None = typer.Option(
        None, "--db-url", help="Database URL (auto-detected if omitted)"
    ),
    use_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show current model + DB state (agent-friendly format)."""
    try:
        if use_json:
            from agent_migrate.formatter import json_snapshot  # noqa: PLC0415
            from agent_migrate.orchestrator import _db_label  # noqa: PLC0415

            r = _orchestrator.pipeline_result(path.resolve(), db_url)
            print(json_snapshot(r.models, r.tables, r.diffs, r.ref_map, _db_label(r.db_url)))  # noqa: T201
        else:
            result = _orchestrator.snapshot(path.resolve(), db_url)
            console.print(result)
    except (AgentMigrateError, Exception) as exc:
        _handle_error(exc, use_json=use_json)


@app.command()
def diff(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Project root path"),
    db_url: str | None = typer.Option(None, "--db-url", help="Database URL"),
    use_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show differences between models and DB."""
    try:
        if use_json:
            from agent_migrate.formatter import json_diff  # noqa: PLC0415

            r = _orchestrator.pipeline_result(path.resolve(), db_url)
            print(json_diff(r.diffs, r.ref_map))  # noqa: T201
        else:
            result = _orchestrator.diff(path.resolve(), db_url)
            console.print(result)
    except (AgentMigrateError, Exception) as exc:
        _handle_error(exc, use_json=use_json)


@app.command()
def plan(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Project root path"),
    db_url: str | None = typer.Option(None, "--db-url", help="Database URL"),
    use_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show migration plan with risk analysis."""
    try:
        if use_json:
            from agent_migrate.formatter import json_plan  # noqa: PLC0415
            from agent_migrate.migration.planner import MigrationPlanner  # noqa: PLC0415

            r = _orchestrator.pipeline_result(path.resolve(), db_url)
            migration_plan = MigrationPlanner().plan(r.diffs, r.models)
            print(json_plan(migration_plan, r.ref_map))  # noqa: T201
        else:
            result = _orchestrator.plan(path.resolve(), db_url)
            console.print(result)
    except (AgentMigrateError, Exception) as exc:
        _handle_error(exc, use_json=use_json)


@app.command()
def generate(
    message: str = typer.Option(..., "-m", "--message", help="Migration description"),
    path: Path = typer.Option(Path("."), "--path", "-p", help="Project root path"),
    db_url: str | None = typer.Option(None, "--db-url", help="Database URL"),
    format: str = typer.Option(
        "auto", "--format", help="Output format: auto, alembic, or sql"
    ),
    use_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate a migration file."""
    try:
        file_path = _orchestrator.generate(path.resolve(), message, db_url, format)
        if use_json:
            print(json.dumps({"generated": str(file_path)}))  # noqa: T201
        else:
            console.print(f"Generated: {file_path}")
    except (AgentMigrateError, Exception) as exc:
        _handle_error(exc, use_json=use_json)


@app.command()
def apply(
    execute: bool = typer.Option(
        False, "--execute", help="Actually apply (default is dry-run)"
    ),
    force: bool = typer.Option(
        False, "--force", help="Allow DANGER migrations"
    ),
    path: Path = typer.Option(Path("."), "--path", "-p", help="Project root path"),
    db_url: str | None = typer.Option(None, "--db-url", help="Database URL"),
    use_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Apply migration (dry-run by default; use --execute to apply)."""
    try:
        result = _orchestrator.apply(path.resolve(), db_url, execute=execute, force=force)
        if use_json:
            print(json.dumps({"result": result}))  # noqa: T201
        else:
            console.print(result)
    except (AgentMigrateError, Exception) as exc:
        _handle_error(exc, use_json=use_json)


@app.command()
def rls(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Project root path"),
    db_url: str | None = typer.Option(None, "--db-url", help="Database URL"),
    use_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show RLS policy status for all tables."""
    try:
        if use_json:
            from agent_migrate.formatter import json_rls  # noqa: PLC0415

            r = _orchestrator.pipeline_result(path.resolve(), db_url)
            print(json_rls(r.rls_statuses, r.rls_policies, r.roles))  # noqa: T201
        else:
            result = _orchestrator.rls(path.resolve(), db_url)
            console.print(result)
    except (AgentMigrateError, Exception) as exc:
        _handle_error(exc, use_json=use_json)


@app.command()
def auto(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Project root path"),
    db_url: str | None = typer.Option(None, "--db-url", help="Database URL"),
    use_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    do_generate: bool = typer.Option(False, "--generate", help="Also generate migration"),
    message: str | None = typer.Option(None, "-m", "--message", help="Migration message"),
    do_apply: bool = typer.Option(False, "--apply", help="Also apply migration"),
    execute: bool = typer.Option(False, "--execute", help="Execute (not dry-run)"),
    force: bool = typer.Option(False, "--force", help="Allow DANGER migrations"),
) -> None:
    """One-step: detect drift, show plan, optionally generate+apply."""
    try:
        from agent_migrate.formatter import (  # noqa: PLC0415
            format_diff,
            format_plan,
            json_auto,
        )
        from agent_migrate.migration.planner import MigrationPlanner  # noqa: PLC0415
        from agent_migrate.orchestrator import _db_label  # noqa: PLC0415

        r = _orchestrator.pipeline_result(path.resolve(), db_url)
        migration_plan = MigrationPlanner().plan(r.diffs, r.models) if r.diffs else None

        generated_file: str | None = None
        applied = False

        if do_generate and r.diffs:
            msg = message or "auto-generated migration"
            file_path = _orchestrator.generate(path.resolve(), msg, db_url)
            generated_file = str(file_path)

        if do_apply and r.diffs:
            msg = message or "auto-generated migration"
            _orchestrator.apply(path.resolve(), db_url, execute=execute, force=force)
            applied = execute

        if use_json:
            print(json_auto(  # noqa: T201
                r.models, r.tables, r.diffs, migration_plan,
                r.ref_map, _db_label(r.db_url), generated_file, applied,
            ))
        else:
            if not r.diffs:
                console.print("No drift detected. Schema in sync.")
            else:
                console.print(f"Auto-detect: {len(r.diffs)} difference(s) found\n")
                console.print(format_diff(diffs=r.diffs, ref_map=r.ref_map))
                if migration_plan:
                    console.print("")
                    console.print(format_plan(plan=migration_plan, ref_map=r.ref_map))
                if generated_file:
                    console.print(f"\nGenerated: {generated_file}")
                if applied:
                    console.print("Migration applied successfully.")
                elif not do_generate:
                    console.print(
                        "\nRun: agent-migrate auto --generate -m \"description\" "
                        "to create migration"
                    )
    except (AgentMigrateError, Exception) as exc:
        _handle_error(exc, use_json=use_json)


if __name__ == "__main__":
    app()
