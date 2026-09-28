from dataclasses import replace

import pytest

from hokm.engine.actions import ChooseTrump
from hokm.engine.cards import Suit, parse_cards
from hokm.engine.errors import BadPhase
from hokm.engine.events import TrumpDeclared
from hokm.engine.rules import apply, legal_actions, new_match
from hokm.engine.state import MatchState, Phase, replace_at
from hokm.engine.variants import MatchConfig, Mode, seat_index
from tests.engine.support import advance


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_R6_1_hakem_may_pick_a_suit_they_do_not_hold(mode: Mode) -> None:
    state, _ = new_match(MatchConfig.new(mode, 5, seed=9))
    hakem = state.round.hakem
    # rig an all-spades first five: hearts is not held but still legal
    hands = replace_at(
        state.round.hands, seat_index(state.mode, hakem), parse_cards("AS KS QS JS 10S")
    )
    state = replace(state, round=replace(state.round, hands=hands))
    assert {a.suit for a in legal_actions(state, hakem) if isinstance(a, ChooseTrump)} == set(Suit)
    state, events = apply(state, ChooseTrump(hakem, Suit.HEARTS))
    assert events[0] == TrumpDeclared(hakem, Suit.HEARTS)


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_R6_2_trump_is_announced_and_fixed_for_the_round(mode: Mode) -> None:
    state, _ = new_match(MatchConfig.new(mode, 5, seed=3))
    hakem = state.round.hakem
    state, events = apply(state, ChooseTrump(hakem, Suit.SPADES))
    assert events[0] == TrumpDeclared(hakem, Suit.SPADES)
    assert state.round.trump is Suit.SPADES
    with pytest.raises(BadPhase):
        apply(state, ChooseTrump(hakem, Suit.HEARTS))

    def three_tricks(s: MatchState) -> bool:
        return len(s.round.tricks) == 3

    state, _ = advance(state, three_tricks)
    assert state.phase is Phase.PLAY
    assert state.round.trump is Suit.SPADES
