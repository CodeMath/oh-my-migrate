<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-31 | Updated: 2026-03-31 -->

# diff

## Purpose
Computes structural and security differences between model-defined schemas and live DB state. Enriches diffs with risk levels.

## Key Files
| File | Description |
|------|-------------|
| `engine.py` | `DiffEngine` — `compute_diff()`, `compute_rls_diff()`, `compute_role_diff()` |
| `risk.py` | `RiskAnalyzer` — assigns SAFE/CAUTION/DANGER to each DiffItem |
| `type_map.py` | `TypeMapper` — SQLAlchemy↔PostgreSQL type compatibility |
| `__init__.py` | Exports `compute_diff()` |

## For AI Agents

### DiffType Coverage (20 values)
Schema: TABLE_ADDED/REMOVED, COLUMN_ADDED/REMOVED/TYPE_CHANGED/NULLABLE_CHANGED/DEFAULT_CHANGED, ENUM_VALUES_CHANGED, FK_ADDED/REMOVED, INDEX_ADDED/REMOVED
RLS: RLS_ENABLED_CHANGED, RLS_POLICY_ADDED/REMOVED/CHANGED/UNTRACKED
Role: ROLE_MISSING, GRANT_ADDED/REMOVED

### Risk Rules
- **DANGER**: TABLE_REMOVED, COLUMN_REMOVED, RLS_ENABLED_CHANGED, RLS_POLICY_REMOVED/CHANGED, ROLE_MISSING, GRANT_REMOVED
- **CAUTION**: COLUMN_TYPE_CHANGED, RLS_POLICY_ADDED/UNTRACKED, GRANT_ADDED, fallthrough default
- **SAFE**: TABLE_ADDED, COLUMN_ADDED, FK/INDEX_ADDED

### Critical: Every new DiffType MUST have
1. Risk rule in `_compute_risk()` (risk.py)
2. Entry in `_DIFF_STYLE` (formatter/diff_fmt.py)
3. Entry in `_STEP_ORDER` (migration/planner.py)
4. Coverage in exhaustive tests

<!-- MANUAL: -->
