"""Actions accepted by `rules.apply`. Seat actions mirror the intents in docs/PROTOCOL.md."""

from __future__ import annotations

from dataclasses import dataclass

from hokm.engine.cards import Card, Suit
from hokm.engine.variants import Seat


@dataclass(frozen=True, slots=True)
class ChooseTrump:
    seat: Seat
    suit: Suit


@dataclass(frozen=True, slots=True)
class Discard:
    """2p opening discard of exactly two cards (R5.3)."""

    seat: Seat
    cards: tuple[Card, ...]


@dataclass(frozen=True, slots=True)
class DrawDecision:
    """2p draw turn (R5.4): keep the shown card, or discard it and keep the next one."""

    seat: Seat
    keep: bool


@dataclass(frozen=True, slots=True)
class PlayCard:
    seat: Seat
    card: Card


@dataclass(frozen=True, slots=True)
class NextRound:
    """System action: leave the round_end phase and deal the next round."""


type SeatAction = ChooseTrump | Discard | DrawDecision | PlayCard
type Action = SeatAction | NextRound
