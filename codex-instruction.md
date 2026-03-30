# agent-migrate — Codex Integration Instructions

You have access to `agent-migrate`, a DB migration CLI for SQLAlchemy + PostgreSQL with RLS/ROLE support.

## When to Use

Use agent-migrate when:
- A SQLAlchemy model is modified and needs DB migration
- User asks about DB schema drift, differences, or sync status
- User mentions RLS policies, roles, or row-level security
- User says "migrate", "migration", "schema", "drift", "table change", "column add/remove"

## Primary Command

Always use `--json` for parseable output:

```bash
agent-migrate auto --json
```

## Decision Tree

1. Run `agent-migrate auto --json`
2. Parse the JSON:
   - `"in_sync": true` → Schema is synchronized, nothing to do
   - `"in_sync": false` → Check `"plan.overall_risk"`:
     - `"safe"` or `"caution"` → Confirm with user, then:
       ```bash
       agent-migrate auto --generate -m "description" --json
       agent-migrate auto --apply --execute -m "description" --json
       ```
     - `"danger"` → Show plan and risks, wait for explicit user approval with `--force`

## All Commands

| Command | Purpose |
|---------|---------|
| `agent-migrate auto --json` | **Primary**: drift detection + migration plan |
| `agent-migrate snapshot --json` | Current model + DB state |
| `agent-migrate diff --json` | Specific differences |
| `agent-migrate plan --json` | Migration SQL preview |
| `agent-migrate generate -m "msg" --json` | Create migration file |
| `agent-migrate apply --execute --json` | Apply migration |
| `agent-migrate rls --json` | RLS policy status |

## JSON Output Schema

Success:
```json
{
  "v": 1,
  "cmd": "auto",
  "drift_count": 1,
  "in_sync": false,
  "diffs": [{"type": "column_added", "tbl": "users", "col": "phone", "risk": "safe"}],
  "plan": {"steps": [{"sql": "ALTER TABLE ...", "risk": "safe"}], "overall_risk": "safe"}
}
```

Error:
```json
{"error": "CONFIG_NOT_FOUND", "message": "...", "hint": "Set DATABASE_URL or use --db-url"}
```

## Error Recovery

- `CONFIG_NOT_FOUND` → Ask user for DATABASE_URL or use `--db-url "postgresql://..."`
- `DB_CONNECTION` → Verify DB is running and accessible
- `PARSE_ERROR` → Check model file syntax
- `DANGEROUS_MIGRATION` → Requires `--force` flag after user confirmation

## RLS Support

Models declare RLS via `__rls__`:
```python
class Post(Base):
    __tablename__ = "posts"
    __rls__ = {"select": "owner", "insert": "authenticated"}
```

Presets: `owner`, `public_read`, `authenticated`, `admin_only`, `team`
Opt-out: `__rls__ = False`

Use `agent-migrate rls --json` to check current RLS status.

## Risk Levels

- **safe**: Additive changes (add column, add table). Auto-apply OK.
- **caution**: Type changes, RLS policy additions. Confirm with user.
- **danger**: Drops, RLS removals, data loss risk. Requires `--force` and explicit approval.
