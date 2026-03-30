"""End-to-end integration test: snapshot → diff → plan → apply cycle.

Scenario against a real postgres:16-alpine container:

  Phase 1: Apply User + Post (partial schema with TimestampMixin)
  Phase 2: Add Comment table → TABLE_ADDED detected and applied
  Phase 3: Add view_count to Post → COLUMN_ADDED detected and applied

Verifies:
  - Mixin columns (created_at, updated_at) are parsed from both models
  - TABLE_ADDED / COLUMN_ADDED diff types are produced correctly
  - MigrationExecutor.execute() creates real tables and columns
  - After full sync, no structural diffs remain
"""

from __future__ import annotations

from textwrap import dedent
from typing import TYPE_CHECKING

from sqlalchemy import inspect

from agent_migrate.diff import compute_diff
from agent_migrate.inspector import inspect_db
from agent_migrate.orchestrator import Orchestrator
from agent_migrate.parser import parse_models
from agent_migrate.types import DiffType

if TYPE_CHECKING:
    from pathlib import Path


# ── Model source for each phase ───────────────────────────────────────────────

_BASE_HEADER = dedent("""\
    \"\"\"Bulletin board models.\"\"\"
    from __future__ import annotations
    from datetime import datetime
    from sqlalchemy import DateTime, ForeignKey, String, Text, func
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

    class Base(DeclarativeBase):
        pass

    class TimestampMixin:
        created_at: Mapped[datetime] = mapped_column(
            DateTime, server_default=func.now(), nullable=False
        )
        updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    class User(TimestampMixin, Base):
        __tablename__ = "users"
        id: Mapped[int] = mapped_column(primary_key=True)
        username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
        email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
        posts: Mapped[list[Post]] = relationship("Post", back_populates="author")

    class Post(TimestampMixin, Base):
        __tablename__ = "posts"
        id: Mapped[int] = mapped_column(primary_key=True)
        title: Mapped[str] = mapped_column(String(300), nullable=False)
        content: Mapped[str] = mapped_column(Text, nullable=False)
        author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
        author: Mapped[User] = relationship("User", back_populates="posts")
""")

_COMMENT_CLASS = dedent("""\

    class Comment(TimestampMixin, Base):
        __tablename__ = "comments"
        id: Mapped[int] = mapped_column(primary_key=True)
        content: Mapped[str] = mapped_column(Text, nullable=False)
        post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False)
        author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
        post: Mapped[Post] = relationship("Post")
        author: Mapped[User] = relationship("User")
""")

_VIEW_COUNT_LINE = (
    "    view_count: Mapped[int] = mapped_column(default=0, nullable=False)\n"
)

# Phase 1: User + Post with mixin
_MODELS_PHASE1 = _BASE_HEADER

# Phase 2: + Comment table
_MODELS_PHASE2 = _BASE_HEADER + _COMMENT_CLASS

