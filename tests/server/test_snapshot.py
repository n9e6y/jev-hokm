import json
import random
import uuid
from dataclasses import replace

import pytest
from pydantic import TypeAdapter, ValidationError

from hokm.engine.state import Phase
from hokm.engine.variants import seats
from hokm.protocol import ObserverSnapshotMsg, PlayerMessage, SnapshotMsg
from hokm.server.snapshot import observer_snapshot, player_snapshot
from hokm.views import build_view, to_json
from tests.engine.support import random_match
from tests.views.support import live_moments
from tests.views.test_leak import permute_hidden

MATCH = uuid.UUID(int=1)
PLAYER = TypeAdapter(PlayerMessage)


def snapshot_json(state, seat, seq):
    return player_snapshot(state, seat, match_id=MATCH, seq=seq, decision_seq=seq).model_dump_json()


def every_moment(match):
    """(state, seq) for every state, live phases and between rounds."""
    return list(enumerate(match.states))


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_wire_view_is_exactly_the_seat_view(mode):
    for state, seq in live_moments(random_match(mode, 3)):
        observer = json.loads(
            observer_snapshot(state, match_id=MATCH, seq=seq, decision_seq=seq).model_dump_json()
        )
        for seat in seats(mode):
            expected = json.loads(to_json(build_view(state, seat, decision_seq=seq)))
            assert json.loads(snapshot_json(state, seat, seq))["view"] == expected
            assert observer["views"][seat] == expected


@pytest.mark.parametrize("mode", ["2p", "4p"])
@pytest.mark.parametrize("seed", range(3))
def test_snapshot_does_not_depend_on_any_hidden_card(mode, seed):
    rng = random.Random(seed)
    for state, seq in live_moments(random_match(mode, seed)):
        for seat in seats(mode):
            expected = snapshot_json(state, seat, seq)
            assert snapshot_json(permute_hidden(state, seat, rng), seat, seq) == expected


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_end_of_round_snapshot_does_not_depend_on_unplayed_cards(mode):
    """R8.1 a round can end with cards still in hand; nobody may learn them."""
    rng = random.Random(9)
    match = random_match(mode, 6)
    ends = [(i, s) for i, s in enumerate(match.states) if s.phase is not Phase.PLAY]
    for seq, state in ends:
        if state.phase not in (Phase.ROUND_END, Phase.MATCH_END):
            continue
        for seat in seats(mode):
            expected = snapshot_json(state, seat, seq)
            assert snapshot_json(permute_hidden(state, seat, rng), seat, seq) == expected


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_snapshot_does_not_depend_on_the_seed(mode):
    for seq, state in every_moment(random_match(mode, 5)):
        reseeded = replace(state, config=replace(state.config, seed=987654321))
        for seat in seats(mode):
            assert snapshot_json(reseeded, seat, seq) == snapshot_json(state, seat, seq)


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_between_rounds_and_after_the_match(mode):
    match = random_match(mode, 4)
    ends = [s for s in match.states if s.phase in (Phase.ROUND_END, Phase.MATCH_END)]
    assert ends[-1].phase is Phase.MATCH_END
    for state in ends:
        snap = player_snapshot(state, seats(mode)[0], match_id=MATCH, seq=1, decision_seq=1)
        assert snap.view is None and snap.whose_turn is None
        assert snap.last_round is not None and snap.last_round.points == state.results[-1].points
        assert snap.match_points == list(state.points)
        observer = observer_snapshot(state, match_id=MATCH, seq=1, decision_seq=1)
        assert observer.views == {}
        assert ObserverSnapshotMsg.model_validate_json(observer.model_dump_json()) == observer
    last = player_snapshot(ends[-1], seats(mode)[0], match_id=MATCH, seq=1, decision_seq=1)
    assert last.winner == ends[-1].winner


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_player_snapshots_round_trip_through_the_player_union(mode):
    for seq, state in every_moment(random_match(mode, 1)):
        for seat in seats(mode):
            text = snapshot_json(state, seat, seq)
            assert PLAYER.validate_json(text).model_dump_json() == text


def test_observer_snapshot_is_not_a_player_message():
    state = random_match("4p", 1).states[3]
    text = observer_snapshot(state, match_id=MATCH, seq=3, decision_seq=3).model_dump_json()
    with pytest.raises(ValidationError):
        PLAYER.validate_json(text)


def test_snapshot_refuses_another_seats_view():
    state = random_match("2p", 1).states[3]
    good = player_snapshot(state, "A", match_id=MATCH, seq=3, decision_seq=3)
    with pytest.raises(ValidationError):
        SnapshotMsg(**{**good.model_dump(), "seat": "B"})
    with pytest.raises(ValidationError):
        SnapshotMsg(**{**good.model_dump(), "view": None})  # live phase needs a view


def test_observer_views_sit_under_their_own_seat():
    state = random_match("2p", 1).states[3]
    snap = observer_snapshot(state, match_id=MATCH, seq=3, decision_seq=3)
    swapped = {"A": snap.views["B"], "B": snap.views["A"]}
    with pytest.raises(ValidationError):
        ObserverSnapshotMsg(**{**snap.model_dump(), "views": swapped})
