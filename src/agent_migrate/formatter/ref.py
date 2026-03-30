"""RefEngine — assign and look up @m1/@d1/@v1 refs."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_migrate.types import DBTableSchema, ModelSchema


class RefType(Enum):
    MODEL = "m"    # @m1, @m2, …
    TABLE = "d"    # @d1, @d2, …  (database)
    VERSION = "v"  # @v1, @v2, …


class RefMap:
    """Bidirectional ref↔object mapping.

    Forward:  resolve("@m1") → ModelSchema
    Reverse:  get_ref(model) → "@m1"
    Lookup:   find_model_ref("users") → "@m1"   (by tablename)
              find_table_ref("users") → "@d1"   (by table name)
    """

    def __init__(self) -> None:
        self._refs: dict[str, tuple[RefType, Any]] = {}
        self._obj_to_ref: dict[Any, str] = {}

    def add(self, ref: str, ref_type: RefType, obj: Any) -> None:
        self._refs[ref] = (ref_type, obj)
        self._obj_to_ref[obj] = ref

    def resolve(self, ref: str) -> Any | None:
        """Return the object for *ref*, or None if unknown."""
        entry = self._refs.get(ref)
        return entry[1] if entry is not None else None

    def get_ref(self, obj: Any) -> str | None:
        """Return the ref string assigned to *obj*, or None."""
        return self._obj_to_ref.get(obj)

    def find_model_ref(self, tablename: str) -> str | None:
        """Find the @mN ref for the model whose tablename matches."""
        for ref, (rtype, obj) in self._refs.items():
            if rtype == RefType.MODEL and getattr(obj, "tablename", None) == tablename:
                return ref
        return None

    def find_table_ref(self, name: str) -> str | None:
        """Find the @dN ref for the DB table whose name matches."""
        for ref, (rtype, obj) in self._refs.items():
            if rtype == RefType.TABLE and getattr(obj, "name", None) == name:
                return ref
        return None

    def all_refs(self, ref_type: RefType | None = None) -> list[str]:
        """Return all ref strings, optionally filtered by type."""
        if ref_type is None:
            return list(self._refs)
        return [r for r, (t, _) in self._refs.items() if t == ref_type]


class RefEngine:
    """Assign @mN / @dN refs to models and tables in list order."""

    def assign(
        self,
        models: list[ModelSchema],
        tables: list[DBTableSchema],
    ) -> RefMap:
        ref_map = RefMap()
        for i, model in enumerate(models, start=1):
            ref_map.add(f"@m{i}", RefType.MODEL, model)
        for i, table in enumerate(tables, start=1):
            ref_map.add(f"@d{i}", RefType.TABLE, table)
        return ref_map
