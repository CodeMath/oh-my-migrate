"""RLS preset definitions: Supabase and PostgreSQL-native presets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RLSPreset:
    """A reusable RLS policy template."""

    name: str
    description: str
    using_template: str
    with_check_template: str | None = None
    default_owner_column: str = "user_id"
    requires_role: str | None = None
    requires_supabase: bool = False


SUPABASE_PRESETS: dict[str, RLSPreset] = {
    "owner": RLSPreset(
        name="owner",
        description="Row owner can SELECT/UPDATE/DELETE their own rows",
        using_template="auth.uid() = {owner_column}",
        with_check_template="auth.uid() = {owner_column}",
        requires_supabase=True,
    ),
    "public_read": RLSPreset(
        name="public_read",
        description="Anyone can SELECT, only owner can modify",
        using_template="true",
        requires_supabase=False,
    ),
    "authenticated": RLSPreset(
        name="authenticated",
        description="Any authenticated user can access",
        using_template="auth.role() = 'authenticated'",
        requires_role="authenticated",
        requires_supabase=True,
    ),
    "admin_only": RLSPreset(
        name="admin_only",
        description="Only service_role can access",
        using_template="auth.role() = 'service_role'",
        requires_role="service_role",
        requires_supabase=True,
    ),
    "team": RLSPreset(
        name="team",
        description="Team members can access shared rows",
        using_template=(
            "auth.uid() IN ("
            "SELECT user_id FROM team_members WHERE team_id = {table}.team_id"
            ")"
        ),
        requires_supabase=True,
    ),
}

PG_NATIVE_PRESETS: dict[str, RLSPreset] = {
    "owner": RLSPreset(
        name="owner",
        description="Row owner can access (PG native: current_user)",
        using_template="current_user = {owner_column}",
        with_check_template="current_user = {owner_column}",
        requires_supabase=False,
    ),
    "public_read": RLSPreset(
        name="public_read",
        description="Anyone can SELECT",
        using_template="true",
        requires_supabase=False,
    ),
    "authenticated": RLSPreset(
        name="authenticated",
        description="Any authenticated (logged-in) user can access (PG native: session_user check)",
        using_template="session_user IS NOT NULL",
        requires_supabase=False,
    ),
    "admin_only": RLSPreset(
        name="admin_only",
        description="Only superuser/admin role can access",
        using_template="current_user = current_setting('app.admin_role', true)",
        requires_supabase=False,
    ),
}


def get_presets(is_supabase: bool) -> dict[str, RLSPreset]:
    """Return appropriate preset dict based on environment."""
    return SUPABASE_PRESETS if is_supabase else PG_NATIVE_PRESETS
