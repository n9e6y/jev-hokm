"""Replay: a match config (with its seed) plus the action list reproduces every state and event."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from hokm.engine.actions import Action
from hokm.engine.events import Event
from hokm.engine.rules import apply, new_match
from hokm.engine.state import MatchState
from hokm.engine.variants import MatchConfig


@dataclass(frozen=True, slots=True)
class Replay:
    states: tuple[MatchState, ...]  # states[0] is the new match; states[i + 1] follows actions[i]
    events: tuple[Event, ...]  # every event in order, starting with new_match's

    @property
    def final(self) -> MatchState:
        return self.states[-1]


def replay(config: MatchConfig, actions: Iterable[Action]) -> Replay:
    """Rebuild a match. Raises the engine's error if any action is not legal at its point."""
    state, events = new_match(config)
    states = [state]
    all_events = list(events)
    for action in actions:
        state, events = apply(state, action)
        states.append(state)
        all_events.extend(events)
    return Replay(tuple(states), tuple(all_events))
