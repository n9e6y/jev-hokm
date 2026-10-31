import json
import uuid

import pytest
from sqlalchemy import Connection, insert, select

from hokm.db.models import Event, Match, Round
from hokm.db.store import (
    CorruptLog,
    SeatAssignment,
    add_bot_profile,
    add_player,
    append_events,
    create_match,
    last_seq,
    rebuild,
)
from hokm.engine.rules import apply, new_match
from hokm.engine.variants import MatchConfig, Seat, seats
from tests.engine.support import RecordedMatch, random_match


def new_stored_match(conn: Connection, config: MatchConfig, forget_seed=None) -> uuid.UUID:
    profile = add_bot_profile(conn, "random", "random")
    assignments: dict[Seat, SeatAssignment] = {
        seat: SeatAssignment(add_player(conn, "bot", f"bot-{seat}"), profile)
        for seat in seats(config.mode)
    }
    return create_match(conn, config, assignments, forget_seed=forget_seed)


def store(conn: Connection, match: RecordedMatch) -> uuid.UUID:
    match_id = new_stored_match(conn, match.config)
    append_events(conn, match_id, match.events)
    return match_id


@pytest.mark.parametrize("mode", ["2p", "4p"])
@pytest.mark.parametrize("seed", range(4))
def test_full_match_rebuilds_to_the_same_states_and_events(conn, mode, seed):
    match = random_match(mode, seed)
    match_id = store(conn, match)
    rebuilt = rebuild(conn, match_id)
    assert rebuilt.config == match.config
    assert rebuilt.replay.events == match.events
    assert rebuilt.replay.states == match.states


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_match_saved_one_action_at_a_time_rebuilds_at_every_point(conn, mode):
    """The server-restart case: after every action the stored log rebuilds the live state."""
    match = random_match(mode, seed=7, target=1)
    match_id = new_stored_match(conn, match.config)
    state, events = new_match(match.config)
    append_events(conn, match_id, events)
    for action in match.actions:
        state, events = apply(state, action)
        append_events(conn, match_id, events)
        assert rebuild(conn, match_id).replay.final == state


def test_seqs_run_from_one_without_gaps(conn):
    match = random_match("2p", 3)
    match_id = store(conn, match)
    seqs = conn.scalars(select(Event.seq).where(Event.match_id == match_id).order_by(Event.seq))
    assert list(seqs) == list(range(1, len(match.events) + 1))
    assert last_seq(conn, match_id) == len(match.events)
    assert last_seq(conn, uuid.uuid4()) == 0


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_visibility_follows_protocol_md(conn, mode):
    match_id = store(conn, random_match(mode, 5))
    rows = conn.execute(
        select(Event.name, Event.visibility, Event.seat, Event.payload).where(
            Event.match_id == match_id
        )
    ).all()
    seat_only = {"CardsDealt", "CardShown", "CardDiscarded", "DrawResolved"}
    for name, visibility, seat, payload in rows:
        if name in seat_only:
            assert (visibility, seat) == ("seat", payload["seat"]), name
        else:
            assert (visibility, seat) == ("all", None), name


def test_rounds_and_match_rows_follow_the_results(conn):
    match = random_match("4p", 2)
    match_id = store(conn, match)
    final = match.states[-1]
    summary = conn.execute(
        select(
            Round.number, Round.hakem_seat, Round.trump, Round.tricks, Round.points, Round.kot_type
        )
        .where(Round.match_id == match_id)
        .order_by(Round.number)
    ).all()
    assert [tuple(r) for r in summary] == [
        (res.number, res.hakem, res.trump.value, list(res.tricks_won), res.points, res.kot)
        for res in final.results
    ]
    row = conn.execute(select(Match).where(Match.id == match_id)).one()
    assert (row.status, row.winner_side, row.rules_version) == ("ended", final.winner, "v1")
    assert row.ended_at is not None


def test_forget_seed_is_kept_with_the_match(conn):
    config = MatchConfig.new("2p", 1, seed=11)
    match_id = new_stored_match(conn, config, forget_seed=123456789)
    append_events(conn, match_id, new_match(config)[1])
    assert rebuild(conn, match_id).forget_seed == 123456789


def test_no_stored_event_carries_the_seed(conn):
    match = random_match("2p", 424242)
    match_id = store(conn, match)
    payloads = conn.scalars(select(Event.payload).where(Event.match_id == match_id))
    for payload in payloads:
        assert "seed" not in json.dumps(payload)
        assert "424242" not in json.dumps(payload)


def test_changed_move_is_reported_as_corrupt(conn):
    """Rows cannot be updated (append-only trigger), so build the bad log by inserting one."""
    match = random_match("2p", 1)
    match_id = new_stored_match(conn, match.config)
    events = list(match.events)
    i = next(i for i, e in enumerate(events) if type(e).__name__ == "TrickWon")
    append_events(conn, match_id, events[:i])
    conn.execute(
        insert(Event).values(
            match_id=match_id,
            seq=i + 1,
            name="TrickWon",
            visibility="all",
            payload={"number": 1, "winner": "A", "tricks_won": [7, 0]},  # never happened
        )
    )
    with pytest.raises(CorruptLog):
        rebuild(conn, match_id)


def test_truncated_log_is_reported_as_corrupt(conn):
    match = random_match("2p", 1)
    match_id = new_stored_match(conn, match.config)
    events = list(match.events)
    i = next(i for i, e in enumerate(events) if type(e).__name__ == "CardDiscarded")
    append_events(conn, match_id, events[: i + 1])  # one card of a two-card discard
    with pytest.raises(CorruptLog):
        rebuild(conn, match_id)


def test_match_needs_every_seat(conn):
    player = add_player(conn, "human", "nima")
    with pytest.raises(ValueError, match="seats"):
        create_match(conn, MatchConfig.new("4p", 1, 1), {"S": SeatAssignment(player)})
