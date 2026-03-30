<!-- Generated: 2026-03-31 | Updated: 2026-03-31 -->

# agent-migrate

## Purpose
AI-agent-optimized DB migration CLI for SQLAlchemy/SQLModel + PostgreSQL. Detects schema drift between Python ORM models and a live database, generates migration plans with risk analysis, and supports RLS policy management with Supabase-first presets.

## Key Files
| File | Description |
|------|-------------|
| `pyproject.toml` | Package config, dependencies, tool settings |
| `codex-instruction.md` | OpenAI Codex integration instructions |
| `project.md` | Project technical document (Korean) |
| `v0.0.1-prd.md` | Phase 1 product requirements |
| `example_skill.md` | Example skill usage flow |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `src/` | Application source code (see `src/AGENTS.md`) |
| `tests/` | Test suites — 210 tests (see `tests/AGENTS.md`) |
| `examples/` | Example projects (see `examples/AGENTS.md`) |
| `fixtures/` | Test fixture projects (see `fixtures/AGENTS.md`) |
| `.claude/` | Claude Code skill definition |

## For AI Agents

### Working In This Directory
- Use `uv` for dependency management (`.venv/bin/python`)
- All source under `src/agent_migrate/` (hatchling build)
- Run `agent-migrate auto --json` as primary entry point

### Testing Requirements
- `pytest`: `.venv/bin/python -m pytest tests/ -q`
- `ruff`: `.venv/bin/ruff check src/agent_migrate/`
- `mypy`: `.venv/bin/mypy src/agent_migrate/ --strict`
- All 3 must pass before completion

### Architecture
```
CLI (typer) → Orchestrator._run_pipeline()
  → ConfigDetector   → db_url
  → ModelDiscovery   → list[Path]
  → parse_models()   → list[ModelSchema]  (SQLAlchemy + SQLModel)
  → inspect_db()     → list[DBTableSchema]
  → inspect_rls()    → RLS statuses + policies
  → compute_diff()   → list[DiffItem]  (schema + RLS + ROLE)
  → RiskAnalyzer     → enriched diffs
  → Formatter        → text or JSON output
```

### Key Principles
- **Additive-Only**: Extend, don't modify existing interfaces
- **Frozen Dataclasses**: All types are `@dataclass(frozen=True)` with `tuple[X, ...]`
- **AST-Only Parsing**: No runtime model imports — pure `ast` module
- **Security-as-Data**: RLS policies and roles are first-class data types

## Dependencies

### External
- `sqlalchemy>=2.0` — DB engine, inspection
- `typer>=0.12` — CLI framework
- `rich>=13.0` — Terminal formatting
- `psycopg[binary]>=3.1` — PostgreSQL driver
- `alembic>=1.13` — Migration file compatibility

<!-- MANUAL: -->