# Phase 3: + view_count column on Post (inserted before `author` relationship)
# After dedent, Post class body lines have 4-space indentation.
_MODELS_PHASE3 = _MODELS_PHASE2.replace(
    "    author: Mapped[User] = relationship(\"User\", back_populates=\"posts\")",
    _VIEW_COUNT_LINE
    + "    author: Mapped[User] = relationship(\"User\", back_populates=\"posts\")",
    1,  # replace only the first occurrence (Post class, not Comment)
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_models(root: Path, source: str) -> None:
    (root / "models.py").write_text(source, encoding="utf-8")


def _orc_apply(root: Path, db_url: str) -> None:
    """Apply migration synchronously using the Orchestrator."""
    Orchestrator().apply(root, db_url=db_url, execute=True)


# ── Parser tests (no DB required) ────────────────────────────────────────────


def test_mixin_columns_on_user(tmp_path):
    """TimestampMixin columns (created_at, updated_at) appear in User."""
    _write_models(tmp_path, _MODELS_PHASE1)
    models = parse_models([tmp_path / "models.py"])
    model_map = {m.tablename: m for m in models}

    user_cols = {c.name for c in model_map["users"].columns}
    assert "created_at" in user_cols
    assert "updated_at" in user_cols


def test_mixin_columns_on_post(tmp_path):
    """TimestampMixin columns (created_at, updated_at) appear in Post."""
    _write_models(tmp_path, _MODELS_PHASE1)
    models = parse_models([tmp_path / "models.py"])
    model_map = {m.tablename: m for m in models}

    post_cols = {c.name for c in model_map["posts"].columns}
    assert "created_at" in post_cols
    assert "updated_at" in post_cols


def test_phase1_parses_two_models(tmp_path):
    """Phase 1 source produces exactly User and Post models (no Comment)."""
    _write_models(tmp_path, _MODELS_PHASE1)
    models = parse_models([tmp_path / "models.py"])
    tablenames = {m.tablename for m in models}
    assert tablenames == {"users", "posts"}


def test_phase2_parses_three_models(tmp_path):
    """Phase 2 source produces User, Post, and Comment models."""
    _write_models(tmp_path, _MODELS_PHASE2)
    models = parse_models([tmp_path / "models.py"])
    tablenames = {m.tablename for m in models}
    assert tablenames == {"users", "posts", "comments"}


def test_phase3_has_view_count_on_post(tmp_path):
    """Phase 3 Post model includes view_count column."""
    _write_models(tmp_path, _MODELS_PHASE3)
    models = parse_models([tmp_path / "models.py"])
    model_map = {m.tablename: m for m in models}
    post_cols = {c.name for c in model_map["posts"].columns}
    assert "view_count" in post_cols


# ── DB integration tests (testcontainers) ─────────────────────────────────────


def test_phase1_creates_users_and_posts_tables(tmp_path, db_engine, postgres_url):
    """Applying phase 1 creates users and posts tables in PostgreSQL."""
    _write_models(tmp_path, _MODELS_PHASE1)
    _orc_apply(tmp_path, postgres_url)

    names = set(inspect(db_engine).get_table_names())
    assert "users" in names
    assert "posts" in names
    assert "comments" not in names


def test_phase2_detects_table_added_for_comments(tmp_path, db_engine, postgres_url):
    """After phase 1 in DB, phase 2 models diff produces TABLE_ADDED for comments."""
    # Establish phase 1 schema in DB
    _write_models(tmp_path, _MODELS_PHASE1)
    _orc_apply(tmp_path, postgres_url)

    # Compute diff with phase 2 models
    _write_models(tmp_path, _MODELS_PHASE2)
    models = parse_models([tmp_path / "models.py"])
    tables = inspect_db(db_engine)
    diffs = compute_diff(models, tables)

    added = [d for d in diffs if d.diff_type == DiffType.TABLE_ADDED]
    assert any(d.table_name == "comments" for d in added), (
        f"Expected TABLE_ADDED for 'comments', got: {diffs}"
    )


def test_phase2_apply_creates_comment_table(tmp_path, db_engine, postgres_url):
    """Applying phase 2 creates the comments table."""
    _write_models(tmp_path, _MODELS_PHASE1)
    _orc_apply(tmp_path, postgres_url)

    _write_models(tmp_path, _MODELS_PHASE2)
    _orc_apply(tmp_path, postgres_url)

    assert "comments" in set(inspect(db_engine).get_table_names())


def test_phase3_detects_column_added_for_view_count(tmp_path, db_engine, postgres_url):
    """After phase 2 in DB, phase 3 models diff produces COLUMN_ADDED view_count on posts."""
    _write_models(tmp_path, _MODELS_PHASE1)
    _orc_apply(tmp_path, postgres_url)
    _write_models(tmp_path, _MODELS_PHASE2)
    _orc_apply(tmp_path, postgres_url)

    # Compute diff with phase 3 models
    _write_models(tmp_path, _MODELS_PHASE3)
    models = parse_models([tmp_path / "models.py"])
    tables = inspect_db(db_engine)
    diffs = compute_diff(models, tables)

    col_added = [
        d for d in diffs
        if d.diff_type == DiffType.COLUMN_ADDED and d.table_name == "posts"
    ]
    assert any(d.column_name == "view_count" for d in col_added), (
        f"Expected COLUMN_ADDED view_count on posts, got: {diffs}"
    )


def test_phase3_apply_adds_view_count_column(tmp_path, db_engine, postgres_url):
    """Applying phase 3 adds view_count to the posts table."""
    _write_models(tmp_path, _MODELS_PHASE1)
    _orc_apply(tmp_path, postgres_url)
    _write_models(tmp_path, _MODELS_PHASE2)
    _orc_apply(tmp_path, postgres_url)
    _write_models(tmp_path, _MODELS_PHASE3)
    _orc_apply(tmp_path, postgres_url)

    post_cols = {c["name"] for c in inspect(db_engine).get_columns("posts")}
    assert "view_count" in post_cols


def test_no_structural_diff_after_full_sync(tmp_path, db_engine, postgres_url):
    """After applying all three phases, no TABLE/COLUMN add/remove diffs remain."""
    for source in (_MODELS_PHASE1, _MODELS_PHASE2, _MODELS_PHASE3):
        _write_models(tmp_path, source)
        _orc_apply(tmp_path, postgres_url)

    models = parse_models([tmp_path / "models.py"])
    tables = inspect_db(db_engine)
    diffs = compute_diff(models, tables)

    structural = [
        d for d in diffs
        if d.diff_type in {
            DiffType.TABLE_ADDED,
            DiffType.TABLE_REMOVED,
            DiffType.COLUMN_ADDED,
            DiffType.COLUMN_REMOVED,
        }
    ]
    assert structural == [], f"Unexpected structural diffs after full sync: {structural}"


def test_generate_raw_sql_file(tmp_path, db_engine, postgres_url):
    """Orchestrator.generate() produces a .sql file for the phase 1 → 2 diff."""
    # Apply phase 1 first
    _write_models(tmp_path, _MODELS_PHASE1)
    _orc_apply(tmp_path, postgres_url)

    # Generate (not apply) migration for phase 2
    _write_models(tmp_path, _MODELS_PHASE2)
    sql_path = Orchestrator().generate(
        tmp_path, message="add comment table", db_url=postgres_url, fmt="sql"
    )

    assert sql_path.exists()
    assert sql_path.suffix == ".sql"
    content = sql_path.read_text()
    assert 'CREATE TABLE "comments"' in content
