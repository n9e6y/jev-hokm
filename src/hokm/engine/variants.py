"""Game modes, seats, sides and match configuration (R1.4, R2, R3.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from hokm.engine.cards import Card, full_deck, parse_cards

type Mode = Literal["2p", "4p"]
type Seat = Literal["S", "E", "N", "W", "A", "B"]
type Side = Literal["NS", "EW", "A", "B"]

# R2.1 counter-clockwise play order; R2.2 two seats alternate
_SEATS: dict[Mode, tuple[Seat, ...]] = {"4p": ("S", "E", "N", "W"), "2p": ("A", "B")}
_SIDE_OF: dict[Seat, Side] = {"S": "NS", "N": "NS", "E": "EW", "W": "EW", "A": "A", "B": "B"}
_SIDES: dict[Mode, tuple[Side, ...]] = {"4p": ("NS", "EW"), "2p": ("A", "B")}

RULES_VERSION = "v1"  # docs/RULES.md "Rules version"; stored with every match
MATCH_TARGETS: tuple[int, ...] = (1, 3, 5, 7)  # R3.1
DEFAULT_REMOVED_CARDS: tuple[Card, ...] = parse_cards("2S 2C")  # R1.4 the black twos


def seats(mode: Mode) -> tuple[Seat, ...]:
    """Seats in play order (R2.1, R2.2)."""
    return _SEATS[mode]


def sides(mode: Mode) -> tuple[Side, ...]:
    return _SIDES[mode]


def seat_index(mode: Mode, seat: Seat) -> int:
    return _SEATS[mode].index(seat)


def next_seat(mode: Mode, seat: Seat) -> Seat:
    """R2.3 next player in play order, wrapping around."""
    order = _SEATS[mode]
    return order[(order.index(seat) + 1) % len(order)]


def side_of(seat: Seat) -> Side:
    """R2.1 partners sit across (NS, EW); R8.3 in 2-player a side is one player."""
    return _SIDE_OF[seat]


def side_index(mode: Mode, side: Side) -> int:
    return _SIDES[mode].index(side)


class ConfigError(ValueError):
    """Invalid match configuration."""


@dataclass(frozen=True, slots=True)
class MatchConfig:
    mode: Mode
    target_points: int
    seed: int
    removed_cards: tuple[Card, ...]

    def __post_init__(self) -> None:
        if self.mode not in _SEATS:
            raise ConfigError(f"unknown mode {self.mode!r}")
        if self.target_points not in MATCH_TARGETS:  # R3.1
            raise ConfigError(f"target_points must be one of {MATCH_TARGETS}")
        if self.mode == "2p":
            # R1.4 exactly two distinct cards
            if len(self.removed_cards) != 2 or len(set(self.removed_cards)) != 2:
                raise ConfigError("2-player removes exactly two distinct cards")
        elif self.removed_cards:
            raise ConfigError("4-player plays the full 52-card deck")

    @staticmethod
    def new(
        mode: Mode,
        target_points: int,
        seed: int,
        removed_cards: tuple[Card, ...] | None = None,
    ) -> MatchConfig:
        """Config with the default removed cards for the mode."""
        if removed_cards is None:
            removed_cards = DEFAULT_REMOVED_CARDS if mode == "2p" else ()
        return MatchConfig(mode, target_points, seed, removed_cards)

    @property
    def deck(self) -> tuple[Card, ...]:
        """The deck used for every deal of this match (R1.4)."""
        return full_deck(self.removed_cards)
