# agent-migrate — Project Technical Document

> **Version:** 0.1.0-draft
> **Date:** 2026-03-27
> **Author:** DongHyeok
> **Status:** Draft

---

## 1. 프로젝트 개요

### 1.1 프로젝트명

**agent-migrate** — AI 에이전트를 위한 DB 마이그레이션 CLI

### 1.2 리포지토리 구조

```
agent-migrate/
├── README.md
├── pyproject.toml              # Python 패키지 설정 (uv/poetry)
├── Cargo.toml                  # Rust 바이너리 (Phase 3)
├── LICENSE                     # Apache-2.0
├── CONTRIBUTING.md
│
├── src/
│   └── agent_migrate/
│       ├── __init__.py
│       ├── cli.py              # CLI 엔트리포인트 (typer 기반)
│       ├── config.py           # 설정 자동 감지
│       │
│       ├── parser/             # 모델 파싱
│       │   ├── __init__.py
│       │   ├── base.py         # ModelSchema 공통 인터페이스
│       │   ├── sqlalchemy.py   # SQLAlchemy DeclarativeBase 파서
│       │   ├── sqlmodel.py     # SQLModel 파서
│       │   └── ast_utils.py    # Python AST 유틸리티
│       │
│       ├── inspector/          # DB 스키마 조회
│       │   ├── __init__.py
│       │   ├── base.py         # DBSchema 공통 인터페이스
│       │   ├── postgresql.py   # PostgreSQL information_schema
│       │   ├── mysql.py        # MySQL (Phase 2)
│       │   └── sqlite.py       # SQLite (Phase 2)
│       │
│       ├── diff/               # 모델 vs DB 비교
│       │   ├── __init__.py
│       │   ├── engine.py       # Diff 알고리즘
│       │   ├── types.py        # DiffItem, DiffType 정의
│       │   └── risk.py         # 위험도 분석
│       │
│       ├── migration/          # 마이그레이션 생성
│       │   ├── __init__.py
│       │   ├── planner.py      # SQL 계획 생성
│       │   ├── alembic_compat.py # Alembic 포맷 생성
│       │   ├── raw_sql.py      # Raw SQL 포맷 생성
│       │   └── executor.py     # 마이그레이션 적용
│       │
│       ├── formatter/          # 에이전트 최적화 출력
│       │   ├── __init__.py
│       │   ├── ref.py          # @m1, @d1 등 ref 체계
│       │   ├── snapshot.py     # snapshot 포매팅
│       │   ├── diff_fmt.py     # diff 포매팅
│       │   └── plan_fmt.py     # plan 포매팅
│       │
│       └── guard/              # CI/CD 가드
│           ├── __init__.py
│           └── checker.py      # 배포 전 안전성 검증
│
├── skills/                     # Claude Code Skill
│   └── agent-migrate/
│       └── SKILL.md
│
├── tests/
│   ├── conftest.py             # pytest fixtures (testcontainers-python)
│   ├── test_parser/
│   │   ├── test_sqlalchemy.py
│   │   └── test_sqlmodel.py
│   ├── test_inspector/
│   │   └── test_postgresql.py
│   ├── test_diff/
│   │   ├── test_engine.py
│   │   └── test_risk.py
│   ├── test_migration/
│   │   └── test_planner.py
│   └── test_cli/
│       └── test_commands.py
│
├── fixtures/                   # 테스트용 샘플 프로젝트
│   ├── fastapi_basic/
│   ├── fastapi_sqlmodel/
│   └── fastapi_complex/
│
└── docs/
    ├── architecture.md
    ├── agent-pattern.md        # agent-browser 패턴 설명
    └── examples/
        ├── basic-usage.md
        └── claude-code-integration.md
```

---

## 2. 아키텍처

### 2.1 전체 아키텍처 다이어그램

