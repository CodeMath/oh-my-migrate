"""AST helper functions for parsing SQLAlchemy models."""

from __future__ import annotations

import ast
from typing import Any

PYTHON_TYPE_MAP: dict[str, str] = {
    "int": "Integer",
    "str": "String",
    "float": "Float",
    "bool": "Boolean",
    "datetime": "DateTime",
    "date": "Date",
    "Decimal": "Numeric",
    "bytes": "LargeBinary",
    "UUID": "UUID",
    "uuid": "UUID",
}


def get_node_name(node: ast.expr) -> str | None:
    """Get the identifier name from a Name or Attribute node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def extract_string_value(node: ast.expr) -> str | None:
    """Extract a string literal from a Constant node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract_call_name(node: ast.expr) -> str | None:
    """Get the function/class name from a Call node."""
    if isinstance(node, ast.Call):
        return get_node_name(node.func)
    return None


def extract_mapped_type(annotation: ast.expr) -> tuple[str, bool]:
    """Parse Mapped[T], Mapped[T | None], Optional[T], T | None, or bare T.

    Returns (python_type_name, nullable).
    Handles both SQLAlchemy Mapped[] and SQLModel bare type annotations.
    """
    if isinstance(annotation, ast.Subscript) and get_node_name(annotation.value) == "Mapped":
        return _parse_inner_type(annotation.slice)
    # Bare T | None (union syntax) — SQLModel style
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        if _is_none_constant(annotation.right):
            return _parse_base_type(annotation.left), True
        if _is_none_constant(annotation.left):
            return _parse_base_type(annotation.right), True
        return _parse_base_type(annotation.left), False
    # Optional[T] without Mapped wrapper
    if isinstance(annotation, ast.Subscript) and get_node_name(annotation.value) == "Optional":
        return _parse_base_type(annotation.slice), True
    # Bare type name: str, int, etc.
    type_name = get_node_name(annotation)
    if type_name:
        return PYTHON_TYPE_MAP.get(type_name, type_name), False
    return "String", False


def _parse_inner_type(node: ast.expr) -> tuple[str, bool]:
    """Parse the type inside Mapped[...], returning (type_name, nullable)."""
    # Optional[T]
    if isinstance(node, ast.Subscript) and get_node_name(node.value) == "Optional":
        return _parse_base_type(node.slice), True

    # T | None  (union syntax)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        if _is_none_constant(node.right):
            return _parse_base_type(node.left), True
        if _is_none_constant(node.left):
            return _parse_base_type(node.right), True
        return _parse_base_type(node.left), False

    # Plain T
    return _parse_base_type(node), False


def _is_none_constant(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _parse_base_type(node: ast.expr) -> str:
    """Convert a type AST node to a SQLAlchemy type name string."""
    if isinstance(node, ast.Name):
        return PYTHON_TYPE_MAP.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return PYTHON_TYPE_MAP.get(node.attr, node.attr)
    if isinstance(node, ast.Subscript):
        return _parse_base_type(node.value)
    return "String"


def extract_column_kwargs(call: ast.Call) -> dict[str, Any]:
    """Extract column properties from mapped_column(), Column(), or Field() call.

    Returns a dict with any of: sql_type, primary_key, nullable, unique,
    foreign_key, default, server_default, max_length.
    """
    result: dict[str, Any] = {}

    for arg in call.args:
        _process_positional_arg(arg, result)

    for kw in call.keywords:
        if kw.arg is None:
            continue
        _process_keyword_arg(kw.arg, kw.value, result)

    return result


def _process_positional_arg(arg: ast.expr, result: dict[str, Any]) -> None:
    """Process a positional argument of Column() or mapped_column()."""
    call_name = extract_call_name(arg)

    # ForeignKey("table.column")
    if call_name == "ForeignKey" and isinstance(arg, ast.Call) and arg.args:
        fk_val = extract_string_value(arg.args[0])
        if fk_val:
            result["foreign_key"] = fk_val
        return

    # Type call: String(100), Numeric(10, 2), etc.
    if isinstance(arg, ast.Call) and call_name and _is_sqla_type(call_name):
        result["sql_type"] = _format_type_call(call_name, arg)
        _maybe_extract_max_length(call_name, arg, result)
        return

    # Bare type name: Integer, Boolean, Text, etc.
    if isinstance(arg, ast.Name) and _is_sqla_type(arg.id):
        result["sql_type"] = arg.id
        return

    if isinstance(arg, ast.Attribute) and _is_sqla_type(arg.attr):
        result["sql_type"] = arg.attr
        return


def _process_keyword_arg(key: str, val: ast.expr, result: dict[str, Any]) -> None:
    """Process a keyword argument of Column() or mapped_column()."""
    if key == "primary_key":
        result["primary_key"] = _extract_bool(val)
    elif key == "nullable":
        result["nullable"] = _extract_bool(val)
    elif key == "unique":
        result["unique"] = _extract_bool(val)
    elif key == "default":
        s = _extract_value_str(val)
        if s is not None:
            result["default"] = s
    elif key == "server_default":
        s = _extract_value_str(val)
        if s is not None:
            result["server_default"] = s
    elif key == "max_length":
        if isinstance(val, ast.Constant) and isinstance(val.value, int):
            result["max_length"] = val.value
    elif key == "foreign_key":
        s = _extract_value_str(val)
        if s is not None:
            result["foreign_key"] = s
    # onupdate and other kwargs are ignored


def _is_sqla_type(name: str) -> bool:
    """Return True if name is a recognized SQLAlchemy column type."""
    return name in {
        "Integer", "BigInteger", "SmallInteger", "String", "Text",
        "Boolean", "Float", "Numeric", "Decimal", "DateTime", "Date",
        "Time", "Interval", "LargeBinary", "JSON", "JSONB", "UUID",
        "Enum", "ARRAY", "VARCHAR", "CHAR", "TIMESTAMP", "SERIAL",
    }


def _format_type_call(type_name: str, call: ast.Call) -> str:
    """Format a type call like String(100) → 'String(100)'."""
    parts: list[str] = []
    for arg in call.args:
        if isinstance(arg, ast.Constant):
            parts.append(str(arg.value))
    for kw in call.keywords:
        if kw.arg and isinstance(kw.value, ast.Constant):
            parts.append(f"{kw.arg}={kw.value.value!r}")
    return f"{type_name}({', '.join(parts)})" if parts else type_name


def _maybe_extract_max_length(type_name: str, call: ast.Call, result: dict[str, Any]) -> None:
    """Extract max_length from String(N) or VARCHAR(N) calls."""
    if type_name in ("String", "VARCHAR") and call.args:
        first = call.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, int):
            result["max_length"] = first.value


def _extract_bool(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return bool(node.value)
    return False


def _extract_value_str(node: ast.expr) -> str | None:
    """Extract a string representation of a simple value node."""
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Call):
        name = extract_call_name(node)
        return f"{name}()" if name else None
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
