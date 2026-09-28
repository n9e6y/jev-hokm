"""Shared engine test helpers.

States are only ever produced by the real engine; `play_state` then rigs hands with
`dataclasses.replace` to set up a specific trick. The engine itself is never mocked.
"""

from collections.abc import Callable
from dataclasses import replace

from hokm.engine.actions import Action
from hokm.engine.cards import Suit, parse_cards
from hokm.engine.events import Event
from hokm.engine.rules import apply, legal_actions, new_match
from hokm.engine.state import MatchState, Phase, Trick, sorted_cards
from hokm.engine.variants import MatchConfig, Mode, Seat, seats

type Chooser = Callable[[tuple[Action, ...]], Action]


def first(options: tuple[Action, ...]) -> Action:
    return options[0]


def start(mode: Mode, seed: int = 1, target: int = 7) -> MatchState:
    state, _ = new_match(MatchConfig.new(mode, target, seed))
    return state


def advance(
    state: MatchState,
    until: Callable[[MatchState], bool],
    choose: Chooser = first,
) -> tuple[MatchState, list[Event]]:
    """Apply legal actions for whoever is to act until `until(state)` holds."""
    events: list[Event] = []
    while not until(state):
        seat = state.round.to_act
        assert seat is not None
        state, new = apply(state, choose(legal_actions(state, seat)))
        events.extend(new)
    return state, events


def in_phase(phase: Phase) -> Callable[[MatchState], bool]:
    return lambda s: s.phase is phase


def play_state(
    mode: Mode,
    hands: dict[Seat, str],
    *,
    trump: Suit = Suit.HEARTS,
    leader: Seat | None = None,
) -> MatchState:
    """A play-phase state with rigged hands (card conservation is not kept)."""
    state = start(mode)
    lead = leader or state.round.hakem
    round_ = replace(
        state.round,
        hands=tuple(sorted_cards(parse_cards(hands[s])) for s in seats(mode)),
        stock=(),
        trump=trump,
        to_act=lead,
        trick=Trick(1, lead),
    )
    return replace(state, phase=Phase.PLAY, round=round_)