```
┌──────────────────────────────────────────────────────────────┐
│                     AI Coding Agent                          │
│  (Claude Code / Cursor / Codex / Gemini CLI)                 │
│                                                              │
│  "User 모델에 phone 필드 추가하고 마이그레이션 해줘"          │
└────────────────────────┬─────────────────────────────────────┘
                         │ bash: agent-migrate diff
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   agent-migrate CLI                           │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ snapshot  │  │   diff   │  │   plan   │  │  apply   │    │
│  │          │  │          │  │          │  │          │    │
│  │ Models + │  │ Model vs │  │ SQL Plan │  │ Execute  │    │
│  │ DB State │  │ DB Diff  │  │ + Risk   │  │ + Verify │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │              │              │              │          │
│  ┌────▼──────────────▼──────────────▼──────────────▼────┐    │
│  │              Core Engine (Python)                     │    │
│  │                                                      │    │
│  │  ┌─────────┐ ┌───────────┐ ┌──────────┐ ┌────────┐  │    │
│  │  │ Parser  │ │ Inspector │ │ Diff Eng │ │Migrator│  │    │
│  │  │         │ │           │ │          │ │        │  │    │
│  │  │SQLAlch. │ │ info_     │ │ Compare  │ │Alembic │  │    │
│  │  │SQLModel │ │ schema    │ │ Analyze  │ │Raw SQL │  │    │
│  │  └────┬────┘ └─────┬─────┘ └────┬─────┘ └───┬────┘  │    │
│  │       │             │            │            │       │    │
│  └───────┼─────────────┼────────────┼────────────┼───────┘    │
│          │             │            │            │            │
│  ┌───────▼─────────────▼────────────▼────────────▼───────┐    │
│  │              Formatter (에이전트 최적화 출력)           │    │
│  │  @m1, @d1 ref 체계 / 토큰 최소화 / 위험도 색상       │    │
│  └───────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
  ┌──────────────┐              ┌──────────────┐
  │ Python Files │              │  PostgreSQL   │
  │ models.py    │              │  Database     │
  │ .env         │              │              │
  │ alembic/     │              │              │
  └──────────────┘              └──────────────┘
```

### 2.2 agent-browser 패턴 매핑

| agent-browser | agent-migrate | 설명 |
|---|---|---|
| `open URL` | `connect` (auto) | DB 연결 (자동 감지) |
| `snapshot -i` | `snapshot` | 모델 + DB 구조를 ref로 |
| `@e1, @e2` refs | `@m1`(모델), `@d1`(테이블), `@v1`(버전) | 참조 체계 |
| `click @e1` | `apply @v4` | 특정 마이그레이션 적용 |
| `fill @e2 "text"` | `generate -m "message"` | 마이그레이션 생성 |
| `Done` (6글자) | `✅ Applied (0.02s)` | 최소 출력 |
| 세션 기반 데몬 | 상태 없음 (매 실행 독립) | 마이그레이션은 상태 불필요 |

### 2.3 데이터 흐름

```
[1] snapshot
    models.py ──── AST Parse ────── ModelSchema[]
                                          │
    PostgreSQL ── information_schema ── DBSchema[]
                                          │
                                    ┌─────▼─────┐
                                    │ Ref Engine │ → @m1, @d1, ...
                                    └─────┬─────┘
                                          │
                                    Agent Output (< 500 tokens)

[2] diff
    ModelSchema[] ─┐
                   ├── Diff Engine ── DiffItem[]
    DBSchema[] ────┘                     │
                                    ┌────▼────┐
                                    │  Risk   │ → SAFE / CAUTION / DANGER
                                    │Analyzer │
                                    └────┬────┘
                                         │
                                    Agent Output (< 200 tokens)

[3] plan
    DiffItem[] ── Planner ── MigrationStep[]
                                  │
                           ┌──────▼──────┐
                           │ Data Check  │ → 기존 데이터와 호환?
                           │ (SELECT ... │    NULL 가능? Enum 매핑?
                           │  from DB)   │
                           └──────┬──────┘
                                  │
                            Agent Output (< 300 tokens)

[4] generate
    MigrationStep[] ── Alembic Generator ── versions/004_xxx.py
                    └─ Raw SQL Generator ── migrations/004_xxx.sql

[5] apply
    Migration File ── Executor ── DB ── Verify ── "✅ Applied"
```

