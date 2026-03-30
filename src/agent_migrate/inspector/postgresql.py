"""PostgreSQL DB Inspector using information_schema."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from sqlalchemy import text

from agent_migrate.types import (
    DBColumnSchema,
    DBRLSPolicy,
    DBRLSStatus,
    DBRoleInfo,
    DBTableSchema,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


class PostgreSQLInspector:
    """PostgreSQL information_schema-based DB Inspector.

    Queries:
    1. information_schema.tables + columns JOIN  →  table/column info
    2. table_constraints + key_column_usage + constraint_column_usage  →  PK, FK, UNIQUE
    3. pg_class.reltuples  →  approximate row count

    All queries use SQLAlchemy text() with bound parameters. No f-string SQL.
    Table/column names from information_schema are values, not SQL identifiers,
    so they need no quoting in the main inspect query.
    get_column_values() uses explicit double-quoting for dynamic identifiers.
    """

    def inspect(self, engine: Engine, schema: str = "public") -> list[DBTableSchema]:
        """Inspect and return all user tables in the given schema."""
        with engine.connect() as conn:
            # 1. Columns
            col_rows = conn.execute(
                text("""
                    SELECT
                        t.table_name,
                        c.column_name,
                        c.data_type,
                        c.is_nullable,
                        c.column_default,
                        c.character_maximum_length,
                        c.ordinal_position
                    FROM information_schema.tables t
                    JOIN information_schema.columns c
                        ON t.table_schema = c.table_schema
                        AND t.table_name = c.table_name
                    WHERE t.table_schema = :schema
                        AND t.table_type = 'BASE TABLE'
                    ORDER BY t.table_name, c.ordinal_position
                """),
                {"schema": schema},
            ).fetchall()

            if not col_rows:
                return []

            # 2. Constraints (PK, UNIQUE, FK)
            constraint_rows = conn.execute(
                text("""
                    SELECT
                        tc.table_name,
                        kcu.column_name,
                        tc.constraint_type,
                        ccu.table_name  AS foreign_table,
                        ccu.column_name AS foreign_column
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema  = kcu.table_schema
                    LEFT JOIN information_schema.constraint_column_usage ccu
                        ON tc.constraint_name = ccu.constraint_name
                        AND tc.table_schema  = ccu.table_schema
                    WHERE tc.table_schema = :schema
                        AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY')
                    ORDER BY tc.table_name, kcu.column_name
                """),
                {"schema": schema},
            ).fetchall()

            # 3. Row counts via pg_class.reltuples (all tables in schema, one query)
            rc_rows = conn.execute(
                text("""
                    SELECT c.relname, c.reltuples::bigint
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = :schema
                        AND c.relkind = 'r'
                """),
                {"schema": schema},
            ).fetchall()

        # Build constraint maps
        pk_cols: dict[str, set[str]] = defaultdict(set)
        unique_cols: dict[str, set[str]] = defaultdict(set)
        fk_map: dict[tuple[str, str], tuple[str, str]] = {}

        for row in constraint_rows:
            tbl, col, ctype, ftbl, fcol = row
            if ctype == "PRIMARY KEY":
                pk_cols[tbl].add(col)
            elif ctype == "UNIQUE":
                unique_cols[tbl].add(col)
            elif ctype == "FOREIGN KEY" and ftbl and fcol:
                fk_map[(tbl, col)] = (ftbl, fcol)

        # Row count lookup (reltuples = -1 means no stats yet → treat as 0)
        row_counts: dict[str, int] = {
            name: max(0, int(cnt)) for name, cnt in rc_rows if cnt is not None
        }

        # Group column rows by table (preserves ordinal_position order)
        tables_cols: dict[str, list[tuple[str, ...]]] = defaultdict(list)
        for row in col_rows:
            tbl_name, col_name, data_type, is_nullable, col_default, char_max_len, _ = row
            tables_cols[tbl_name].append(
                (col_name, data_type, is_nullable, col_default, char_max_len)
            )

        # Build DBTableSchema list
        result: list[DBTableSchema] = []
        for tbl_name, columns in tables_cols.items():
            db_cols = tuple(
                DBColumnSchema(
                    name=col_name,
                    data_type=data_type,
                    is_nullable=(is_nullable == "YES"),
                    column_default=col_default,
                    character_maximum_length=(
                        int(char_max_len) if char_max_len is not None else None
                    ),
                    is_primary_key=(col_name in pk_cols[tbl_name]),
                    is_unique=(col_name in unique_cols[tbl_name]),
                    foreign_table=(fk := fk_map.get((tbl_name, col_name), (None, None)))[0],
                    foreign_column=fk[1],
                )
                for col_name, data_type, is_nullable, col_default, char_max_len in columns
            )
            result.append(
                DBTableSchema(
                    name=tbl_name,
                    schema_name=schema,
                    columns=db_cols,
                    row_count=row_counts.get(tbl_name, 0),
                )
            )

        return sorted(result, key=lambda t: t.name)

    def get_row_count(self, engine: Engine, table_name: str) -> int:
        """Approximate row count for *table_name* via pg_class.reltuples."""
        stmt = text("""
            SELECT reltuples::bigint
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
            AND   c.relname = :table_name
        """)
        with engine.connect() as conn:
            row = conn.execute(stmt, {"table_name": table_name}).fetchone()
        if row is None or row[0] is None:
            return 0
        return max(0, int(row[0]))

    def get_column_values(
        self, engine: Engine, table_name: str, column_name: str
    ) -> list[str]:
        """Return distinct non-NULL values of *column_name* in *table_name*.

        Identifiers are double-quoted (with internal double-quote escaping) to
        handle reserved words and special characters safely.
        """
        q_tbl = '"' + table_name.replace('"', '""') + '"'
        q_col = '"' + column_name.replace('"', '""') + '"'
        stmt = text(
            "SELECT DISTINCT "
            + q_col
            + " FROM public."
            + q_tbl
            + " WHERE "
            + q_col
            + " IS NOT NULL ORDER BY 1"
        )
        with engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [str(row[0]) for row in rows]

    def inspect_rls(
        self, engine: Engine, schema: str = "public"
    ) -> tuple[list[DBRLSStatus], list[DBRLSPolicy]]:
        """Inspect RLS status and policies for all tables in schema."""
        with engine.connect() as conn:
            # RLS status (pg_class)
            rls_rows = conn.execute(
                text("""
                    SELECT c.relname,
                           c.relrowsecurity,
                           c.relforcerowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = :schema
                      AND c.relkind = 'r'
                """),
                {"schema": schema},
            ).fetchall()

            # RLS policies (pg_policies view)
            try:
                policy_rows = conn.execute(
                    text("""
                        SELECT policyname, tablename, schemaname,
                               cmd, permissive, roles,
                               qual, with_check
                        FROM pg_policies
                        WHERE schemaname = :schema
                    """),
                    {"schema": schema},
                ).fetchall()
            except Exception:  # noqa: BLE001
                # pg_policies view may not exist in PostgreSQL < 10
                policy_rows = []

        statuses = [
            DBRLSStatus(
                table_name=row[0],
                schema_name=schema,
                rls_enabled=bool(row[1]),
                rls_forced=bool(row[2]),
            )
            for row in rls_rows
        ]

        policies = [
            DBRLSPolicy(
                policy_name=row[0],
                table_name=row[1],
                schema_name=row[2],
                command=row[3] or "ALL",
                permissive=row[4] or "PERMISSIVE",
                roles=tuple(
                    r.strip("{} ")
                    for r in (
                        row[5] if isinstance(row[5], (list, tuple))
                        else str(row[5]).split(",")
                    )
                    if r.strip("{} ")
                ),
                using_qual=row[6],
                with_check_qual=row[7],
            )
            for row in policy_rows
        ]

        return statuses, policies

    def inspect_roles(
        self, engine: Engine, schema: str = "public"
    ) -> list[DBRoleInfo]:
        """Inspect roles with grants on the given schema."""
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT DISTINCT r.rolname, r.rolsuper, r.rolcanlogin,
                           r.rolcreaterole, r.rolcreatedb
                    FROM pg_roles r
                    WHERE r.rolname IN (
                        SELECT grantee FROM information_schema.role_table_grants
                        WHERE table_schema = :schema
                    )
                    OR r.rolname IN ('anon', 'authenticated', 'service_role')
                """),
                {"schema": schema},
            ).fetchall()

        return [
            DBRoleInfo(
                role_name=row[0],
                is_superuser=bool(row[1]),
                can_login=bool(row[2]),
                can_create_role=bool(row[3]),
                can_create_db=bool(row[4]),
            )
            for row in rows
        ]

    def inspect_grants(
        self, engine: Engine, schema: str = "public"
    ) -> dict[str, list[tuple[str, str]]]:
        """Return {table_name: [(role, privilege), ...]} from role_table_grants."""
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT table_name, grantee, privilege_type
                    FROM information_schema.role_table_grants
                    WHERE table_schema = :schema
                """),
                {"schema": schema},
            ).fetchall()

        result: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for row in rows:
            result[row[0]].append((row[1], row[2]))
        return dict(result)
