"""Immutable game state (frozen dataclasses). Per-seat and per-side data are tuples in
play order (`variants.seats`) and side order (`variants.sides`)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from hokm.engine.cards import Card, Suit
from hokm.engine.variants import MatchConfig, Mode, Seat, Side, seat_index, side_index


class Phase(StrEnum):
    """trump → [2p: discard → draw] → play → round_end → match_end"""

    TRUMP = "trump"
    DISCARD = "discard"
    DRAW = "draw"
    PLAY = "play"
    ROUND_END = "round_end"
    MATCH_END = "match_end"


type KotType = Literal["kot", "hakem_koti"]


@dataclass(frozen=True, slots=True)
class Play:
    seat: Seat
    card: Card


@dataclass(frozen=True, slots=True)
class Trick:
    number: int  # 1-based
    leader: Seat
    plays: tuple[Play, ...] = ()
    winner: Seat | None = None  # set once the trick is complete

    @property
    def led_suit(self) -> Suit | None:
        return self.plays[0].card.suit if self.plays else None


@dataclass(frozen=True, slots=True)
class RoundState:
    number: int  # 1-based
    hakem: Seat
    hands: tuple[tuple[Card, ...], ...]  # per seat, sorted by Card.sort_key
    # 2p: the draw stock, top at index 0 (R5.3). 4p: the cards still to deal after trump (R4.4).
    stock: tuple[Card, ...]
    discards: tuple[tuple[Card, ...], ...]  # per seat (2p only; empty in 4p)
    tricks_won: tuple[int, ...]  # per side
    to_act: Seat | None
    trump: Suit | None = None
    draw_turns_done: int = 0  # 2p draw phase, 0..20
    trick: Trick | None = None  # the trick in progress
    tricks: tuple[Trick, ...] = ()  # completed tricks, in order


@dataclass(frozen=True, slots=True)
class RoundResult:
    number: int
    hakem: Seat
    trump: Suit
    tricks_won: tuple[int, ...]  # per side
    winner: Side
    points: int
    kot: KotType | None


@dataclass(frozen=True, slots=True)
class MatchState:
    config: MatchConfig
    phase: Phase
    round: RoundState
    points: tuple[int, ...]  # match points per side
    results: tuple[RoundResult, ...] = ()
    winner: Side | None = None

    @property
    def mode(self) -> Mode:
        return self.config.mode

    def hand(self, seat: Seat) -> tuple[Card, ...]:
        return self.round.hands[seat_index(self.mode, seat)]

    def discards(self, seat: Seat) -> tuple[Card, ...]:
        return self.round.discards[seat_index(self.mode, seat)]

    def tricks_of(self, side: Side) -> int:
        return self.round.tricks_won[side_index(self.mode, side)]

    def points_of(self, side: Side) -> int:
        return self.points[side_index(self.mode, side)]


def replace_at[T](items: tuple[T, ...], index: int, value: T) -> tuple[T, ...]:
    """Copy of `items` with one position replaced."""
    return (*items[:index], value, *items[index + 1 :])


def sorted_cards(cards: tuple[Card, ...]) -> tuple[Card, ...]:
    return tuple(sorted(cards, key=Card.sort_key))