---

## 3. 핵심 컴포넌트 상세

### 3.1 Model Parser

**목적:** Python 소스 파일에서 SQLAlchemy/SQLModel 모델 정의를 추출하여 구조화된 `ModelSchema`로 변환

**접근 방식: AST + Runtime 하이브리드**

```python
# Phase 1: AST 기반 (빠르고 안전)
# - Column(Type) 패턴 매칭
# - 기본적인 관계(ForeignKey) 감지
# - Enum 클래스 감지

# Phase 2: Runtime 기반 (정확하지만 import 부작용 가능)
# - Base.metadata.tables 직접 접근
# - 동적 생성 모델, Mixin, column_property 등 처리
# - AST가 놓친 케이스 보완
```

**ModelSchema 구조:**

```python
@dataclass
class ColumnSchema:
    name: str
    python_type: str          # "String", "Integer", "Enum", ...
    sql_type: str | None      # "VARCHAR(100)", "INTEGER", ...
    nullable: bool
    primary_key: bool
    foreign_key: str | None   # "users.id"
    default: str | None
    server_default: str | None
    enum_values: list[str] | None

@dataclass
class ModelSchema:
    name: str                 # "User"
    tablename: str            # "users"
    columns: list[ColumnSchema]
    relationships: list[RelationshipSchema]
    source_file: str          # "app/models/user.py"
    source_line: int          # 15
```

**파싱 전략:**

```python
import ast

class SQLAlchemyModelVisitor(ast.NodeVisitor):
    """SQLAlchemy 모델 클래스에서 컬럼 정의를 추출"""

    def visit_ClassDef(self, node: ast.ClassDef):
        # Base 상속 확인
        if not self._inherits_from_base(node):
            return

        model = ModelSchema(name=node.name, ...)

        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                # __tablename__ = "users"
                # id = Column(Integer, primary_key=True)
                self._parse_assignment(stmt, model)
            elif isinstance(stmt, ast.AnnAssign):
                # id: Mapped[int] = mapped_column(primary_key=True)
                self._parse_annotated_assignment(stmt, model)

        return model
```

**지원 패턴 (Phase 1):**

```python
# Pattern 1: Classic SQLAlchemy
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(100), unique=True, nullable=False)
    name = Column(String(50))

# Pattern 2: SQLAlchemy 2.0 Mapped
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str | None] = mapped_column(String(50))

# Pattern 3: SQLModel
class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(max_length=100, unique=True)
    name: str | None = Field(default=None, max_length=50)
```

### 3.2 DB Inspector

**목적:** 실제 데이터베이스에서 현재 스키마를 조회하여 `DBSchema`로 변환

```python
@dataclass
class DBColumnSchema:
    name: str
    data_type: str            # "character varying", "integer", ...
    is_nullable: bool
    column_default: str | None
    character_maximum_length: int | None
    constraint_type: str | None  # "PRIMARY KEY", "UNIQUE", "FOREIGN KEY"
    foreign_table: str | None
    foreign_column: str | None

@dataclass
class DBTableSchema:
    name: str
    schema_name: str          # "public"
    columns: list[DBColumnSchema]
    row_count: int            # approximate (pg_class.reltuples)
    size_bytes: int           # pg_total_relation_size
```

**PostgreSQL 조회:**

```sql
-- 테이블 + 컬럼 정보
SELECT
    t.table_name,
    c.column_name,
    c.data_type,
    c.is_nullable,
    c.column_default,
    c.character_maximum_length
FROM information_schema.tables t
JOIN information_schema.columns c
    ON t.table_name = c.table_name
WHERE t.table_schema = 'public'
    AND t.table_type = 'BASE TABLE'
ORDER BY t.table_name, c.ordinal_position;

-- FK 관계
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table,
    ccu.column_name AS foreign_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY';

-- 테이블 행 수 (approximate, 빠름)
SELECT relname, reltuples::bigint AS row_count
FROM pg_class
WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace;
```

