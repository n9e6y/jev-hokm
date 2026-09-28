from typing import get_args

import pytest

from hokm.engine import events as engine_events
from hokm.engine.events import Event
from hokm.engine.variants import Mode
from tests.engine.support import random_match

# Event names from the table in docs/PROTOCOL.md. Kept here because docs/ is local-only
# (ADR-011); update both together. BotDecision and BotPaused are server events, not engine.
PROTOCOL_EVENT_NAMES = {
    "MatchStarted",
    "RoundStarted",
    "CardsDealt",
    "TrumpDeclared",
    "CardDiscarded",
    "CardShown",
    "DrawResolved",
    "CardPlayed",
    "TrickWon",
    "RoundEnded",
    "MatchEnded",
    "BotDecision",
    "BotPaused",
}
SERVER_ONLY = {"BotDecision", "BotPaused"}


def test_every_engine_event_class_uses_a_protocol_name() -> None:
    names = {cls.__name__ for cls in get_args(Event.__value__)}
    assert names == PROTOCOL_EVENT_NAMES - SERVER_ONLY
    # nothing in events.py outside the union
    defined = {
        name
        for name, obj in vars(engine_events).items()
        if isinstance(obj, type) and obj.__module__ == engine_events.__name__
    }
    assert defined == names


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_apply_emits_every_event_type_of_the_mode(mode: Mode) -> None:
    seen = {type(e).__name__ for seed in range(3) for e in random_match(mode, seed).events}
    two_player_only = {"CardDiscarded", "CardShown", "DrawResolved"}
    expected = PROTOCOL_EVENT_NAMES - SERVER_ONLY
    assert seen == (expected if mode == "2p" else expected - two_player_only)
