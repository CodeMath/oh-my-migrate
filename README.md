# agent-migrate

AI-agent-optimized DB migration CLI for **SQLAlchemy / SQLModel + PostgreSQL**.

Schema drift detection, migration generation, RLS policy management — designed for AI coding agents (Claude Code, Codex) with `--json` output.

## One-Line Install

```bash
curl -fsSL https://raw.githubusercontent.com/CodeMath/oh-my-migrate/main/install.sh | bash
```

This installs:
- `agent-migrate` CLI (pip/uv)
- Claude Code skill (`~/.claude/skills/agent-migrate/SKILL.md`)

With Codex support:
```bash
curl -fsSL https://raw.githubusercontent.com/CodeMath/oh-my-migrate/main/install.sh | bash -s -- --codex
```

### Manual Install

```bash
pip install git+https://github.com/CodeMath/oh-my-migrate.git
```

## Quick Start

```bash
# Detect drift between models and DB
agent-migrate auto --json

# Generate migration
agent-migrate auto --generate -m "add user phone field" --json

# Apply migration
agent-migrate auto --apply --execute -m "add user phone field" --json

# Check RLS policies
agent-migrate rls --json
```

## Commands

| Command | Purpose |
|---------|---------|
| `agent-migrate auto` | **Primary** — drift detection + plan in one step |
| `agent-migrate snapshot` | Current model + DB state |
| `agent-migrate diff` | Schema + RLS differences |
| `agent-migrate plan` | Migration SQL with risk analysis |
| `agent-migrate generate -m "msg"` | Create migration file (Alembic or raw SQL) |
| `agent-migrate apply --execute` | Apply migration (dry-run by default) |
| `agent-migrate rls` | RLS policy status per table |

All commands support `--json` for agent-parseable output and `--db-url` for explicit DB connection.

## Supported ORMs

| ORM | Pattern | Status |
|-----|---------|--------|
| SQLAlchemy 2.0 | `Mapped[T] = mapped_column(...)` | ✅ |
| SQLAlchemy Classic | `name = Column(Type, ...)` | ✅ |
| SQLModel | `name: str = Field(...)` with `table=True` | ✅ |

## RLS Policy Management

Declare RLS policies directly on models:

```python
class Post(Base):
    __tablename__ = "posts"
    __rls__ = {
        "select": "owner",           # auth.uid() = user_id (Supabase)
        "insert": "authenticated",    # role = authenticated
        "update": "owner",
        "delete": "admin_only",       # service_role only
    }
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column()
```

Opt out explicitly:
```python
class AuditLog(Base):
    __tablename__ = "audit_logs"
    __rls__ = False  # excluded from RLS drift detection
```

### Presets

| Preset | Supabase | PostgreSQL Native |
|--------|----------|-------------------|
| `owner` | `auth.uid() = user_id` | `current_user = user_id` |
| `public_read` | `true` | `true` |
| `authenticated` | `auth.role() = 'authenticated'` | `session_user IS NOT NULL` |
| `admin_only` | `auth.role() = 'service_role'` | `current_setting('app.admin_role')` |
| `team` | `auth.uid() IN (subquery)` | — |

Supabase is auto-detected by URL pattern + `pg_roles` check. Non-Supabase environments use PostgreSQL-native presets automatically.

## Risk Analysis

Every diff gets a risk level:

| Risk | Meaning | Examples |
|------|---------|----------|
| **SAFE** | Additive, no data loss | Add column, add table |
| **CAUTION** | Needs review | Type change, RLS policy add |
| **DANGER** | Potential data loss or security impact | Drop column, RLS removal |

DANGER migrations require `--force` to apply.

## JSON Output

All `--json` output follows a compact schema:

```json
{
  "v": 1,
  "cmd": "auto",
  "drift_count": 2,
  "in_sync": false,
  "diffs": [
    {"type": "column_added", "tbl": "users", "col": "phone", "risk": "safe"},
    {"type": "rls_policy_added", "tbl": "posts", "model_val": "posts_select_owner", "risk": "caution"}
  ],
  "plan": {
    "steps": [
      {"sql": "ALTER TABLE \"users\" ADD COLUMN \"phone\" TEXT;", "risk": "safe"},
      {"sql": "CREATE POLICY \"posts_select_owner\" ON \"posts\" ...", "risk": "caution"}
    ],
    "overall_risk": "caution",
    "step_count": 2
  }
}
```

## AI Agent Integration

### Claude Code

Installed automatically via the install script. The skill triggers on keywords like `migrate`, `마이그레이션`, `RLS`, `schema`, `drift`.

**Manual install:**
```bash
mkdir -p ~/.claude/skills/agent-migrate
curl -fsSL https://raw.githubusercontent.com/CodeMath/oh-my-migrate/main/.claude/skills/agent-migrate/SKILL.md \
  -o ~/.claude/skills/agent-migrate/SKILL.md
```

### OpenAI Codex

```bash
mkdir -p ~/.codex
curl -fsSL https://raw.githubusercontent.com/CodeMath/oh-my-migrate/main/codex-instruction.md \
  -o ~/.codex/agent-migrate-instruction.md
```

Then add to your Codex system prompt or instruction file.

### Agent Decision Tree

```
1. agent-migrate auto --json
2. if "in_sync": true → done
3. if "overall_risk": "safe"/"caution" → generate + apply (with user confirmation)
4. if "overall_risk": "danger" → show plan, wait for explicit --force approval
```

## Development

```bash
git clone https://github.com/CodeMath/oh-my-migrate.git
cd oh-my-migrate
uv sync --all-extras

# Run tests (210 tests)
.venv/bin/python -m pytest tests/ -q

# Lint + type check
.venv/bin/ruff check src/agent_migrate/
.venv/bin/mypy src/agent_migrate/ --strict
```

## Architecture

```
CLI (typer) → Orchestrator._run_pipeline()
  → ConfigDetector    → db_url (env, .env, alembic.ini, pyproject.toml)
  → ModelDiscovery    → list[Path]
  → parse_models()    → list[ModelSchema]  (SQLAlchemy + SQLModel, AST-only)
  → inspect_db()      → list[DBTableSchema]
  → inspect_rls()     → RLS statuses + policies + roles
  → compute_diff()    → list[DiffItem]  (20 DiffTypes: schema + RLS + ROLE)
  → RiskAnalyzer      → SAFE / CAUTION / DANGER per diff
  → Formatter         → text (@m1/@d1 refs) or JSON output
```

## License

Apache-2.0
