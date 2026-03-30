<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-31 | Updated: 2026-03-31 -->

# tests

## Purpose
Pytest test suite — 210 tests covering parser, diff engine, risk analyzer, migration planner, formatters, RLS presets, and CLI integration.

## Key Files
| File | Description |
|------|-------------|
| `conftest.py` | Shared fixtures (PostgresContainer for integration tests) |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `test_parser/` | SQLAlchemy/SQLModel parser tests + __rls__ parsing |
| `test_diff/` | Diff engine + risk analyzer tests |
| `test_formatter/` | Snapshot, diff, plan, JSON formatter tests |
| `test_migration/` | Planner, executor, raw SQL tests |
| `test_inspector/` | PostgreSQL inspector tests (requires DB) |
| `test_cli/` | CLI command tests |
| `test_integration/` | End-to-end integration tests |
| `test_rls/` | RLS preset, resolver, diff, risk tests |

## For AI Agents

### Running Tests
```bash
.venv/bin/python -m pytest tests/ -q --tb=short
```

### Test Categories
- **Unit tests** (no DB): test_parser, test_diff, test_formatter, test_migration, test_rls
- **Integration tests** (need PostgreSQL): test_inspector, test_integration
- Integration tests use `testcontainers[postgres]` — auto-start Docker PG

### Adding Tests
- Mirror source structure: `src/agent_migrate/X.py` → `tests/test_X/`
- Use `@dataclass(frozen=True)` test data — match source patterns
- Exhaustive DiffType coverage: every new DiffType must appear in `test_all_diff_types_have_*` tests

<!-- MANUAL: -->
