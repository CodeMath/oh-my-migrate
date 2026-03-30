"""SQLAlchemy 2.0 AST-based model parser."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Any

from agent_migrate.exceptions import ParseError
from agent_migrate.parser.ast_utils import (
    PYTHON_TYPE_MAP,
    extract_call_name,
    extract_column_kwargs,
    extract_mapped_type,
    extract_string_value,
    get_node_name,
)
from agent_migrate.types import ColumnSchema, ModelSchema

if TYPE_CHECKING:
    from pathlib import Path

# Class names that indicate a declarative base definition
_DECLARATIVE_BASE_NAMES: frozenset[str] = frozenset({
    "DeclarativeBase",
    "DeclarativeBaseNoMeta",
    "SQLModel",
})

# Legacy factory functions that return a Base class object
_DECLARATIVE_FACTORY_NAMES: frozenset[str] = frozenset({
    "declarative_base",
    "as_declarative",
})


def _has_table_true(class_def: ast.ClassDef) -> bool:
    """Check if class has table=True keyword (SQLModel pattern)."""
    for kw in class_def.keywords:
        if (
            kw.arg == "table"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
        ):
            return True
    return False


class SQLAlchemyParser:
    """AST-based parser for SQLAlchemy 2.0 Mapped + Classic style models.

    Supports:
    1. Mapped[T] = mapped_column(...)  (SQLAlchemy 2.0 style)
    2. Column(Type, ...)               (Classic style)
    3. __tablename__ extraction
    4. ForeignKey("table.column") detection
    5. Mapped[str | None] / Optional[str] → nullable=True
    6. server_default detection
    7. Same-file mixin inheritance (TimestampMixin pattern)
    8. Multiple models per file
    9. Ignores classes not inheriting from Base/DeclarativeBase
    10. __rls__ annotation extraction
    """

    def __init__(self) -> None:
        self._rls_raw: dict[str, dict[str, str]] = {}

    def parse_file(self, path: Path) -> list[ModelSchema]:
        """Parse all SQLAlchemy models from a Python file."""
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ParseError(f"Cannot read {path}: {exc}") from exc
        return self.parse_source(source, filename=str(path))

    def parse_source(self, source: str, filename: str = "<string>") -> list[ModelSchema]:
        """Parse all SQLAlchemy models from Python source code."""
        if not source.strip():
            return []
        try:
            tree = ast.parse(source, filename=filename)
        except SyntaxError as exc:
            raise ParseError(f"Syntax error in {filename}: {exc}") from exc

        class_defs = self._collect_class_definitions(tree)
        base_names = self._find_base_class_names(tree, class_defs)

        models: list[ModelSchema] = []
        for class_def in class_defs.values():
            if self._is_base_definition(class_def):
                continue
            if not self._inherits_from_base(class_def, base_names, class_defs, set()):
                continue
            model = self._parse_model_class(class_def, class_defs, filename)
            if model is not None:
                models.append(model)

        return models

    # ── Class discovery ────────────────────────────────────────────────────────

    def _collect_class_definitions(self, tree: ast.Module) -> dict[str, ast.ClassDef]:
        """Collect top-level class definitions in file order."""
        return {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
        }

    def _find_base_class_names(
        self,
        tree: ast.Module,
        class_defs: dict[str, ast.ClassDef],
    ) -> set[str]:
        """Return all names that refer to declarative base classes."""
        bases: set[str] = set(_DECLARATIVE_BASE_NAMES)

        # Classes inheriting directly from DeclarativeBase
        for name, class_def in class_defs.items():
            for base in class_def.bases:
                if get_node_name(base) in _DECLARATIVE_BASE_NAMES:
                    bases.add(name)

        # Module-level: Base = declarative_base()
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and extract_call_name(node.value) in _DECLARATIVE_FACTORY_NAMES
            ):
                for target in node.targets:
                    name_val = get_node_name(target)
                    if name_val:
                        bases.add(name_val)

        return bases

    def _is_base_definition(self, class_def: ast.ClassDef) -> bool:
        """Return True if this class IS the Base definition itself."""
        for base in class_def.bases:
            name = get_node_name(base)
            if name == "SQLModel":
                # SQLModel with table=True is a model, not a base
                return not _has_table_true(class_def)
            if name in _DECLARATIVE_BASE_NAMES:
                return True
        return False

    def _inherits_from_base(
        self,
        class_def: ast.ClassDef,
        base_names: set[str],
        class_defs: dict[str, ast.ClassDef],
        visited: set[str],
    ) -> bool:
        """Return True if class inherits from a known Base (directly or transitively)."""
        if class_def.name in visited:
            return False
        visited.add(class_def.name)

        for base in class_def.bases:
            base_name = get_node_name(base)
            if base_name in base_names:
                return True
            if base_name and base_name in class_defs and self._inherits_from_base(
                class_defs[base_name], base_names, class_defs, visited
            ):
                return True
        return False

    # ── Mixin merging ──────────────────────────────────────────────────────────

    def _merge_mixin_columns(
        self,
        class_def: ast.ClassDef,
        class_defs: dict[str, ast.ClassDef],
    ) -> list[ast.stmt]:
        """Merge same-file mixin column stmts into the model class body.

        Strategy:
        - Collect mixin columns (left-to-right base order)
        - Collect class body columns
        - Child columns override mixin columns on name conflict
        - Final order: mixin-only columns first, then child columns
        """
        mixin_stmts: dict[str, ast.stmt] = {}
        for base in class_def.bases:
            base_name = get_node_name(base)
            if base_name and base_name in class_defs:
                mixin_def = class_defs[base_name]
                if not self._is_base_definition(mixin_def):
                    for stmt in mixin_def.body:
                        col_name = self._get_col_name(stmt)
                        if col_name:
                            mixin_stmts[col_name] = stmt

        child_stmts: dict[str, ast.stmt] = {}
        for stmt in class_def.body:
            col_name = self._get_col_name(stmt)
            if col_name:
                child_stmts[col_name] = stmt

        # Mixin columns not overridden by child, then all child columns
        merged: dict[str, ast.stmt] = {}
        for name, stmt in mixin_stmts.items():
            if name not in child_stmts:
                merged[name] = stmt
        merged.update(child_stmts)

        return list(merged.values())

    def _get_col_name(self, stmt: ast.stmt) -> str | None:
        """Return the column name if this stmt defines a column; else None."""
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            if self._is_mapped_column_stmt(stmt):
                return stmt.target.id
            if self._is_sqlmodel_column_stmt(stmt):
                return stmt.target.id

        if (
            isinstance(stmt, ast.Assign)
            and isinstance(stmt.value, ast.Call)
            and extract_call_name(stmt.value) == "Column"
        ):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    return target.id

        return None

    def _is_mapped_column_stmt(self, stmt: ast.AnnAssign) -> bool:
        """Return True if this is a Mapped[T] column stmt (not a relationship)."""
        ann = stmt.annotation
        if not (
            isinstance(ann, ast.Subscript)
            and get_node_name(ann.value) == "Mapped"
        ):
            return False

        # Inner type must not be list[...] (relationship collection)
        inner = ann.slice
        if isinstance(inner, ast.Subscript) and get_node_name(inner.value) == "list":
            return False

        return not (
            stmt.value
            and isinstance(stmt.value, ast.Call)
            and extract_call_name(stmt.value) == "relationship"
        )

    # ── Model / column parsing ─────────────────────────────────────────────────

    def _parse_model_class(
        self,
        class_def: ast.ClassDef,
        class_defs: dict[str, ast.ClassDef],
        filename: str,
    ) -> ModelSchema | None:
        """Parse a SQLAlchemy model class into a ModelSchema."""
        tablename = self._extract_tablename(class_def)
        if tablename is None:
            return None

        all_stmts = self._merge_mixin_columns(class_def, class_defs)
        columns: list[ColumnSchema] = []
        for stmt in all_stmts:
            col = self._parse_column_stmt(stmt)
            if col is not None:
                columns.append(col)

        rls_raw = self._extract_rls(class_def)
        rls_opt_out = rls_raw is False
        if isinstance(rls_raw, dict):
            self._rls_raw[tablename] = rls_raw

        return ModelSchema(
            name=class_def.name,
            tablename=tablename,
            columns=tuple(columns),
            rls_opt_out=rls_opt_out,
            source_file=filename,
            source_line=class_def.lineno,
        )

    def _extract_tablename(self, class_def: ast.ClassDef) -> str | None:
        """Extract __tablename__ string from class body.

        For SQLModel classes with table=True, auto-generates from class name
        if __tablename__ is not explicitly defined.
        """
        for stmt in class_def.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == "__tablename__":
                        return extract_string_value(stmt.value)
        # SQLModel: auto-generate tablename from class name
        if _has_table_true(class_def):
            return class_def.name.lower()
        return None

    def _extract_rls(
        self, class_def: ast.ClassDef
    ) -> dict[str, str] | None | bool:
        """Extract __rls__ from class body.

        Returns:
            dict[str, str]: parsed __rls__ dict (e.g. {"select": "owner"})
            False: explicit opt-out (__rls__ = False)
            None: __rls__ not defined
        """
        for stmt in class_def.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == "__rls__":
                        if isinstance(stmt.value, ast.Constant) and stmt.value.value is False:
                            return False
                        return self._parse_dict_literal(stmt.value)
        return None

    def _parse_dict_literal(self, node: ast.expr) -> dict[str, str] | None:
        """Parse ast.Dict or dict() call into a Python dict."""
        if isinstance(node, ast.Dict):
            result: dict[str, str] = {}
            for key, value in zip(node.keys, node.values, strict=True):
                k = extract_string_value(key) if key else None
                v = extract_string_value(value)
                if k and v:
                    result[k] = v
            return result if result else None
        if isinstance(node, ast.Call) and extract_call_name(node) == "dict":
            result = {}
            for kw in node.keywords:
                if kw.arg and isinstance(kw.value, ast.Constant):
                    result[kw.arg] = extract_string_value(kw.value) or ""
            return result if result else None
        return None

    def _parse_column_stmt(self, stmt: ast.stmt) -> ColumnSchema | None:
        """Parse a column stmt into ColumnSchema; return None if not a column."""
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            if self._is_mapped_column_stmt(stmt):
                return self._parse_mapped_column(stmt)
            if self._is_sqlmodel_column_stmt(stmt):
                return self._parse_sqlmodel_column(stmt)

        if (
            isinstance(stmt, ast.Assign)
            and isinstance(stmt.value, ast.Call)
            and extract_call_name(stmt.value) == "Column"
        ):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    return self._parse_classic_column(target.id, stmt.value)

        return None

    def _is_sqlmodel_column_stmt(self, stmt: ast.AnnAssign) -> bool:
        """Return True if this is a SQLModel-style column (bare type + optional Field())."""
        ann = stmt.annotation
        # Already handled by _is_mapped_column_stmt
        if isinstance(ann, ast.Subscript) and get_node_name(ann.value) == "Mapped":
            return False
        # Bare type: str, int, float, etc.
        if isinstance(ann, ast.Name) and ann.id in PYTHON_TYPE_MAP:
            return True
        # T | None union
        if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
            return True
        # Optional[T]
        if isinstance(ann, ast.Subscript) and get_node_name(ann.value) == "Optional":
            return True
        # Field() value is a strong signal
        return bool(
            stmt.value
            and isinstance(stmt.value, ast.Call)
            and extract_call_name(stmt.value) == "Field"
        )

    def _parse_sqlmodel_column(self, stmt: ast.AnnAssign) -> ColumnSchema:
        """Parse a SQLModel-style column: name: str = Field(...)."""
        assert isinstance(stmt.target, ast.Name)
        col_name = stmt.target.id

        python_type, nullable = extract_mapped_type(stmt.annotation)

        kwargs: dict[str, Any] = {}
        if stmt.value and isinstance(stmt.value, ast.Call):
            call_name = extract_call_name(stmt.value)
            if call_name == "Field":
                kwargs = extract_column_kwargs(stmt.value)
        elif stmt.value and isinstance(stmt.value, ast.Constant):
            if stmt.value.value is None:
                nullable = True

        if "nullable" in kwargs:
            nullable = kwargs["nullable"]

        return ColumnSchema(
            name=col_name,
            python_type=python_type,
            sql_type=kwargs.get("sql_type"),
            nullable=nullable,
            primary_key=kwargs.get("primary_key", False),
            unique=kwargs.get("unique", False),
            foreign_key=kwargs.get("foreign_key"),
            default=kwargs.get("default"),
            server_default=kwargs.get("server_default"),
            max_length=kwargs.get("max_length"),
        )

    def _parse_mapped_column(self, stmt: ast.AnnAssign) -> ColumnSchema:
        """Parse a Mapped[T] = mapped_column(...) statement."""
        assert isinstance(stmt.target, ast.Name)
        col_name = stmt.target.id

        python_type, nullable = extract_mapped_type(stmt.annotation)

        kwargs: dict[str, Any] = {}
        if stmt.value and isinstance(stmt.value, ast.Call):
            call_name = extract_call_name(stmt.value)
            if call_name in ("mapped_column", "Column"):
                kwargs = extract_column_kwargs(stmt.value)

        # Explicit nullable= kwarg overrides annotation-derived value
        if "nullable" in kwargs:
            nullable = kwargs["nullable"]

        return ColumnSchema(
            name=col_name,
            python_type=python_type,
            sql_type=kwargs.get("sql_type"),
            nullable=nullable,
            primary_key=kwargs.get("primary_key", False),
            unique=kwargs.get("unique", False),
            foreign_key=kwargs.get("foreign_key"),
            default=kwargs.get("default"),
            server_default=kwargs.get("server_default"),
            max_length=kwargs.get("max_length"),
        )

    def _parse_classic_column(self, col_name: str, call: ast.Call) -> ColumnSchema:
        """Parse a name = Column(...) statement."""
        kwargs = extract_column_kwargs(call)

        sql_type = kwargs.get("sql_type", "String")
        python_type = sql_type.split("(")[0]  # "String(100)" → "String"

        # Classic style: nullable defaults to True unless specified
        nullable = kwargs.get("nullable", True)

        return ColumnSchema(
            name=col_name,
            python_type=python_type,
            sql_type=sql_type,
            nullable=nullable,
            primary_key=kwargs.get("primary_key", False),
            unique=kwargs.get("unique", False),
            foreign_key=kwargs.get("foreign_key"),
            default=kwargs.get("default"),
            server_default=kwargs.get("server_default"),
            max_length=kwargs.get("max_length"),
        )
