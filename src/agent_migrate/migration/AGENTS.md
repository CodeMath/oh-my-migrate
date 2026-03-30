<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-31 | Updated: 2026-03-31 -->

# migration

## Purpose
Converts DiffItems into ordered SQL migration steps, generates migration files (Alembic or raw SQL), and executes them with safety checks.

## Key Files
| File | Description |
|------|-------------|
| `planner.py` | `MigrationPlanner` — DiffItem → MigrationStep with `_STEP_ORDER` (20 entries) |
| `executor.py` | `MigrationExecutor` — dry-run and execute with DANGER guard |
| `raw_sql.py` | `RawSQLGenerator` — timestamped .sql files |
| `alembic_compat.py` | `AlembicGenerator` — Alembic revision files |
| `version_table.py` | Migration version tracking |
| `__init__.py` | Package init |

## For AI Agents

### Step Order
Schema steps (0-11) → RLS steps (12-15) → Role/Grant steps (16-18). `RLS_POLICY_UNTRACKED = -1` (informational, no SQL generated).

### SQL Generation
- All identifiers double-quoted via `_qi()`
- String literals single-quoted via `_ql()`
- RLS: CREATE/DROP POLICY, ENABLE/DISABLE ROW LEVEL SECURITY, GRANT/REVOKE
- Rollback SQL provided for all additive steps

<!-- MANUAL: -->
