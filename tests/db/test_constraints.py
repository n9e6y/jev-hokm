import uuid

import pytest
from sqlalchemy import Connection, insert, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from hokm.db.models import BotProfile, Decision, Event, JevCall, Match, Round


def add_match(conn: Connection, **overrides) -> uuid.UUID:
    values = {
        "id": uuid.uuid4(),
        "mode": "2p",
        "target_points": 7,
        "seed": 1,
        "removed_cards": ["2S", "2C"],
        "rules_version": "1",
        "app_version": "0.1.0",
        "status": "running",
    }
    values.update(overrides)
    conn.execute(insert(Match).values(**values))
    return values["id"]


def add_event(conn: Connection, match_id: uuid.UUID, seq: int, **overrides) -> None:
    values = {"match_id": match_id, "seq": seq, "name": "CardPlayed", "visibility": "all"}
    values |= {"payload": {"seat": "A", "card": "AS"}} | overrides
    conn.execute(insert(Event).values(**values))


def rejected(conn: Connection, statement, error: type[DBAPIError] = IntegrityError) -> bool:
    """Run `statement` in a savepoint; True when the database refused it."""
    savepoint = conn.begin_nested()
    try:
        conn.execute(statement)
    except error:
        savepoint.rollback()
        return True
    savepoint.rollback()
    return False


def test_match_checks(conn):
    add_match(conn)
    add_match(conn, mode="4p", target_points=1, forget_seed=99)
    assert rejected(
        conn,
        insert(Match).values(
            mode="3p",
            target_points=7,
            seed=1,
            removed_cards=[],
            rules_version="1",
            app_version="0",
            status="x",
        ),
    )
    assert rejected(
        conn,
        insert(Match).values(
            mode="2p",
            target_points=2,
            seed=1,
            removed_cards=[],
            rules_version="1",
            app_version="0",
            status="x",
        ),
    )


def test_event_seq_is_unique_per_match_and_visibility_is_checked(conn):
    match_id = add_match(conn)
    add_event(conn, match_id, 1)
    add_event(conn, add_match(conn), 1)  # same seq, other match: fine
    assert rejected(
        conn, insert(Event).values(match_id=match_id, seq=1, name="x", visibility="all", payload={})
    )
    assert rejected(
        conn,
        insert(Event).values(match_id=match_id, seq=2, name="x", visibility="everyone", payload={}),
    )


def decision_chain(conn: Connection) -> tuple[uuid.UUID, uuid.UUID]:
    """A match, round, bot profile, decision and Jev call; returns (match_id, decision_id)."""
    match_id = add_match(conn)
    round_id, profile_id, decision_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    conn.execute(insert(Round).values(id=round_id, match_id=match_id, number=1, hakem_seat="A"))
    conn.execute(insert(BotProfile).values(id=profile_id, name="jev-raw", bot_type="jev"))
    conn.execute(
        insert(Decision).values(
            id=decision_id,
            match_id=match_id,
            round_id=round_id,
            event_seq=4,
            seat="A",
            role="bot",
            bot_profile_id=profile_id,
            decision_type="play",
            view={},
            question_id="q.play.v1",
            question_text="?",
            options=["AS"],
            forced=False,
            final_choice="AS",
            attempts=1,
            status="ok",
        )
    )
    conn.execute(
        insert(JevCall).values(
            decision_id=decision_id, attempt=1, model_id="jev-x", request={}, response={}
        )
    )
    add_event(conn, match_id, 1)
    return match_id, decision_id


@pytest.mark.parametrize("table", ["events", "decisions", "jev_calls"])
def test_append_only_tables_refuse_update_and_delete(conn, table):
    decision_chain(conn)
    for sql in (f"UPDATE {table} SET created_at = now()", f"DELETE FROM {table}"):
        savepoint = conn.begin_nested()
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text(sql))
        savepoint.rollback()


def test_other_tables_can_still_be_updated(conn):
    match_id = add_match(conn)
    assert not rejected(
        conn, update(Match).where(Match.id == match_id).values(status="ended"), error=DBAPIError
    )
