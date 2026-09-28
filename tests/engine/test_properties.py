"""Property tests over seeded random matches (1.14). Hypothesis picks mode, seed and target;
the playout itself is driven by a seeded random.Random so every failure replays exactly."""

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from hokm.engine.events import CardPlayed, RoundEnded, RoundStarted, TrickWon
from hokm.engine.rules import apply, legal_actions, new_match
from hokm.engine.state import MatchState, Phase
from hokm.engine.variants import MATCH_TARGETS, MatchConfig, Mode, seats
from tests.engine.support import (
    assert_accepts_exactly_legal,
    check_invariants,
    next_action,
    random_match,
    random_probe,
)

modes = st.sampled_from(["2p", "4p"])
seeds = st.integers(min_value=0, max_value=2**63)
targets = st.sampled_from(MATCH_TARGETS)


def _playout(mode: Mode, seed: int, target: int, probes: int = 0) -> MatchState:
    rng = random.Random(f"prop:{seed}")
    state, _ = new_match(MatchConfig.new(mode, target, seed))
    check_invariants(state)
    while state.phase is not Phase.MATCH_END:
        for _ in range(probes):
            assert_accepts_exactly_legal(state, random_probe(state, rng))
        state, _ = apply(state, next_action(state, rng.choice))
        check_invariants(state)
    return state


@settings(max_examples=150, deadline=None)
@given(mode=modes, seed=seeds, target=targets)
def test_card_conservation_and_invariants_hold_after_every_action(
    mode: Mode, seed: int, target: int
) -> None:
    _playout(mode, seed, target)


@settings(max_examples=60, deadline=None)
@given(mode=modes, seed=seeds, target=st.sampled_from((1, 3)))
def test_no_illegal_action_is_ever_accepted(mode: Mode, seed: int, target: int) -> None:
    _playout(mode, seed, target, probes=6)


@settings(max_examples=60, deadline=None)
@given(mode=modes, seed=seeds)
def test_every_listed_legal_action_is_accepted(mode: Mode, seed: int) -> None:
    rng = random.Random(f"listed:{seed}")
    state, _ = new_match(MatchConfig.new(mode, 1, seed))
    while state.phase is not Phase.MATCH_END:
        seat = state.round.to_act
        assert seat is not None
        for action in legal_actions(state, seat):
            assert_accepts_exactly_legal(state, action)
        state, _ = apply(state, next_action(state, rng.choice))


@settings(max_examples=100, deadline=None)
@given(mode=modes, seed=seeds, target=targets)
def test_every_round_ends_exactly_when_a_side_reaches_seven(
    mode: Mode, seed: int, target: int
) -> None:
    match = random_match(mode, seed, target)
    n_seats = len(seats(mode))
    in_round = False
    tricks = plays = 0
    last: tuple[int, ...] = ()
    for e in match.events:
        match e:
            case RoundStarted():
                assert not in_round
                in_round, tricks, plays = True, 0, 0
            case CardPlayed():
                assert in_round, "a card was played outside a round"
                plays += 1
            case TrickWon(tricks_won=tw):
                tricks += 1
                assert max(tw) <= 7
                last = tw
            case RoundEnded(tricks_won=tw):
                # R8.1 the round ended on the trick that gave a side its 7th
                assert tw == last and max(tw) == 7 and min(tw) < 7
                assert sum(tw) == tricks and plays == tricks * n_seats
                in_round = False
            case _:
                pass
    assert not in_round
