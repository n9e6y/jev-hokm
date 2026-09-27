"""Cards, suits, ranks and the deck (R1)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum, StrEnum


class Suit(StrEnum):
    """R1.1 the four suits, in canonical order."""

    SPADES = "S"
    HEARTS = "H"
    DIAMONDS = "D"
    CLUBS = "C"


class Rank(IntEnum):
    """R1.2 ranks; a higher value beats a lower one within a suit."""

    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14

    @property
    def symbol(self) -> str:
        return _RANK_SYMBOLS[self]


_RANK_SYMBOLS: dict[Rank, str] = {
    **{r: str(r.value) for r in Rank if r <= Rank.TEN},
    Rank.JACK: "J",
    Rank.QUEEN: "Q",
    Rank.KING: "K",
    Rank.ACE: "A",
}
_SYMBOL_RANKS: dict[str, Rank] = {s: r for r, s in _RANK_SYMBOLS.items()}
_SUIT_LETTERS: frozenset[str] = frozenset(s.value for s in Suit)

# R1.2 high to low: A K Q J 10 ... 2
RANKS_HIGH_TO_LOW: tuple[Rank, ...] = tuple(sorted(Rank, reverse=True))


@dataclass(frozen=True, slots=True)
class Card:
    rank: Rank
    suit: Suit

    @staticmethod
    def parse(text: str) -> Card:
        """R1.3 parse notation such as `AS`, `10H`, `2D`."""
        rank = _SYMBOL_RANKS.get(text[:-1])
        if rank is None or text[-1:] not in _SUIT_LETTERS:
            raise ValueError(f"not a card: {text!r}")
        return Card(rank, Suit(text[-1]))

    def sort_key(self) -> int:
        """Position in the canonical deck (suits S H D C, ranks high to low)."""
        return _CANONICAL_INDEX[self]

    def __str__(self) -> str:
        return f"{self.rank.symbol}{self.suit.value}"

    def __repr__(self) -> str:
        return f"Card({str(self)!r})"


# R1.1 the 52-card French deck in canonical order
CANONICAL_DECK: tuple[Card, ...] = tuple(Card(r, s) for s in Suit for r in RANKS_HIGH_TO_LOW)
_CANONICAL_INDEX: dict[Card, int] = {c: i for i, c in enumerate(CANONICAL_DECK)}


def parse_cards(text: str) -> tuple[Card, ...]:
    """Parse whitespace-separated cards: `"AS 10H 2D"`."""
    return tuple(Card.parse(t) for t in text.split())


def full_deck(removed: Iterable[Card] = ()) -> tuple[Card, ...]:
    """Canonical deck minus `removed` (R1.4 removes two cards in 2-player)."""
    gone = set(removed)
    return tuple(c for c in CANONICAL_DECK if c not in gone)
