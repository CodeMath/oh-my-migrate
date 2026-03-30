<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-31 | Updated: 2026-03-31 -->

# inspector

## Purpose
PostgreSQL schema inspection using information_schema and pg_catalog queries. Returns typed dataclasses for tables, columns, RLS, roles, and grants.

## Key Files
| File | Description |
|------|-------------|
| `postgresql.py` | `PostgreSQLInspector` — inspect(), inspect_rls(), inspect_roles(), inspect_grants() |
| `base.py` | `DBInspector` protocol |
| `__init__.py` | Exports `inspect_db()` |

## For AI Agents

### Query Sources
- `information_schema.columns` + `table_constraints` → columns, PK, FK, UNIQUE
- `pg_class.reltuples` → approximate row counts
- `pg_class.relrowsecurity/relforcerowsecurity` → RLS status
- `pg_policies` → RLS policies (PostgreSQL 10+, graceful fallback)
- `pg_roles` + `role_table_grants` → roles and grants

### All queries use `sqlalchemy.text()` with bound parameters — no f-string SQL.

<!-- MANUAL: -->
