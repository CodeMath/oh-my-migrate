"""Tests for the SQLAlchemy AST-based model parser.

13 required test cases + fixture parsing verification.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_migrate.exceptions import ParseError
from agent_migrate.parser.sqlalchemy import SQLAlchemyParser

# ── Shared parser instance ─────────────────────────────────────────────────────

_parser = SQLAlchemyParser()


def parse(source: str):
    return _parser.parse_source(source)


# ── Source helpers ─────────────────────────────────────────────────────────────

_BASE_HEADER = """\
from __future__ import annotations
from typing import Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Boolean, Float, Text, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass

"""


def _src(*class_bodies: str) -> str:
    """Prepend the standard header and join class bodies."""
    return _BASE_HEADER + "\n\n".join(class_bodies)


# ── Test 1: Mapped[int] primary_key ───────────────────────────────────────────

def test_mapped_int_primary_key():
    source = _src("""\
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
""")
    models = parse(source)
    assert len(models) == 1
    model = models[0]
    assert model.name == "User"
    assert model.tablename == "users"
    assert len(model.columns) == 1
    col = model.columns[0]
    assert col.name == "id"
    assert col.python_type == "Integer"
    assert col.primary_key is True
    assert col.nullable is False


# ── Test 2: Mapped[str] + String(100) ─────────────────────────────────────────

def test_mapped_str_with_string_type():
    source = _src("""\
class User(Base):
    __tablename__ = "users"
    name: Mapped[str] = mapped_column(String(100))
""")
    models = parse(source)
    assert len(models) == 1
    col = models[0].columns[0]
    assert col.name == "name"
    assert col.python_type == "String"
    assert col.sql_type == "String(100)"
    assert col.nullable is False
    assert col.max_length == 100


# ── Test 3: Mapped[str | None] nullable ───────────────────────────────────────

def test_mapped_str_none_is_nullable():
    source = _src("""\
class User(Base):
    __tablename__ = "users"
    bio: Mapped[str | None] = mapped_column(Text)
""")
    models = parse(source)
    assert len(models) == 1
    col = models[0].columns[0]
    assert col.name == "bio"
    assert col.nullable is True


# ── Test 4: Optional[str] nullable ────────────────────────────────────────────

def test_optional_str_is_nullable():
    source = _src("""\
class User(Base):
    __tablename__ = "users"
    nickname: Mapped[Optional[str]] = mapped_column(String(30))
""")
    models = parse(source)
    assert len(models) == 1
    col = models[0].columns[0]
    assert col.name == "nickname"
    assert col.python_type == "String"
    assert col.nullable is True


# ── Test 5: Column(Integer, primary_key=True) classic style ───────────────────

def test_classic_column_integer_primary_key():
    source = _src("""\
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
""")
    models = parse(source)
    assert len(models) == 1
    cols = {c.name: c for c in models[0].columns}
    assert "id" in cols
    assert cols["id"].python_type == "Integer"
    assert cols["id"].primary_key is True
    assert "email" in cols
    assert cols["email"].unique is True
    assert cols["email"].nullable is False


# ── Test 6: ForeignKey detection ──────────────────────────────────────────────

def test_foreign_key_detection():
    source = _src("""\
class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
""")
    models = parse(source)
    assert len(models) == 1
    cols = {c.name: c for c in models[0].columns}
    assert cols["user_id"].foreign_key == "users.id"
    assert cols["id"].foreign_key is None


# ── Test 7: __tablename__ extraction ─────────────────────────────────────────

def test_tablename_extraction():
    source = _src("""\
class MyModel(Base):
    __tablename__ = "my_custom_table"
    id: Mapped[int] = mapped_column(primary_key=True)
""")
    models = parse(source)
    assert len(models) == 1
    assert models[0].tablename == "my_custom_table"
    assert models[0].name == "MyModel"


# ── Test 8: server_default detection ─────────────────────────────────────────

def test_server_default_detection():
    source = _src("""\
class User(Base):
    __tablename__ = "users"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
""")
    models = parse(source)
    assert len(models) == 1
    col = models[0].columns[0]
    assert col.name == "created_at"
    assert col.server_default is not None
    assert "now" in col.server_default


# ── Test 9: Multiple models in one file ───────────────────────────────────────

def test_multiple_models_in_one_file():
    source = _src(
        """\
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
""",
        """\
