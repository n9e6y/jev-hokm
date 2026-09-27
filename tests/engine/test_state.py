import dataclasses

import pytest

from hokm.engine.cards import parse_cards
from hokm.engine.state import MatchState, Phase, RoundState, replace_at, sorted_cards
from hokm.engine.variants import MatchConfig


def _state() -> MatchState:
    round_ = RoundState(
        number=1,
        hakem="A",
        hands=(parse_cards("AS KS"), parse_cards("QH")),
        stock=(),
        discards=((), ()),
        tricks_won=(0, 0),
        to_act="A",
    )
    return MatchState(MatchConfig.new("2p", 5, seed=1), Phase.TRUMP, round_, points=(0, 0))


def test_phases_in_order() -> None:
    assert [p.value for p in Phase] == [
        "trump",
        "discard",
        "draw",
        "play",
        "round_end",
        "match_end",
    ]


def test_state_is_frozen() -> None:
    state = _state()
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.phase = Phase.PLAY  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.round.to_act = "B"  # type: ignore[misc]


def test_state_helpers_index_by_seat_and_side() -> None:
    state = _state()
    assert state.hand("A") == parse_cards("AS KS")
    assert state.hand("B") == parse_cards("QH")
    assert state.tricks_of("B") == 0
    assert state.points_of("A") == 0


def test_replace_at_and_sorted_cards() -> None:
    assert replace_at((1, 2, 3), 1, 9) == (1, 9, 3)
    assert sorted_cards(parse_cards("2C 10H AS KS")) == parse_cards("AS KS 10H 2C")