### 3.3 Diff Engine

**목적:** ModelSchema와 DBSchema를 비교하여 차이점(DiffItem)을 생성

```python
from enum import Enum

class DiffType(Enum):
    TABLE_ADDED = "table_added"       # 모델에만 있고 DB에 없음
    TABLE_REMOVED = "table_removed"   # DB에만 있고 모델에 없음
    COLUMN_ADDED = "column_added"
    COLUMN_REMOVED = "column_removed"
    COLUMN_TYPE_CHANGED = "column_type_changed"
    COLUMN_NULLABLE_CHANGED = "column_nullable_changed"
    COLUMN_DEFAULT_CHANGED = "column_default_changed"
    FK_ADDED = "fk_added"
    FK_REMOVED = "fk_removed"
    ENUM_VALUES_CHANGED = "enum_values_changed"

class RiskLevel(Enum):
    SAFE = "safe"             # 데이터 손실 없음 (e.g., 컬럼 추가)
    CAUTION = "caution"       # 주의 필요 (e.g., nullable→not null)
    DANGER = "danger"         # 데이터 손실 가능 (e.g., 컬럼 삭제, 타입 변경)

@dataclass
class DiffItem:
    diff_type: DiffType
    model_ref: str            # "@m1.phone_number"
    db_ref: str | None        # "@d1" (없으면 None)
    description: str          # "Column 'phone_number' exists in model but not in DB"
    risk: RiskLevel
    model_value: str | None   # "String(20), nullable"
    db_value: str | None      # None (DB에 없으므로)
    affected_rows: int | None # 영향받는 행 수 (DB 조회 필요)
```

**타입 매핑 테이블:**

```python
# SQLAlchemy Python type → PostgreSQL expected types
TYPE_MAP: dict[str, set[str]] = {
    "Integer": {"integer", "int4"},
    "BigInteger": {"bigint", "int8"},
    "SmallInteger": {"smallint", "int2"},
    "String": {"character varying", "varchar", "text"},
    "Text": {"text"},
    "Boolean": {"boolean", "bool"},
    "DateTime": {"timestamp without time zone", "timestamp with time zone"},
    "Date": {"date"},
    "Float": {"double precision", "float8", "real", "float4"},
    "Numeric": {"numeric", "decimal"},
    "JSON": {"json", "jsonb"},
    "UUID": {"uuid"},
    "LargeBinary": {"bytea"},
    "Enum": {"user-defined"},  # PostgreSQL 커스텀 Enum
}
```

### 3.4 Risk Analyzer

**목적:** 각 DiffItem의 위험도를 분석하고 데이터 호환성을 검증

```python
class RiskAnalyzer:
    """마이그레이션 위험도 분석기"""

    def analyze(self, diff: DiffItem, db_conn) -> RiskAssessment:
        match diff.diff_type:
            case DiffType.COLUMN_ADDED:
                return self._assess_column_add(diff)
            case DiffType.COLUMN_REMOVED:
                return self._assess_column_remove(diff, db_conn)
            case DiffType.COLUMN_TYPE_CHANGED:
                return self._assess_type_change(diff, db_conn)
            case DiffType.ENUM_VALUES_CHANGED:
                return self._assess_enum_change(diff, db_conn)
            # ...

    def _assess_column_remove(self, diff, db_conn) -> RiskAssessment:
        """컬럼 삭제: 항상 DANGER, 영향받는 행 수 조회"""
        non_null_count = db_conn.execute(
            f"SELECT COUNT(*) FROM {diff.table} WHERE {diff.column} IS NOT NULL"
        ).scalar()

        return RiskAssessment(
            risk=RiskLevel.DANGER,
            reason=f"Dropping column with {non_null_count} non-null values",
            affected_rows=non_null_count,
            recommendation="Backup data before proceeding" if non_null_count > 0 else None,
        )

    def _assess_enum_change(self, diff, db_conn) -> RiskAssessment:
        """Enum 변경: DB에 있지만 모델에 없는 값 확인"""
        db_values = set(db_conn.execute(
            f"SELECT DISTINCT {diff.column} FROM {diff.table}"
        ).scalars())
        model_values = set(diff.model_enum_values)
        orphaned = db_values - model_values

        if orphaned:
            return RiskAssessment(
                risk=RiskLevel.DANGER,
                reason=f"DB has values {orphaned} not in model Enum",
                affected_rows=len(orphaned),
                recommendation=f"Add {orphaned} to model or migrate data first",
            )
        return RiskAssessment(risk=RiskLevel.SAFE)
```

