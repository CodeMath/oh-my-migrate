<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-31 | Updated: 2026-03-31 -->

# rls

## Purpose
RLS (Row Level Security) preset system with dual Supabase/PostgreSQL support. Resolves `__rls__` model annotations into full `RLSPolicySchema` instances.

## Key Files
| File | Description |
|------|-------------|
| `presets.py` | `SUPABASE_PRESETS` (5) + `PG_NATIVE_PRESETS` (4) + `RLSPreset` dataclass |
| `supabase.py` | `SupabaseDetector` — 2-stage detection (URL regex + pg_roles) |
| `resolver.py` | `PresetResolver` — key validation, supabase guard, policy naming |
| `__init__.py` | Re-exports |

## For AI Agents

### Preset Names
| Preset | Supabase | PG Native |
|--------|----------|-----------|
| `owner` | `auth.uid() = {col}` | `current_user = {col}` |
| `public_read` | `true` | `true` |
| `authenticated` | `auth.role() = 'authenticated'` | `session_user IS NOT NULL` |
| `admin_only` | `auth.role() = 'service_role'` | `current_setting('app.admin_role')` |
| `team` | `auth.uid() IN (subquery)` | N/A |

### Policy Naming: `{table}_{command}_{preset}` (e.g. `posts_select_owner`)
### Key Validation: only `select`, `insert`, `update`, `delete`, `all` allowed
### `all` expands to 4 individual policies (SELECT, INSERT, UPDATE, DELETE)

<!-- MANUAL: -->
