"""Shared pytest fixtures for agent-migrate tests.

Uses testcontainers for real PostgreSQL (no mocks).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_url() -> str:  # type: ignore[return]
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url().replace("psycopg2", "psycopg")


@pytest.fixture
def db_engine(postgres_url: str) -> Engine:  # type: ignore[return]
    engine = create_engine(postgres_url)
    yield engine  # type: ignore[misc]
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO PUBLIC"))
        conn.commit()
    engine.dispose()