### 3.5 Ref 체계

```python
class RefEngine:
    """에이전트 친화적 ref 체계 관리"""

    def assign_refs(
        self,
        models: list[ModelSchema],
        tables: list[DBTableSchema],
        versions: list[MigrationVersion],
    ) -> RefMap:
        ref_map = RefMap()

        for i, model in enumerate(models, 1):
            ref_map.add(f"@m{i}", RefType.MODEL, model)

        for i, table in enumerate(tables, 1):
            ref_map.add(f"@d{i}", RefType.TABLE, table)

        for i, version in enumerate(versions, 1):
            ref_map.add(f"@v{i}", RefType.VERSION, version)

        return ref_map
```

---

## 4. 설정 자동 감지 (Zero-config)

### 4.1 DB URL 탐색 순서

```python
class ConfigDetector:
    """프로젝트에서 DB 연결 정보를 자동 감지"""

    SEARCH_ORDER = [
        # 1. 환경변수
        ("env", "DATABASE_URL"),
        ("env", "DB_URL"),
        ("env", "POSTGRES_URL"),
        ("env", "SQLALCHEMY_DATABASE_URI"),

        # 2. .env 파일
        ("dotenv", ".env"),
        ("dotenv", ".env.local"),
        ("dotenv", ".env.development"),

        # 3. Python 설정 파일 (AST 파싱)
        ("python", "app/core/config.py"),
        ("python", "app/config.py"),
        ("python", "config/settings.py"),
        ("python", "settings.py"),

        # 4. alembic.ini
        ("ini", "alembic.ini", "sqlalchemy.url"),

        # 5. pyproject.toml
        ("toml", "pyproject.toml", "tool.agent-migrate.database-url"),
    ]
```

### 4.2 모델 파일 탐색

```python
class ModelDiscovery:
    """SQLAlchemy/SQLModel 모델 파일을 자동 탐색"""

    INDICATORS = [
        "from sqlalchemy",
        "from sqlmodel",
        "DeclarativeBase",
        "declarative_base",
        "SQLModel",
        "mapped_column",
        "Column(",
    ]

    def discover(self, project_root: Path) -> list[Path]:
        """프로젝트에서 모델 정의가 있는 Python 파일을 찾음"""
        model_files = []
        for py_file in project_root.rglob("*.py"):
            if self._skip(py_file):  # venv, __pycache__, migrations 등
                continue
            content = py_file.read_text(errors="ignore")
            if any(indicator in content for indicator in self.INDICATORS):
                model_files.append(py_file)
        return model_files
```

---

## 5. 출력 포맷 설계

### 5.1 설계 원칙

agent-browser의 출력 설계 원칙을 그대로 적용:

1. **최소 토큰**: 성공 시 한 줄, 실패 시 원인만
2. **ref 기반**: `@m1`, `@d1` 등으로 후속 명령에서 참조 가능
3. **구조화**: AI가 파싱하기 쉬운 일관된 포맷
4. **위험도 가시화**: SAFE/CAUTION/DANGER를 즉시 인식

### 5.2 snapshot 출력

```
Models (3 found in app/models/):
  @m1 User      (id:int, email:str, name:str?, created_at:datetime)
  @m2 Order     (id:int, user_id→@m1:int, total:Decimal, status:Enum[pending,paid,shipped])
  @m3 Product   (id:int, name:str, price:Decimal, description:str?)

Database (PostgreSQL localhost:5432/myapp):
  @d1 users     (id:int4, email:varchar, name:varchar?, created_at:timestamp)  1,247 rows
  @d2 orders    (id:int4, user_id→@d1:int4, total:numeric, status:varchar)     5,832 rows
  @d3 products  (id:int4, name:varchar, price:numeric)                          89 rows

Drift: 2 differences
  @m2.status  Enum vs varchar
  @m3         +description (model only)

Migrations: 3 applied (@v1..@v3), 0 pending
```

