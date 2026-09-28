"""Events emitted by `rules.apply`. Class names are the event names in docs/PROTOCOL.md.

Events carry full information plus the owning seat; per-seat redaction happens in the server.
"""

from __future__ import annotations

from dataclasses import dataclass

from hokm.engine.cards import Card, Suit
from hokm.engine.variants import Mode, Seat


@dataclass(frozen=True, slots=True)
class MatchStarted:
    mode: Mode
    target_points: int
    seats: tuple[Seat, ...]  # the seed stays server-side


@dataclass(frozen=True, slots=True)
class RoundStarted:
    number: int
    hakem: Seat


@dataclass(frozen=True, slots=True)
class CardsDealt:
    """Cards that just became visible to `seat` (ADR-012)."""

    seat: Seat
    cards: tuple[Card, ...]


@dataclass(frozen=True, slots=True)
class TrumpDeclared:
    hakem: Seat
    suit: Suit


@dataclass(frozen=True, slots=True)
class CardDiscarded:
    """2p opening discard, one event per card; the card is known only to `seat` (R5.3)."""

    seat: Seat
    card: Card


@dataclass(frozen=True, slots=True)
class CardShown:
    """2p draw: top stock card shown to `seat` only (R5.4)."""

    seat: Seat
    card: Card


@dataclass(frozen=True, slots=True)
class DrawResolved:
    """2p draw: `kept` went to the hand, `dropped` to the seat's discards (R5.4)."""

    seat: Seat
    kept: Card
    dropped: Card


@dataclass(frozen=True, slots=True)
class CardPlayed:
    seat: Seat
    card: Card


@dataclass(frozen=True, slots=True)
class TrickWon:
    number: int
    winner: Seat
    tricks_won: tuple[int, ...]  # per side, after this trick


type Event = (
    MatchStarted
    | RoundStarted
    | CardsDealt
    | TrumpDeclared
    | CardDiscarded
    | CardShown
    | DrawResolved
    | CardPlayed
    | TrickWon
)
