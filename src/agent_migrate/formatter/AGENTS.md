<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-31 | Updated: 2026-03-31 -->

# formatter

## Purpose
Agent-optimized output formatters. Text mode uses `@m1/@d1` ref system for token efficiency (<500 tokens). JSON mode for machine parsing.

## Key Files
| File | Description |
|------|-------------|
| `snapshot_fmt.py` | `format_snapshot()` — models + DB + drift in text |
| `diff_fmt.py` | `format_diff()` — one-line-per-diff with `_DIFF_STYLE` symbols |
| `plan_fmt.py` | `format_plan()` — numbered SQL steps with risk |
| `rls_fmt.py` | `format_rls()` — RLS status per table |
| `json_fmt.py` | `json_snapshot/diff/plan/rls/auto()` — compact JSON output |
| `ref.py` | `RefEngine` + `RefMap` — `@m1`/`@d1` reference assignment |
| `__init__.py` | Re-exports all formatters |

## For AI Agents

### _DIFF_STYLE must cover all 20 DiffTypes
Every DiffType needs: symbol in `_DIFF_STYLE` (diff_fmt.py), case in `_fmt_drift_line` (snapshot_fmt.py), case in `_short_desc` (diff_fmt.py).

### JSON output keys are compact
`tbl` not `table_name`, `cols` not `columns`, `desc` not `description` — keeps output under 500 tokens.

<!-- MANUAL: -->
