"""Core data types for agent-migrate.

All dataclasses are frozen (immutable) and use tuple[X, ...] for collections.
These types form the contract between all modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ── Model Schema (Parser output) ──


@dataclass(frozen=True)
class ColumnSchema:
    name: str
    python_type: str  # "String", "Integer", "Boolean", ...
    sql_type: str | None = None  # "VARCHAR(100)", "INTEGER", ...
    nullable: bool = True
    primary_key: bool = False
    unique: bool = False
    foreign_key: str | None = None  # "users.id"
    default: str | None = None
    server_default: str | None = None
    max_length: int | None = None
    enum_values: tuple[str, ...] | None = None


@dataclass(frozen=True)
class IndexSchema:
    name: str
    columns: tuple[str, ...]
    unique: bool = False


class RLSCommand(Enum):
    """PostgreSQL RLS policy command types."""
    ALL = "ALL"
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


VALID_RLS_COMMANDS: frozenset[str] = frozenset({"select", "insert", "update", "delete", "all"})


@dataclass(frozen=True)
class RLSPolicySchema:
    """Model-defined RLS policy (from __rls__ annotation)."""
    name: str
    table_name: str
    command: RLSCommand
    using_expr: str
    with_check_expr: str | None = None
    role: str = "PUBLIC"
    permissive: bool = True


@dataclass(frozen=True)
class RoleRequirement:
    """Model/config-defined role requirement."""
    role_name: str
    grants: tuple[str, ...]
    table_name: str
    is_supabase_builtin: bool = False


@dataclass(frozen=True)
class ModelSchema:
    name: str  # "User"
    tablename: str  # "users"
    columns: tuple[ColumnSchema, ...]
    indexes: tuple[IndexSchema, ...] = ()
    source_file: str = ""
    source_line: int = 0
    rls_policies: tuple[RLSPolicySchema, ...] = ()
    rls_opt_out: bool = False
    role_requirements: tuple[RoleRequirement, ...] = ()


# ── DB Schema (Inspector output) ──


@dataclass(frozen=True)
class DBColumnSchema:
    name: str
    data_type: str  # "character varying", "integer", ...
    is_nullable: bool
    column_default: str | None = None
    character_maximum_length: int | None = None
    is_primary_key: bool = False
    is_unique: bool = False
    foreign_table: str | None = None
    foreign_column: str | None = None


@dataclass(frozen=True)
class DBTableSchema:
    name: str
    schema_name: str  # "public"
    columns: tuple[DBColumnSchema, ...]
    row_count: int = 0
    size_bytes: int = 0
    rls_enabled: bool = False
    rls_forced: bool = False


@dataclass(frozen=True)
class DBRLSPolicy:
    """RLS policy as read from pg_policies."""
    policy_name: str
    table_name: str
    schema_name: str
    command: str
    permissive: str
    roles: tuple[str, ...]
    using_qual: str | None
    with_check_qual: str | None


@dataclass(frozen=True)
class DBRLSStatus:
    """RLS enablement status for a table."""
    table_name: str
    schema_name: str
    rls_enabled: bool
    rls_forced: bool


@dataclass(frozen=True)
class DBRoleInfo:
    """Role as read from pg_roles."""
    role_name: str
    is_superuser: bool
    can_login: bool
    can_create_role: bool
    can_create_db: bool


# ── Diff Types ──


class DiffType(Enum):
    TABLE_ADDED = "table_added"
    TABLE_REMOVED = "table_removed"
    COLUMN_ADDED = "column_added"
    COLUMN_REMOVED = "column_removed"
    COLUMN_TYPE_CHANGED = "column_type_changed"
    COLUMN_NULLABLE_CHANGED = "column_nullable_changed"
    COLUMN_DEFAULT_CHANGED = "column_default_changed"
    ENUM_VALUES_CHANGED = "enum_values_changed"
    FK_ADDED = "fk_added"
    FK_REMOVED = "fk_removed"
    INDEX_ADDED = "index_added"
    INDEX_REMOVED = "index_removed"
    RLS_ENABLED_CHANGED = "rls_enabled_changed"
    RLS_POLICY_ADDED = "rls_policy_added"
    RLS_POLICY_REMOVED = "rls_policy_removed"
    RLS_POLICY_CHANGED = "rls_policy_changed"
    RLS_POLICY_UNTRACKED = "rls_policy_untracked"
    ROLE_MISSING = "role_missing"
    GRANT_ADDED = "grant_added"
    GRANT_REMOVED = "grant_removed"


class RiskLevel(Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGER = "danger"


@dataclass(frozen=True)
class DiffItem:
    diff_type: DiffType
    table_name: str
    column_name: str | None = None
    risk: RiskLevel = RiskLevel.SAFE
    description: str = ""
    model_value: str | None = None
    db_value: str | None = None
    affected_rows: int | None = None


@dataclass(frozen=True)
class RiskAssessment:
    risk: RiskLevel
    reason: str = ""
    affected_rows: int = 0
    recommendation: str | None = None


# ── Migration Types ──


@dataclass(frozen=True)
class MigrationStep:
    sql: str
    risk: RiskLevel
    description: str
    rollback_sql: str | None = None
    affected_rows: int | None = None


@dataclass(frozen=True)
class MigrationPlan:
    steps: tuple[MigrationStep, ...]
    overall_risk: RiskLevel
    message: str = ""
