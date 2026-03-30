<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-31 | Updated: 2026-03-31 -->

# parser

## Purpose
AST-based model parsing for SQLAlchemy 2.0, Classic, and SQLModel. Extracts `ModelSchema` from Python files without runtime imports.

## Key Files
| File | Description |
|------|-------------|
| `sqlalchemy.py` | Main parser — handles Mapped[], Column(), Field(), `__rls__`, `__tablename__` |
| `ast_utils.py` | AST helpers: type mapping, Column/Field kwargs extraction |
| `base.py` | `ModelParser` protocol definition |
| `__init__.py` | `parse_models()` entry point |

## For AI Agents

### Supported Patterns
- `Mapped[T] = mapped_column(...)` — SQLAlchemy 2.0
- `name = Column(Type, ...)` — SQLAlchemy Classic
- `name: str = Field(...)` — SQLModel (`table=True` required)
- `__rls__ = {"select": "owner"}` — RLS annotation
- `__rls__ = False` — RLS opt-out
- `__tablename__` — explicit or auto-generated (SQLModel: class name lowercased)

### Key Internals
- `_rls_raw: dict[str, dict[str, str]]` on parser instance stores raw __rls__ dicts
- `_has_table_true()` detects SQLModel table models vs schema models
- `PYTHON_TYPE_MAP` in ast_utils maps `str→String`, `int→Integer`, etc.
- `extract_column_kwargs()` works for `mapped_column()`, `Column()`, and `Field()`

<!-- MANUAL: -->
