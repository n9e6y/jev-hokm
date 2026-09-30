"""The one gate from a bot's answer to an engine action.

A choice must come from the view's `options` (discard: exactly `discard_count` distinct options).
Anything else raises `InvalidChoice`; the caller decides what that means (the simulator treats it
as a bot bug; the Jev bot re-asks, docs/JEV.md).
"""

from __future__ import annotations

from hokm.engine.actions import Action, ChooseTrump, Discard, DrawDecision, PlayCard
from hokm.engine.cards import Card, Suit
from hokm.views.schema import SeatView

type Choice = str | list[str]

_SUITS_BY_NAME: dict[str, Suit] = {
    "spades": Suit.SPADES,
    "hearts": Suit.HEARTS,
    "diamonds": Suit.DIAMONDS,
    "clubs": Suit.CLUBS,
}


class InvalidChoice(ValueError):
    """The choice is not one of the view's options."""


def to_action(view: SeatView, choice: Choice) -> Action:
    seat, options = view["seat"], view["options"]
    if not options:
        raise InvalidChoice(f"{seat} has no decision to make")
    if view["phase"] == "discard":
        if not isinstance(choice, list):
            raise InvalidChoice("a discard is a list of cards")
        picked = [c for c in choice if c in options]
        count = view["discard_count"]
        if len(choice) != count or len(set(picked)) != count:
            raise InvalidChoice(f"discard exactly {count} distinct cards from {options}")
        return Discard(seat, tuple(Card.parse(c) for c in choice))
    if not isinstance(choice, str) or choice not in options:
        raise InvalidChoice(f"{choice!r} is not one of {options}")
    match view["phase"]:
        case "trump":
            return ChooseTrump(seat, _SUITS_BY_NAME[choice])
        case "draw":
            return DrawDecision(seat, keep=choice == "keep")
        case "play":
            return PlayCard(seat, Card.parse(choice))
