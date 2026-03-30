---
name: agent-migrate
description: |
  SQLAlchemy/SQLModel + PostgreSQL DB 마이그레이션을 자동으로 관리합니다.
  모델 변경 감지, RLS 정책 관리, 마이그레이션 생성 및 적용을 수행합니다.
---

# agent-migrate Skill

DB migration management for SQLAlchemy/SQLModel + PostgreSQL projects with RLS/ROLE support.

## When to Use

Use this skill when the user:
- Modifies a SQLAlchemy or SQLModel model and needs migration
- Asks about DB schema drift or differences
- Wants to check/manage RLS policies or roles
- Says "migrate", "마이그레이션", "drift", or mentions table/column/schema changes

## Quick Start — Always use `--json`

```bash
agent-migrate auto --json
```

This single command detects drift, shows differences, and proposes a migration plan.

## Decision Tree

```
1. Run: agent-migrate auto --json
2. Parse JSON response:
   a. "in_sync": true → Tell user "스키마가 동기화 상태입니다"
   b. "in_sync": false → Check "plan.overall_risk":
      i.  "safe" or "caution" →
          Ask user for confirmation, then:
          agent-migrate auto --generate -m "description" --json
          agent-migrate auto --apply --execute -m "description" --json
      ii. "danger" →
          Show the plan to user, explain risks
          Wait for explicit approval, then use --force
```

## Available Commands

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `agent-migrate auto --json` | Full drift detection + plan | **Primary entry point** |
| `agent-migrate snapshot --json` | Current model + DB state | "현재 상태 보여줘" |
| `agent-migrate diff --json` | Specific differences | "뭐가 다른지 보여줘" |
| `agent-migrate plan --json` | Migration SQL preview | "마이그레이션 계획" |
| `agent-migrate generate -m "msg"` | Create migration file | After plan approval |
| `agent-migrate apply --execute` | Apply migration | After generate |
| `agent-migrate rls --json` | RLS policy status | "RLS 정책 확인" |

## Error Handling

```
If "CONFIG_NOT_FOUND":
  → Ask user for DATABASE_URL or: agent-migrate auto --db-url "postgresql://..." --json

If "DB_CONNECTION":
  → Check if DB is running, retry with --db-url

If "PARSE_ERROR":
  → Check model file for syntax errors

If "DANGEROUS_MIGRATION":
  → Show risks to user, use --force after approval
```

## JSON Output Format

All `--json` output:
```json
{
  "v": 1,
  "cmd": "auto|snapshot|diff|plan|rls",
  "drift_count": 0,
  "in_sync": true,
  "diffs": [{"type": "column_added", "tbl": "users", "col": "phone", "risk": "safe"}],
  "plan": {"steps": [{"sql": "ALTER TABLE ...", "risk": "safe"}], "overall_risk": "safe"}
}
```

Error output:
```json
{"error": "CONFIG_NOT_FOUND", "message": "...", "hint": "..."}
```

## Example Flows

### "User 모델에 phone 필드 추가하고 마이그레이션 해줘"

1. Edit `models/user.py` — add `phone: Mapped[str | None] = mapped_column()`
2. `agent-migrate auto --json` → parse: 1 diff (column_added, safe)
3. `agent-migrate auto --generate -m "add user phone field" --json`
4. `agent-migrate auto --apply --execute -m "add user phone field" --json`
5. "phone 컬럼이 추가되었습니다"

### "RLS 정책 확인해줘"

1. `agent-migrate rls --json` → parse table list with RLS on/off, policies
2. Show user the status

### "posts 테이블에 owner RLS 추가"

1. Edit model: add `__rls__ = {"select": "owner", "update": "owner"}`
2. `agent-migrate auto --json` → RLS diffs (CAUTION/DANGER)
3. Show plan to user, wait for approval
4. Generate and apply after approval

## RLS Presets

Models can declare RLS policies:
```python
class Post(Base):
    __tablename__ = "posts"
    __rls__ = {"select": "owner", "insert": "authenticated"}
```

Available presets: `owner`, `public_read`, `authenticated`, `admin_only`, `team`
Opt-out: `__rls__ = False`
