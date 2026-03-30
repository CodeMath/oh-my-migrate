"""Supabase environment detection."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

SUPABASE_ROLES: dict[str, str] = {
    "anon": "Unauthenticated users (public API)",
    "authenticated": "Logged-in users (after auth)",
    "service_role": "Backend service (bypasses RLS by default)",
}


class SupabaseDetector:
    """Supabase environment detection with two-stage confirmation."""

    @staticmethod
    def detect_by_url(db_url: str) -> bool:
        """Stage 1: URL pattern check (fast, no DB connection)."""
        return bool(re.search(r"supabase\.(com|co|io)", db_url))

    @staticmethod
    def confirm_by_roles(engine: Engine) -> bool:
        """Stage 2: Runtime confirmation via pg_roles query."""
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT EXISTS("
                    "SELECT 1 FROM pg_roles WHERE rolname = 'authenticated'"
                    ")"
                )
            ).scalar()
        return bool(result)

    @classmethod
    def is_supabase(cls, db_url: str, engine: Engine | None = None) -> bool:
        """Two-stage Supabase detection.

        1. URL pattern match (fast)
        2. If URL matches OR engine provided, confirm with pg_roles query
        3. If URL does not match and no engine, return False
        """
        url_match = cls.detect_by_url(db_url)
        if not url_match and engine is None:
            return False
        if engine is not None:
            return cls.confirm_by_roles(engine)
        return url_match
