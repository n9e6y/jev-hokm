"""Fixtures for tests against a real Postgres (`docker compose up -d db`).

Each test database is created fresh next to the dev database named in DATABASE_URL (or the
docker-compose default). When Postgres is not reachable, every test here is skipped.
"""

import os
from collections.abc import Callable, Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import URL, make_url

COMPOSE_URL = "postgresql+psycopg://hokm:hokm@localhost:5432/hokm"


def server_url() -> URL:
    return make_url(os.environ.get("DATABASE_URL") or COMPOSE_URL)


@pytest.fixture(scope="session")
def admin_engine() -> Iterator[Engine]:
    engine = create_engine(server_url().set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect():
            pass
    except Exception as exc:  # noqa: BLE001 any connection failure means "no database here"
        pytest.skip(f"Postgres not reachable ({type(exc).__name__}); run docker compose up -d db")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def fresh_database(admin_engine: Engine) -> Callable[[str], str]:
    """Create an empty database and return its URL."""

    def create(name: str) -> str:
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        return server_url().set(database=name).render_as_string(hide_password=False)

    return create


def alembic_config(url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture(scope="session")
def migrated_engine(fresh_database: Callable[[str], str]) -> Iterator[Engine]:
    url = fresh_database("hokm_test")
    command.upgrade(alembic_config(url), "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def conn(migrated_engine: Engine) -> Iterator[Connection]:
    """A connection whose work is rolled back after the test."""
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()