**토큰 추정: ~250 토큰** (vs Alembic 출력 ~2,000 토큰)

### 5.3 diff 출력

```
[+] @m3.description  Text, nullable        SAFE
[~] @m2.status       Enum→varchar mismatch DANGER (23 rows with 'cancelled' not in Enum)
```

**토큰 추정: ~50 토큰**

### 5.4 plan 출력

```
Plan: 2 steps

1. [SAFE] ALTER TABLE products ADD COLUMN description TEXT;
   Impact: 89 rows, no data change

2. [DANGER] ALTER TABLE orders ALTER COLUMN status TYPE order_status USING status::order_status;
   Requires: CREATE TYPE order_status AS ENUM('pending','paid','shipped');
   ⚠️ 23 rows with status='cancelled' will FAIL
   Recommendation: Add 'cancelled' to Enum or UPDATE first

Overall: MEDIUM risk
```

**토큰 추정: ~120 토큰**

### 5.5 apply 출력

```
✅ Step 1 applied (0.01s): products.description added
❌ Step 2 blocked: DANGER migration requires --force flag
```

---

## 6. 테스트 전략

### 6.1 테스트 인프라

```python
# conftest.py
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres():
    """테스트용 PostgreSQL 컨테이너"""
    with PostgresContainer("postgres:16") as pg:
        yield pg.get_connection_url()

@pytest.fixture
def fresh_db(postgres):
    """매 테스트마다 깨끗한 DB"""
    engine = create_engine(postgres)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
```

### 6.2 테스트 매트릭스

| 카테고리 | 테스트 | 우선순위 |
|----------|--------|---------|
| Parser | SQLAlchemy 2.0 Mapped 모델 파싱 | P0 |
| Parser | SQLModel 모델 파싱 | P0 |
| Parser | Classic SQLAlchemy 파싱 | P1 |
| Parser | Enum, JSON, Array 타입 | P1 |
| Parser | FK / relationship 감지 | P0 |
| Inspector | PostgreSQL information_schema 조회 | P0 |
| Inspector | 행 수 / 테이블 크기 조회 | P1 |
| Diff | 컬럼 추가 감지 | P0 |
| Diff | 컬럼 삭제 감지 | P0 |
| Diff | 타입 변경 감지 | P0 |
| Diff | Enum 값 변경 감지 | P1 |
| Risk | SAFE 분류 (additive) | P0 |
| Risk | DANGER 분류 (destructive) | P0 |
| Risk | 영향 행 수 계산 | P0 |
| Migration | Alembic 호환 파일 생성 | P0 |
| Migration | dry-run 동작 | P0 |
| Migration | apply + verify | P0 |
| CLI | snapshot 명령어 E2E | P0 |
| CLI | diff → plan → generate → apply 풀 플로우 | P0 |

### 6.3 Fixture 프로젝트

```python
# fixtures/fastapi_basic/app/models.py
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, func

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

---

## 7. 의존성

### 7.1 Python 핵심 의존성

```toml
[project]
name = "agent-migrate"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",          # CLI 프레임워크
    "rich>=13.0",           # 터미널 출력
    "sqlalchemy>=2.0",      # DB 연결 + 메타데이터 (inspector용)
    "psycopg[binary]>=3.1", # PostgreSQL 드라이버
    "python-dotenv>=1.0",   # .env 파일 읽기
    "alembic>=1.13",        # 마이그레이션 파일 생성 (호환 모드)
]