class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
""",
        """\
class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str] = mapped_column(Text)
""",
    )
    models = parse(source)
    assert len(models) == 3
    tablenames = {m.tablename for m in models}
    assert tablenames == {"users", "posts", "comments"}


# ── Test 10: Base inheritance check — ignore non-Base classes ─────────────────

def test_ignore_non_base_classes():
    source = _src("""\
class NotAModel:
    some_attr = "value"


class AlsoNotAModel:
    def helper(self) -> None:
        pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
""")
    models = parse(source)
    assert len(models) == 1
    assert models[0].name == "User"


# ── Test 11: TimestampMixin with created_at / updated_at ──────────────────────

def test_timestamp_mixin_columns_inherited():
    source = _src("""\
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50))
""")
    models = parse(source)
    assert len(models) == 1
    model = models[0]
    assert model.name == "User"

    col_names = [c.name for c in model.columns]
    assert "created_at" in col_names
    assert "updated_at" in col_names
    assert "id" in col_names
    assert "username" in col_names
    assert len(col_names) == 4

    cols = {c.name: c for c in model.columns}
    assert cols["updated_at"].nullable is True
    assert cols["created_at"].server_default is not None
    assert cols["id"].primary_key is True


# ── Test 12: Multiple mixins in one model ─────────────────────────────────────

def test_multiple_mixin_inheritance():
    source = _src("""\
class AuditMixin:
    created_by: Mapped[str | None] = mapped_column(String(100))


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)


class Post(Base, AuditMixin, TimestampMixin):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
""")
    models = parse(source)
    assert len(models) == 1
    model = models[0]

    col_names = [c.name for c in model.columns]
    assert "created_by" in col_names
    assert "created_at" in col_names
    assert "updated_at" in col_names
    assert "id" in col_names
    assert "title" in col_names
    assert len(col_names) == 5

    cols = {c.name: c for c in model.columns}
    assert cols["created_by"].nullable is True


# ── Test 13: Edge cases — empty file, import-only file ────────────────────────

def test_empty_source_returns_empty_list():
    assert parse("") == []
    assert parse("   \n\n  ") == []


def test_import_only_file_returns_empty_list():
    source = """\
from __future__ import annotations
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
"""
    assert parse(source) == []


def test_invalid_syntax_raises_parse_error():
    with pytest.raises(ParseError, match="Syntax error"):
        parse("class Broken(:\n    pass\n")


# ── Bonus: child column overrides mixin column ────────────────────────────────

def test_child_column_overrides_mixin():
    source = _src("""\
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
""")
    models = parse(source)
    assert len(models) == 1
    cols = {c.name: c for c in models[0].columns}
    # Child's created_at (with server_default) wins
    assert cols["created_at"].server_default is not None


# ── Bonus: relationship fields are not treated as columns ─────────────────────

def test_relationships_excluded_from_columns():
    source = _src("""\
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    posts: Mapped[list[Post]] = relationship("Post", back_populates="author")
    profile: Mapped[Profile] = relationship("Profile", uselist=False)


class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
""")
    models = parse(source)
    assert len(models) == 3
    user = next(m for m in models if m.name == "User")
    col_names = [c.name for c in user.columns]
    assert col_names == ["id"]  # No posts or profile


# ── Fixture file integration ──────────────────────────────────────────────────

def test_parse_fastapi_basic_fixture():
    fixture_path = (
        Path(__file__).parent.parent.parent
        / "fixtures"
        / "fastapi_basic"
        / "app"
        / "models.py"
    )
    if not fixture_path.exists():
        pytest.skip("fixtures/fastapi_basic/app/models.py not found")

    models = SQLAlchemyParser().parse_file(fixture_path)
    assert len(models) >= 3

    tablenames = {m.tablename for m in models}
    assert "users" in tablenames
    assert "products" in tablenames
    assert "orders" in tablenames

    user = next(m for m in models if m.tablename == "users")
    col_names = [c.name for c in user.columns]
    assert "id" in col_names
    assert "email" in col_names

    # id should be primary key
    id_col = next(c for c in user.columns if c.name == "id")
    assert id_col.primary_key is True
    assert id_col.nullable is False
