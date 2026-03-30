# .claude/skills/agent-migrate/SKILL.md
---
name: agent-migrate
description: >
  DB 마이그레이션을 관리합니다. 모델 변경 후 자동으로 drift를 감지하고
  마이그레이션을 생성합니다. "마이그레이션", "DB 스키마", "테이블 변경",
  "컬럼 추가/삭제", "migrate" 키워드에 반응합니다.
---
```

**실제 대화 흐름:**
```
You: "User 모델에 phone_number 필드 추가하고 마이그레이션까지 해줘"

Claude Code:
  1. app/models/user.py 수정 (phone_number: str 추가)
  2. agent-migrate diff 실행
     → "+phone_number: String(20), nullable"
  3. agent-migrate plan 실행
     → "Step 1: ALTER TABLE users ADD COLUMN phone_number VARCHAR(20)"
     → "Risk: LOW, Safe migration"
  4. agent-migrate generate -m "add user phone number"
  5. agent-migrate apply --execute
  6. "완료! phone_number 컬럼이 추가되었습니다."
