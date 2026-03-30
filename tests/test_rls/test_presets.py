"""Tests for RLS preset system: presets, resolver, supabase detection."""

from __future__ import annotations

import pytest

from agent_migrate.exceptions import ConfigError
from agent_migrate.rls.presets import (
    PG_NATIVE_PRESETS,
    SUPABASE_PRESETS,
    get_presets,
)
from agent_migrate.rls.resolver import PresetResolver
from agent_migrate.rls.supabase import SupabaseDetector
from agent_migrate.types import RLSCommand


class TestPresets:
    def test_supabase_presets_keys(self) -> None:
        assert set(SUPABASE_PRESETS.keys()) == {
            "owner", "public_read", "authenticated", "admin_only", "team",
        }

    def test_pg_native_presets_keys(self) -> None:
        assert set(PG_NATIVE_PRESETS.keys()) == {
            "owner", "public_read", "authenticated", "admin_only",
        }

    def test_get_presets_supabase(self) -> None:
        assert get_presets(is_supabase=True) is SUPABASE_PRESETS

    def test_get_presets_pg(self) -> None:
        assert get_presets(is_supabase=False) is PG_NATIVE_PRESETS

    def test_preset_is_frozen(self) -> None:
        preset = SUPABASE_PRESETS["owner"]
        with pytest.raises(AttributeError):
            preset.name = "other"  # type: ignore[misc]

    def test_supabase_owner_uses_auth_uid(self) -> None:
        assert "auth.uid()" in SUPABASE_PRESETS["owner"].using_template

    def test_pg_owner_uses_current_user(self) -> None:
        assert "current_user" in PG_NATIVE_PRESETS["owner"].using_template

    def test_supabase_presets_require_supabase(self) -> None:
        for name in ("owner", "authenticated", "admin_only", "team"):
            assert SUPABASE_PRESETS[name].requires_supabase is True

    def test_public_read_no_supabase_required(self) -> None:
        assert SUPABASE_PRESETS["public_read"].requires_supabase is False
        assert PG_NATIVE_PRESETS["public_read"].requires_supabase is False


class TestSupabaseDetector:
    def test_detect_supabase_com(self) -> None:
        assert SupabaseDetector.detect_by_url(
            "postgresql://db.abc.supabase.com:5432/postgres"
        ) is True

    def test_detect_supabase_co(self) -> None:
        assert SupabaseDetector.detect_by_url(
            "postgresql://db.xyz.supabase.co:6543/postgres"
        ) is True

    def test_detect_supabase_io(self) -> None:
        assert SupabaseDetector.detect_by_url(
            "postgresql://pooler.supabase.io/postgres"
        ) is True

    def test_not_supabase_localhost(self) -> None:
        assert SupabaseDetector.detect_by_url(
            "postgresql://localhost:5432/mydb"
        ) is False

    def test_not_supabase_custom_host(self) -> None:
        assert SupabaseDetector.detect_by_url(
            "postgresql://myhost.example.com/db"
        ) is False

    def test_is_supabase_no_engine_no_url_match(self) -> None:
        assert SupabaseDetector.is_supabase(
            "postgresql://localhost/db", None
        ) is False

    def test_is_supabase_url_match_no_engine(self) -> None:
        assert SupabaseDetector.is_supabase(
            "postgresql://db.abc.supabase.co/db", None
        ) is True


class TestPresetResolver:
    def test_resolve_pg_owner(self) -> None:
        resolver = PresetResolver()
        policies = resolver.resolve("posts", {"select": "owner"}, is_supabase=False)
        assert len(policies) == 1
        p = policies[0]
        assert p.name == "posts_select_owner"
        assert p.table_name == "posts"
        assert p.command == RLSCommand.SELECT
        assert "current_user" in p.using_expr

    def test_resolve_supabase_owner(self) -> None:
        resolver = PresetResolver()
        policies = resolver.resolve("posts", {"select": "owner"}, is_supabase=True)
        assert len(policies) == 1
        assert "auth.uid()" in policies[0].using_expr

    def test_resolve_multiple_commands(self) -> None:
        resolver = PresetResolver()
        policies = resolver.resolve(
            "posts",
            {"select": "owner", "insert": "authenticated"},
            is_supabase=False,
        )
        assert len(policies) == 2
        names = {p.name for p in policies}
        assert "posts_select_owner" in names
        assert "posts_insert_authenticated" in names

    def test_resolve_all_expands_to_four(self) -> None:
        resolver = PresetResolver()
        policies = resolver.resolve("posts", {"all": "owner"}, is_supabase=False)
        assert len(policies) == 4
        commands = {p.command for p in policies}
        assert commands == {
            RLSCommand.SELECT, RLSCommand.INSERT,
            RLSCommand.UPDATE, RLSCommand.DELETE,
        }

    def test_invalid_key_raises_config_error(self) -> None:
        resolver = PresetResolver()
        with pytest.raises(ConfigError, match="Invalid __rls__ keys"):
            resolver.resolve("posts", {"read": "owner"}, is_supabase=False)

    def test_supabase_preset_in_pg_raises_config_error(self) -> None:
        resolver = PresetResolver()
        with pytest.raises(ConfigError, match="requires Supabase"):
            resolver.resolve("posts", {"select": "team"}, is_supabase=False)

    def test_unknown_preset_raises_config_error(self) -> None:
        resolver = PresetResolver()
        with pytest.raises(ConfigError, match="Unknown RLS preset"):
            resolver.resolve("posts", {"select": "nonexistent"}, is_supabase=False)

    def test_policy_naming_convention(self) -> None:
        resolver = PresetResolver()
        policies = resolver.resolve(
            "users", {"delete": "admin_only"}, is_supabase=False
        )
        assert policies[0].name == "users_delete_admin_only"

    def test_owner_column_substitution(self) -> None:
        resolver = PresetResolver()
        policies = resolver.resolve(
            "posts", {"select": "owner"},
            is_supabase=False, owner_column="author_id",
        )
        assert "author_id" in policies[0].using_expr

    def test_with_check_expr_present_for_owner(self) -> None:
        resolver = PresetResolver()
        policies = resolver.resolve(
            "posts", {"insert": "owner"}, is_supabase=False
        )
        assert policies[0].with_check_expr is not None
