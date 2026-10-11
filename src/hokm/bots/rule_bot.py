"""Rule-based bot (2.5): simple, deterministic card-table heuristics, from the view only.

Heuristics:
- Trump: the longest suit among the 5 cards; ties go to the higher total rank, then to
  suit order S H D C.
- Discard (2p): the 2 least useful cards: non-trump before trump, then lowest rank, then the
  shorter suit (to make a void).
- Draw (2p): keep the shown card if it is trump or rank J or higher; otherwise discard it and
  take the unseen next card.
- Lead: a non-trump ace if held; else the lowest card of the longest non-trump suit; with only
  trumps left, the lowest trump.
- Follow suit: if the partner is winning the trick (4p), play the lowest card; otherwise the
  lowest card that beats the current winner, or the lowest card if none can.
- Void in the led suit: if the partner is winning, throw the lowest non-trump; otherwise trump
  with the lowest trump that wins, or throw the lowest non-trump (lowest card if only trumps).

"Current winner" is the bot's own reading of the visible trick (highest trump, else highest of
the led suit). "Lowest" means lowest rank, ties broken by suit order S H D C.
"""

from __future__ import annotations

from collections import Counter

from hokm.engine.cards import Card, Rank, Suit
from hokm.views import Choice, SeatView
from hokm.views.schema import DiscardView, DrawView, PlayView, TrumpView

_SUIT_BY_NAME: dict[str, Suit] = {
    "spades": Suit.SPADES,
    "hearts": Suit.HEARTS,
    "diamonds": Suit.DIAMONDS,
    "clubs": Suit.CLUBS,
}
_NAME_BY_SUIT: dict[Suit, str] = {s: n for n, s in _SUIT_BY_NAME.items()}
_SUIT_ORDER: dict[Suit, int] = {s: i for i, s in enumerate(Suit)}


def _parse(cards: list[str]) -> list[Card]:
    return [Card.parse(c) for c in cards]


def _lowest(cards: list[Card]) -> Card:
    return min(cards, key=lambda c: (c.rank, _SUIT_ORDER[c.suit]))


def _trump(view: SeatView) -> Suit | None:
    name = view["trump_suit"]
    return _SUIT_BY_NAME[name] if name is not None else None


def beats(card: Card, best: Card, trump: Suit | None) -> bool:
    """Would `card` beat the current winning card `best`? (best is trump or of the led suit)"""
    if card.suit == trump:
        return best.suit != trump or card.rank > best.rank
    return card.suit == best.suit and card.rank > best.rank


class RuleBot:
    kind = "rule"

    def decide(self, view: SeatView) -> Choice:
        if not view["options"]:
            raise ValueError("no decision to make: the view has no options")
        match view["phase"]:
            case "trump":
                return self._trump(view)
            case "discard":
                return self._discard(view)
            case "draw":
                return self._draw(view)
            case "play":
                return self._play(view)

    def _trump(self, view: TrumpView) -> Choice:
        hand = _parse(view["hand"])
        counts = Counter(c.suit for c in hand)
        strength = Counter[Suit]()
        for c in hand:
            strength[c.suit] += c.rank
        best = max(Suit, key=lambda s: (counts[s], strength[s], -_SUIT_ORDER[s]))
        return _NAME_BY_SUIT[best]

    def _discard(self, view: DiscardView) -> Choice:
        trump = _trump(view)
        hand = _parse(view["options"])
        length = Counter(c.suit for c in hand)
        ranked = sorted(
            hand, key=lambda c: (c.suit == trump, c.rank, length[c.suit], _SUIT_ORDER[c.suit])
        )
        return [str(c) for c in ranked[: view["discard_count"]]]

    def _draw(self, view: DrawView) -> Choice:
        shown = view["card_shown"]
        assert shown is not None  # the seat on turn is always shown the top card
        card = Card.parse(shown)
        keep = card.suit == _trump(view) or card.rank >= Rank.JACK
        return "keep" if keep else "discard"

    def _play(self, view: PlayView) -> Choice:
        trump = _trump(view)
        options = _parse(view["options"])
        played = [(p["seat"], Card.parse(p["card"])) for p in view["trick"]["cards"]]
        if not played:
            return str(self._lead(options, trump))

        led = played[0][1].suit
        winner_seat, best = played[0]
        for seat, card in played[1:]:
            if beats(card, best, trump):
                winner_seat, best = seat, card
        partner_winning = view.get("partner") == winner_seat
        winners = [c for c in options if beats(c, best, trump)]
        non_trump = [c for c in options if c.suit != trump] or options

        if any(c.suit == led for c in options):  # following suit (options are all of led suit)
            if partner_winning or not winners:
                return str(_lowest(options))
            return str(_lowest(winners))
        # void in the led suit
        if partner_winning or not winners:
            return str(_lowest(non_trump))
        return str(_lowest(winners))

    def _lead(self, options: list[Card], trump: Suit | None) -> Card:
        side_suits = [c for c in options if c.suit != trump]
        aces = [c for c in side_suits if c.rank == Rank.ACE]
        if aces:
            return aces[0]
        if not side_suits:
            return _lowest(options)
        length = Counter(c.suit for c in side_suits)
        longest = max(length.values())
        suit = min((s for s in length if length[s] == longest), key=lambda s: _SUIT_ORDER[s])
        return _lowest([c for c in side_suits if c.suit == suit])
