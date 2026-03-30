<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-31 | Updated: 2026-03-31 -->

# agent_migrate

## Purpose
Core package for agent-migrate. Orchestrates the full pipeline: config detection → model parsing → DB inspection → diff computation → risk analysis → migration planning → formatting.

## Key Files
| File | Description |
|------|-------------|
| `cli.py` | Typer CLI — 7 commands: snapshot, diff, plan, generate, apply, rls, auto |
| `orchestrator.py` | Pipeline coordinator — `_run_pipeline()` wires all modules |
| `config.py` | ConfigDetector (DB URL), ModelDiscovery (file scanner), AlembicDetector |
| `types.py` | All frozen dataclasses: ModelSchema, DBTableSchema, DiffItem, RLSPolicySchema, etc. |
| `exceptions.py` | Error hierarchy: ConfigNotFoundError, ParseError, ConfigError, etc. |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `parser/` | AST-based model parsing — SQLAlchemy + SQLModel (see `parser/AGENTS.md`) |
| `inspector/` | PostgreSQL schema inspection via information_schema (see `inspector/AGENTS.md`) |
| `diff/` | Schema + RLS diff engine and risk analyzer (see `diff/AGENTS.md`) |
| `migration/` | SQL generation, Alembic compat, executor (see `migration/AGENTS.md`) |
| `formatter/` | Text + JSON output formatters (see `formatter/AGENTS.md`) |
| `rls/` | RLS preset system — Supabase/PG dual presets (see `rls/AGENTS.md`) |

## For AI Agents

### Type System
All data flows through frozen dataclasses in `types.py`:
- **Parser output**: `ModelSchema` (with `rls_policies`, `rls_opt_out`)
- **Inspector output**: `DBTableSchema`, `DBRLSStatus`, `DBRLSPolicy`, `DBRoleInfo`
- **Diff output**: `DiffItem` (20 DiffType values, 3 RiskLevel values)
- **Plan output**: `MigrationPlan` → `MigrationStep`

### Adding a New Feature
1. Add types to `types.py` (frozen, with defaults for backward compat)
2. Extend relevant module (parser/inspector/diff/planner/formatter)
3. Wire through `orchestrator.py._run_pipeline()`
4. Add exhaustive DiffType tests if new DiffTypes added
5. Verify: pytest + ruff + mypy strict

### CLI Commands
| Command | Entry Point |
|---------|-------------|
| `auto --json` | Primary agent entry point — combines all steps |
| `snapshot` | models + DB state |
| `diff` | schema + RLS differences |
| `plan` | migration SQL with risk |
| `generate` | create migration file |
| `apply` | execute migration |
| `rls` | RLS policy status |

<!-- MANUAL: -->
