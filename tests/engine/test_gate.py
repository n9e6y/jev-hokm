"""Phase 1 gate: 10,000 seeded random matches (5,000 per mode) with zero invariant violations.

Every step is probed and fully re-checked, so it takes about 15 minutes; opt-in with
`uv run pytest -m slow tests/engine/test_gate.py`.
"""

import random

import pytest

from hokm.engine.events import RoundEnded
from hokm.engine.rules import apply, new_match
from hokm.engine.state import Phase
from hokm.engine.variants import MATCH_TARGETS, MatchConfig, Mode
from tests.engine.support import (
    assert_accepts_exactly_legal,
    check_invariants,
    next_action,
    random_probe,
)

GAMES_PER_MODE = 5_000


@pytest.mark.slow
@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_gate_ten_thousand_random_matches(mode: Mode) -> None:
    rounds = 0
    for seed in range(GAMES_PER_MODE):
        target = MATCH_TARGETS[seed % len(MATCH_TARGETS)]
        rng = random.Random(f"gate:{mode}:{seed}")
        state, _ = new_match(MatchConfig.new(mode, target, seed))
        check_invariants(state)
        while state.phase is not Phase.MATCH_END:
            # one random probe per step: illegal actions must be rejected, legal ones accepted
            assert_accepts_exactly_legal(state, random_probe(state, rng))
            state, events = apply(state, next_action(state, rng.choice))
            check_invariants(state)
            rounds += sum(isinstance(e, RoundEnded) for e in events)
    assert rounds >= GAMES_PER_MODE
