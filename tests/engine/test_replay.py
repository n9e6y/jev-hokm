import pytest

from hokm.engine.actions import PlayCard
from hokm.engine.errors import EngineError
from hokm.engine.replay import replay
from hokm.engine.state import Phase
from hokm.engine.variants import MatchConfig, Mode
from tests.engine.support import random_match


@pytest.mark.parametrize("mode", ["2p", "4p"])
@pytest.mark.parametrize("seed", range(5))
def test_replay_reproduces_identical_states_and_events(mode: Mode, seed: int) -> None:
    match = random_match(mode, seed)
    result = replay(match.config, match.actions)
    assert result.states == match.states
    assert result.events == match.events
    assert result.final.phase is Phase.MATCH_END


def test_same_seed_and_actions_are_deterministic_across_runs() -> None:
    match = random_match("4p", 11)
    assert replay(match.config, match.actions) == replay(match.config, match.actions)


def test_a_different_seed_does_not_accept_the_same_actions() -> None:
    match = random_match("4p", 11)
    other = MatchConfig.new("4p", match.config.target_points, seed=12)
    with pytest.raises(EngineError):
        replay(other, match.actions)


def test_replay_rejects_a_tampered_action() -> None:
    match = random_match("2p", 3)
    i = next(i for i, a in enumerate(match.actions) if isinstance(a, PlayCard))
    played = match.actions[i]
    assert isinstance(played, PlayCard)
    # play a card the seat does not hold at that point
    stranger = next(c for c in match.config.deck if c not in match.states[i].hand(played.seat))
    tampered = (*match.actions[:i], PlayCard(played.seat, stranger), *match.actions[i + 1 :])
    with pytest.raises(EngineError):
        replay(match.config, tampered)
