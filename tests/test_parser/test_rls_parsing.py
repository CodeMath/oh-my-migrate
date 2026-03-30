"""Tests for __rls__ AST parsing in the SQLAlchemy parser."""

from __future__ import annotations

from agent_migrate.parser.sqlalchemy import SQLAlchemyParser


class TestRLSParsing:
    def test_dict_literal(self) -> None:
        source = '''
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Post(Base):
    __tablename__ = "posts"
    __rls__ = {"select": "owner", "insert": "authenticated"}
    id: Mapped[int] = mapped_column(primary_key=True)
'''
        parser = SQLAlchemyParser()
        models = parser.parse_source(source)
        assert len(models) == 1
        assert models[0].rls_opt_out is False
        assert parser._rls_raw == {
            "posts": {"select": "owner", "insert": "authenticated"},
        }

    def test_dict_call_form(self) -> None:
        source = '''
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Post(Base):
    __tablename__ = "posts"
    __rls__ = dict(select="owner", update="admin_only")
    id: Mapped[int] = mapped_column(primary_key=True)
'''
        parser = SQLAlchemyParser()
        parser.parse_source(source)
        assert parser._rls_raw == {
            "posts": {"select": "owner", "update": "admin_only"},
        }

    def test_false_opt_out(self) -> None:
        source = '''
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class AuditLog(Base):
    __tablename__ = "audit_logs"
    __rls__ = False
    id: Mapped[int] = mapped_column(primary_key=True)
'''
        parser = SQLAlchemyParser()
        models = parser.parse_source(source)
        assert len(models) == 1
        assert models[0].rls_opt_out is True
        assert "audit_logs" not in parser._rls_raw

    def test_no_rls_defined(self) -> None:
        source = '''
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
'''
        parser = SQLAlchemyParser()
        models = parser.parse_source(source)
        assert len(models) == 1
        assert models[0].rls_opt_out is False
        assert models[0].rls_policies == ()
        assert "users" not in parser._rls_raw

    def test_dynamic_expression_returns_none(self) -> None:
        source = '''
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Post(Base):
    __tablename__ = "posts"
    __rls__ = get_rls_config("posts")
    id: Mapped[int] = mapped_column(primary_key=True)
'''
        parser = SQLAlchemyParser()
        models = parser.parse_source(source)
        assert len(models) == 1
        assert models[0].rls_opt_out is False
        assert "posts" not in parser._rls_raw

    def test_multiple_models_with_rls(self) -> None:
        source = '''
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Post(Base):
    __tablename__ = "posts"
    __rls__ = {"select": "owner"}
    id: Mapped[int] = mapped_column(primary_key=True)

class Comment(Base):
    __tablename__ = "comments"
    __rls__ = {"all": "authenticated"}
    id: Mapped[int] = mapped_column(primary_key=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    __rls__ = False
    id: Mapped[int] = mapped_column(primary_key=True)
'''
        parser = SQLAlchemyParser()
        models = parser.parse_source(source)
        assert len(models) == 3
        assert parser._rls_raw == {
            "posts": {"select": "owner"},
            "comments": {"all": "authenticated"},
        }
        audit = next(m for m in models if m.tablename == "audit_logs")
        assert audit.rls_opt_out is True
