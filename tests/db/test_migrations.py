from alembic import command
from sqlalchemy import create_engine, inspect

from tests.db.conftest import alembic_config

# docs/DATABASE.md, table by table (plus ADR-014 `forget_seed`)
EXPECTED: dict[str, set[str]] = {
    "players": {"id", "kind", "name", "created_at"},
    "bot_profiles": {
        "id",
        "name",
        "bot_type",
        "view_profile",
        "profile_version",
        "forgetfulness",
        "question_set",
        "model_id",
        "config",
        "created_at",
    },
    "matches": {
        "id",
        "mode",
        "target_points",
        "seed",
        "forget_seed",
        "removed_cards",
        "rules_version",
        "app_version",
        "status",
        "winner_side",
        "started_at",
        "ended_at",
    },
    "match_seats": {"match_id", "seat", "player_id", "bot_profile_id", "side"},
    "rounds": {
        "id",
        "match_id",
        "number",
        "hakem_seat",
        "trump",
        "tricks",
        "points",
        "kot_type",
        "winner_side",
    },
    "events": {
        "id",
        "match_id",
        "round_id",
        "seq",
        "name",
        "visibility",
        "seat",
        "payload",
        "created_at",
    },
    "decisions": {
        "id",
        "match_id",
        "round_id",
        "event_seq",
        "seat",
        "role",
        "bot_profile_id",
        "decision_type",
        "view",
        "question_id",
        "question_text",
        "options",
        "forced",
        "final_choice",
        "attempts",
        "status",
        "created_at",
    },
    "truth_snapshots": {"decision_id", "all_hands", "stock", "all_discards"},
    "jev_calls": {
        "id",
        "decision_id",
        "attempt",
        "model_id",
        "request",
        "response",
        "probabilities",
        "latency_ms",
        "http_status",
        "error",
        "cost_usd",
        "created_at",
    },
    "experiments": {"id", "name", "hypothesis", "arms", "seed_set", "created_at"},
    "experiment_matches": {"experiment_id", "match_id", "arm"},
}


def test_every_table_and_column_in_database_md(migrated_engine):
    inspector = inspect(migrated_engine)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    assert tables == set(EXPECTED)
    for table, columns in EXPECTED.items():
        assert {c["name"] for c in inspector.get_columns(table)} == columns, table


def test_models_and_migration_agree(migrated_engine):
    command.check(alembic_config(migrated_engine.url.render_as_string(hide_password=False)))


def test_upgrade_downgrade_upgrade(fresh_database):
    url = fresh_database("hokm_test_migrations")
    config = alembic_config(url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    engine = create_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
        command.upgrade(config, "head")
        assert set(EXPECTED) <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
