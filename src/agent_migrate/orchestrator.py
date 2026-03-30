"""Orchestrator: coordinates all modules for CLI commands."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from sqlalchemy import Engine, create_engine

from agent_migrate.config import ConfigDetector, ModelDiscovery
from agent_migrate.diff import compute_diff
from agent_migrate.diff.engine import DiffEngine
from agent_migrate.diff.risk import RiskAnalyzer
from agent_migrate.exceptions import InspectorError
from agent_migrate.formatter import format_diff, format_plan, format_rls, format_snapshot
from agent_migrate.formatter.ref import RefEngine, RefMap
from agent_migrate.inspector import inspect_db
from agent_migrate.inspector.postgresql import PostgreSQLInspector
from agent_migrate.migration.planner import MigrationPlanner
from agent_migrate.parser import parse_models
from agent_migrate.rls import PresetResolver, SupabaseDetector

if TYPE_CHECKING:
    from pathlib import Path

    from agent_migrate.types import (
        DBRLSPolicy,
        DBRLSStatus,
        DBRoleInfo,
        DBTableSchema,
        DiffItem,
        MigrationPlan,
        ModelSchema,
    )


def _db_label(db_url: str) -> str:
    """Return a safe display label for the DB URL (no password)."""
    try:
        parsed = urlparse(db_url)
        host = parsed.hostname or "unknown"
        port = parsed.port or 5432
        db = (parsed.path or "/").lstrip("/") or "postgres"
        return f"PostgreSQL {host}:{port}/{db}"
    except Exception:  # noqa: BLE001
        return "PostgreSQL"


class _PipelineResult:
    """Holds the result of the common analysis pipeline."""

    __slots__ = (
        "models", "tables", "diffs", "ref_map", "engine", "db_url", "plan",
        "rls_statuses", "rls_policies", "roles", "grants",
        "rls_diffs", "role_diffs", "is_supabase",
    )

    def __init__(
        self,
        models: list[ModelSchema],
        tables: list[DBTableSchema],
        diffs: list[DiffItem],
        ref_map: RefMap,
        engine: Engine,
        db_url: str,
    ) -> None:
        self.models = models
        self.tables = tables
        self.diffs = diffs
        self.ref_map = ref_map
        self.engine = engine
        self.db_url = db_url
        self.plan: MigrationPlan | None = None
        self.rls_statuses: list[DBRLSStatus] = []
        self.rls_policies: list[DBRLSPolicy] = []
        self.roles: list[DBRoleInfo] = []
        self.grants: dict[str, list[tuple[str, str]]] = {}
        self.rls_diffs: list[DiffItem] = []
        self.role_diffs: list[DiffItem] = []
        self.is_supabase: bool = False


class Orchestrator:
    """Coordinates all modules for CLI commands.

    Pipeline:
      ConfigDetector → DB URL
      ModelDiscovery → model file paths
      parse_models   → list[ModelSchema]
      create_engine  → Engine
      inspect_db     → list[DBTableSchema]
      RefEngine      → RefMap
      compute_diff   → list[DiffItem]
      RiskAnalyzer   → enriched list[DiffItem]
      Formatter      → str
    """

    def __init__(self) -> None:
        self._config = ConfigDetector()
        self._discovery = ModelDiscovery()
        self._ref_engine = RefEngine()
        self._planner = MigrationPlanner()
        self._inspector = PostgreSQLInspector()
        self._diff_engine = DiffEngine()
        self._preset_resolver = PresetResolver()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _run_pipeline(
        self, project_root: Path, db_url_hint: str | None
    ) -> _PipelineResult:
        """Run the full analysis pipeline: detect → parse → inspect → diff → risk."""
        db_url = self._config.detect(project_root, db_url_hint)
        models = self._discovery.discover(project_root)
        model_schemas = parse_models(models)

        try:
            engine = create_engine(db_url)
            tables = inspect_db(engine)
        except Exception as exc:  # noqa: BLE001
            raise InspectorError(f"Cannot connect to database: {exc!s}") from exc

        ref_map = self._ref_engine.assign(model_schemas, tables)
        raw_diffs = compute_diff(model_schemas, tables)

        # RLS/ROLE inspection
        is_supabase = SupabaseDetector.is_supabase(db_url, engine)

        # Resolve __rls__ presets into RLSPolicySchema on models

        enriched_models = self._resolve_rls_on_models(
            model_schemas, is_supabase
        )

        rls_statuses, rls_policies = self._inspector.inspect_rls(engine)
        roles = self._inspector.inspect_roles(engine)
        grants = self._inspector.inspect_grants(engine)

        # RLS/ROLE diffs
        rls_diffs = self._diff_engine.compute_rls_diff(
            enriched_models, rls_statuses, rls_policies
        )
        role_reqs = [
            req
            for m in enriched_models
            for req in m.role_requirements
        ]
        role_diffs = self._diff_engine.compute_role_diff(role_reqs, roles, grants)

        # Merge all diffs and run risk analysis
        all_diffs = raw_diffs + rls_diffs + role_diffs
        diffs = RiskAnalyzer(engine=engine).analyze(all_diffs)

        result = _PipelineResult(
            models=enriched_models,
            tables=tables,
            diffs=diffs,
            ref_map=ref_map,
            engine=engine,
            db_url=db_url,
        )
        result.rls_statuses = rls_statuses
        result.rls_policies = rls_policies
        result.roles = roles
        result.grants = grants
        result.rls_diffs = rls_diffs
        result.role_diffs = role_diffs
        result.is_supabase = is_supabase
        return result

    def _resolve_rls_on_models(
        self,
        models: list[ModelSchema],
        is_supabase: bool,
    ) -> list[ModelSchema]:
        """Re-parse files to extract __rls__ dicts and resolve presets."""
        from pathlib import Path as _Path  # noqa: PLC0415

        from agent_migrate.parser.sqlalchemy import SQLAlchemyParser  # noqa: PLC0415
        from agent_migrate.types import ModelSchema as _MS  # noqa: PLC0415, N814, N817

        parser = SQLAlchemyParser()
        parsed_files: set[str] = set()
        for model in models:
            if model.source_file and model.source_file not in parsed_files:
                with contextlib.suppress(Exception):
                    parser.parse_file(_Path(model.source_file))
                parsed_files.add(model.source_file)

        enriched: list[ModelSchema] = []
        for model in models:
            rls_dict = parser._rls_raw.get(model.tablename)
            if rls_dict is not None:
                policies = tuple(
                    self._preset_resolver.resolve(
                        table_name=model.tablename,
                        rls_dict=rls_dict,
                        is_supabase=is_supabase,
                    )
                )
                enriched.append(
                    _MS(
                        name=model.name,
                        tablename=model.tablename,
                        columns=model.columns,
                        indexes=model.indexes,
                        source_file=model.source_file,
                        source_line=model.source_line,
                        rls_policies=policies,
                        rls_opt_out=model.rls_opt_out,
                        role_requirements=model.role_requirements,
                    )
                )
            else:
                enriched.append(model)
        return enriched

    # ── Public commands ───────────────────────────────────────────────────────

    def snapshot(self, project_root: Path, db_url: str | None = None) -> str:
        """Return formatted snapshot of models + DB state."""
        r = self._run_pipeline(project_root, db_url)
        return format_snapshot(
            models=r.models,
            tables=r.tables,
            diffs=r.diffs,
            ref_map=r.ref_map,
            db_name=_db_label(r.db_url),
        )

    def diff(self, project_root: Path, db_url: str | None = None) -> str:
        """Return formatted diff output."""
        r = self._run_pipeline(project_root, db_url)
        return format_diff(diffs=r.diffs, ref_map=r.ref_map)

    def plan(self, project_root: Path, db_url: str | None = None) -> str:
        """Return formatted migration plan with risk."""
        r = self._run_pipeline(project_root, db_url)
        migration_plan = self._planner.plan(r.diffs, r.models)
        return format_plan(plan=migration_plan, ref_map=r.ref_map)

    def generate(
        self,
        project_root: Path,
        message: str,
        db_url: str | None = None,
        fmt: str = "auto",
    ) -> Path:
        """Generate a migration file. Returns the created file path."""
        from agent_migrate.config import AlembicDetector  # noqa: PLC0415

        r = self._run_pipeline(project_root, db_url)
        migration_plan = self._planner.plan(r.diffs, r.models)

        alembic_cfg = AlembicDetector().detect(project_root)
        use_alembic = fmt == "alembic" or (fmt == "auto" and alembic_cfg is not None)

        if use_alembic and alembic_cfg is not None:
            from agent_migrate.migration.alembic_compat import AlembicGenerator  # noqa: PLC0415

            return AlembicGenerator(alembic_cfg).generate(migration_plan, message)

        from agent_migrate.migration.raw_sql import RawSQLGenerator  # noqa: PLC0415

        output_dir = project_root / "migrations"
        return RawSQLGenerator(output_dir).generate(migration_plan, message)

    def apply(
        self,
        project_root: Path,
        db_url: str | None = None,
        execute: bool = False,
        force: bool = False,
    ) -> str:
        """Apply (or dry-run) the migration. Returns a result summary."""
        from agent_migrate.migration.executor import MigrationExecutor  # noqa: PLC0415

        r = self._run_pipeline(project_root, db_url)
        migration_plan = self._planner.plan(r.diffs, r.models)

        executor = MigrationExecutor()

        if not execute:
            sql_lines = executor.dry_run(migration_plan)
            return "Dry-run (add --execute to apply):\n" + "\n".join(sql_lines)

        executor.execute(r.engine, migration_plan, force=force)
        return "Migration applied successfully."

    def rls(self, project_root: Path, db_url: str | None = None) -> str:
        """Return formatted RLS policy status."""
        r = self._run_pipeline(project_root, db_url)
        return format_rls(
            rls_statuses=r.rls_statuses,
            rls_policies=r.rls_policies,
            roles=r.roles,
        )

    def pipeline_result(
        self, project_root: Path, db_url: str | None = None
    ) -> _PipelineResult:
        """Return raw pipeline result for JSON/auto commands."""
        return self._run_pipeline(project_root, db_url)
