"""Build the seat view: the only input a bot receives (docs/SEAT_VIEW.md).

Every field is set explicitly from engine state; nothing is serialised wholesale. A field that is
not listed in SEAT_VIEW.md does not belong here.
"""

from __future__ import annotations

from hokm.engine.actions import PlayCard
from hokm.engine.cards import Card, Suit
from hokm.engine.rules import DISCARD_COUNT, DRAW_TURNS, legal_actions
from hokm.engine.scoring import TRICKS_TO_WIN
from hokm.engine.state import MatchState, Phase, Trick
from hokm.engine.variants import Seat, next_seat, seats, side_of, sides
from hokm.views.forgetfulness import forget
from hokm.views.schema import (
    PROFILE_VERSION,
    SCHEMA_VERSION,
    DiscardView,
    DrawView,
    Header,
    HistoryTrick,
    PlayedCardView,
    PlayView,
    Scores,
    SeatView,
    SuitName,
    TrickView,
    TrumpView,
)

SUIT_NAMES: dict[Suit, SuitName] = {
    Suit.SPADES: "spades",
    Suit.HEARTS: "hearts",
    Suit.DIAMONDS: "diamonds",
    Suit.CLUBS: "clubs",
}
DRAW_TURNS_PER_SEAT = DRAW_TURNS // 2  # R5.4 10 turns each


def cards(cs: tuple[Card, ...]) -> list[str]:
    """ADR-013 sorted by suit S H D C, then rank high to low."""
    return [str(c) for c in sorted(cs, key=Card.sort_key)]


def build_view(
    state: MatchState,
    seat: Seat,
    *,
    decision_seq: int,
    forgetfulness: float = 0.0,
    forget_seed: int | None = None,
) -> SeatView:
    """The `raw` view of `seat` at this moment. Only live phases have views (ADR-013).

    `forget_seed` is required when `forgetfulness > 0`; it must be drawn independently of the
    deal seed and stored with the match (ADR-014).
    """
    if seat not in seats(state.mode):
        raise ValueError(f"no seat {seat} in a {state.mode} match")
    if not 0.0 <= forgetfulness <= 1.0:
        raise ValueError("forgetfulness must be between 0 and 1")
    if forgetfulness > 0.0 and forget_seed is None:
        raise ValueError("forgetfulness > 0 needs a forget_seed (never the deal seed, ADR-014)")
    header = _header(state, seat)
    on_turn = state.round.to_act == seat
    match state.phase:
        case Phase.TRUMP:
            return _trump(state, seat, header, on_turn)
        case Phase.DISCARD:
            return _discard(state, seat, header, on_turn)
        case Phase.DRAW:
            return _draw(state, seat, header, on_turn)
        case Phase.PLAY:
            return _play(state, seat, header, decision_seq, forgetfulness, forget_seed)
        case Phase.ROUND_END | Phase.MATCH_END:
            raise ValueError(f"no seat view in phase {state.phase}")


def _header(state: MatchState, seat: Seat) -> Header:
    mode, r = state.mode, state.round
    mine = side_of(seat)
    pair = sides(mode)
    theirs = pair[1] if pair[0] == mine else pair[0]
    me, opp = ("me", "opp") if mode == "2p" else ("us", "them")
    scores: Scores = {
        "round_tricks": {me: state.tricks_of(mine), opp: state.tricks_of(theirs)},
        "tricks_to_win": TRICKS_TO_WIN,
        "match_points": {me: state.points_of(mine), opp: state.points_of(theirs)},
        "match_target": state.config.target_points,
    }
    header: Header = {
        "schema_version": SCHEMA_VERSION,
        "profile": "raw",
        "profile_version": PROFILE_VERSION,
        "mode": mode,
        "seat": seat,
        "hakem": r.hakem,
        "trump_suit": SUIT_NAMES[r.trump] if r.trump is not None else None,
        "scores": scores,
    }
    if mode == "4p":
        header["partner"] = next_seat(mode, next_seat(mode, seat))  # R2.1 partners sit across
    return header


def _trump(state: MatchState, seat: Seat, header: Header, on_turn: bool) -> TrumpView:
    # R4.2 / R5.2 only the hakem has seen any cards before trump
    hand = cards(state.hand(seat)) if seat == state.round.hakem else []
    return {
        **header,
        "phase": "trump",
        "hand": hand,
        "options": list(SUIT_NAMES.values()) if on_turn else [],
    }


def _discard(state: MatchState, seat: Seat, header: Header, on_turn: bool) -> DiscardView:
    hand = cards(state.hand(seat))
    return {
        **header,
        "phase": "discard",
        "hand": hand,
        "options": hand if on_turn else [],
        "discard_count": DISCARD_COUNT,
        "own_discards": [str(c) for c in state.discards(seat)],  # in discard order
    }


def _draw(state: MatchState, seat: Seat, header: Header, on_turn: bool) -> DrawView:
    r = state.round
    # R5.4 the hakem takes the even-numbered turns (0, 2, ...), the opponent the odd ones
    done = r.draw_turns_done
    own_done = (done + 1) // 2 if seat == r.hakem else done // 2
    return {
        **header,
        "phase": "draw",
        "turn": own_done + 1,
        "turns_total": DRAW_TURNS_PER_SEAT,
        "hand": cards(state.hand(seat)),
        "own_discards": [str(c) for c in state.discards(seat)],
        # R5.4 the top card is shown to the seat on turn only
        "card_shown": str(r.stock[0]) if on_turn else None,
        "stock_left": len(r.stock),
        "options": ["keep", "discard"] if on_turn else [],
    }


def _played(trick: Trick) -> list[PlayedCardView]:
    return [{"seat": p.seat, "card": str(p.card)} for p in trick.plays]


def _play(
    state: MatchState,
    seat: Seat,
    header: Header,
    decision_seq: int,
    forgetfulness: float,
    forget_seed: int | None,
) -> PlayView:
    r = state.round
    assert r.trick is not None
    trick: TrickView = {
        "number": r.trick.number,
        "leader": r.trick.leader,
        "cards": _played(r.trick),
    }
    history: list[HistoryTrick] = []
    for t in r.tricks:
        assert t.winner is not None
        history.append({"trick": t.number, "cards": _played(t), "winner": t.winner})
    playable = tuple(a.card for a in legal_actions(state, seat) if isinstance(a, PlayCard))
    view: PlayView = {
        **header,
        "phase": "play",
        "hand": cards(state.hand(seat)),
        "trick": trick,
        "options": cards(playable),
        "history": forget(
            history,
            forgetfulness,
            forget_seed=forget_seed,
            seat=seat,
            decision_seq=decision_seq,
        ),
    }
    if state.mode == "2p":
        view["own_discards"] = [str(c) for c in state.discards(seat)]
    return view
