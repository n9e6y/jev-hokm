"""Helpers for view tests: walk every live moment of a recorded random match."""

from collections.abc import Iterator

from hokm.engine.state import MatchState, Phase
from tests.engine.support import RecordedMatch

LIVE = (Phase.TRUMP, Phase.DISCARD, Phase.DRAW, Phase.PLAY)


def live_moments(match: RecordedMatch) -> Iterator[tuple[MatchState, int]]:
    """(state, decision_seq) for every state with a view; decision_seq = actions applied so far."""
    for i, state in enumerate(match.states):
        if state.phase in LIVE:
            yield state, i