[project.optional-dependencies]
mysql = ["pymysql>=1.1"]
sqlite = []  # 빌트인
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "testcontainers[postgres]>=4.0",
    "ruff>=0.5",
]
```

### 7.2 Phase 3 Rust/Go 의존성

```toml
# Cargo.toml (CLI 엔트리포인트 + 출력 포매터)
[dependencies]
clap = "4"                  # CLI 파싱
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio-postgres = "0.7"      # 직접 DB 연결 (snapshot 속도 최적화)
tree-sitter = "0.24"        # Python AST 파싱 (선택적)
tree-sitter-python = "0.23"
```

---

## 8. 배포 전략

### 8.1 Phase 1: PyPI (Python 패키지)

```bash
pip install agent-migrate
agent-migrate snapshot
```

### 8.2 Phase 3: 멀티 채널

```bash
# PyPI
pip install agent-migrate

# Homebrew
brew install agent-migrate

# npm (agent-browser와 동일 패턴)
npm install -g agent-migrate

# Cargo
cargo install agent-migrate
```

### 8.3 Claude Code Skill 배포

```bash
# 자동 설치 (agent-browser와 동일 패턴)
cd your-project
npx agent-migrate init --skill

# 수동 설치
mkdir -p .claude/skills/agent-migrate
curl -o .claude/skills/agent-migrate/SKILL.md \
  https://raw.githubusercontent.com/donghyeok/agent-migrate/main/skills/agent-migrate/SKILL.md
```

---

## 9. SKILL.md (Claude Code 통합)

```markdown
---
name: agent-migrate
description: >
  DB 마이그레이션을 관리합니다. SQLAlchemy/SQLModel 모델과 PostgreSQL DB 사이의
  스키마 차이를 감지하고, 안전한 마이그레이션을 생성/적용합니다.
  모델 변경 후 "마이그레이션", "DB 동기화", "스키마 변경", "migrate",
  "drift", "컬럼 추가/삭제" 키워드에 반응합니다.
---

## 워크플로우

모델 변경 후 다음 순서로 실행:

1. `agent-migrate diff` — 모델과 DB 차이 확인
2. `agent-migrate plan` — SQL 계획 + 위험도 확인
3. `agent-migrate generate -m "설명"` — 마이그레이션 파일 생성
4. `agent-migrate apply --execute` — 적용

## 명령어

```bash
agent-migrate snapshot              # 현재 모델 + DB 상태
agent-migrate diff                  # 차이점 목록
agent-migrate plan                  # SQL 계획 + 위험도
agent-migrate generate -m "msg"     # 마이그레이션 파일 생성
agent-migrate apply                 # dry-run
agent-migrate apply --execute       # 실제 적용
agent-migrate guard                 # CI/CD 안전 체크
agent-migrate rollback @v4          # 특정 버전으로 롤백
```

## 주의사항

- DANGER 위험도 마이그레이션은 사용자에게 반드시 확인을 구하세요
- `apply`는 기본이 dry-run입니다. 실제 적용은 `--execute` 필요
- 모델 파일 수정 후에는 항상 `diff`로 확인하세요
```

---

## 10. 개발 일정 (Phase 1 MVP)

### Week 1: 기반

- 프로젝트 세팅 (pyproject.toml, ruff, pytest, CI)
- ConfigDetector: DB URL 자동 감지
- ModelDiscovery: 모델 파일 탐색
- SQLAlchemy 2.0 Parser (기본 Column/Mapped 타입)
- PostgreSQL Inspector (information_schema 조회)

### Week 2: 핵심 로직

- Diff Engine: 모델 vs DB 비교
- Risk Analyzer: SAFE/CAUTION/DANGER 분류
- Ref Engine: @m1, @d1 ref 체계
- snapshot, diff 명령어 구현

### Week 3: 마이그레이션

- Migration Planner: diff → SQL 계획
- Alembic 호환 마이그레이션 생성
- plan, generate 명령어 구현
- apply (dry-run + --execute) 구현
- guard 명령어 구현

### Week 4: 통합 + 배포

- Claude Code SKILL.md 작성 + 테스트
- E2E 테스트 (fixture 프로젝트)
- README.md 작성
- PyPI 배포
- Show HN / Reddit 준비
