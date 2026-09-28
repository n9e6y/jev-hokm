import random

import pytest

from hokm.engine.rules import apply, legal_actions
from hokm.engine.state import MatchState, Phase
from hokm.engine.variants import Mode, seats
from tests.engine.support import start


def _seven_tricks(state: MatchState) -> bool:
    return max(state.round.tricks_won) == 7


@pytest.mark.parametrize("mode", ["2p", "4p"])
@pytest.mark.parametrize("seed", range(10))
def test_every_legal_action_is_accepted_and_only_the_seat_to_act_has_any(
    mode: Mode, seed: int
) -> None:
    rng = random.Random(seed)
    state = start(mode, seed)
    phases_seen: set[Phase] = set()
    while not _seven_tricks(state):
        phases_seen.add(state.phase)
        to_act = state.round.to_act
        for seat in seats(mode):
            if seat != to_act:
                assert legal_actions(state, seat) == ()
        assert to_act is not None
        options = legal_actions(state, to_act)
        assert options
        for action in options:
            apply(state, action)  # must not raise
        state, _ = apply(state, rng.choice(options))
    expected = {Phase.TRUMP, Phase.PLAY} | ({Phase.DISCARD, Phase.DRAW} if mode == "2p" else set())
    assert phases_seen == expected
