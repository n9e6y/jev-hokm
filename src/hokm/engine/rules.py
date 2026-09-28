"""Game flow: `new_match`, `legal_actions`, `apply` (R3–R8)."""

from __future__ import annotations

from dataclasses import replace
from itertools import combinations

from hokm.engine.actions import (
    Action,
    ChooseTrump,
    Discard,
    DrawDecision,
    NextRound,
    PlayCard,
)
from hokm.engine.cards import Card, Suit
from hokm.engine.deck import first_hakem, shuffled_deck
from hokm.engine.errors import BadPhase, IllegalAction, MatchOver, NotYourTurn
from hokm.engine.events import (
    CardDiscarded,
    CardPlayed,
    CardsDealt,
    CardShown,
    DrawResolved,
    Event,
    MatchEnded,
    MatchStarted,
    RoundEnded,
    RoundStarted,
    TrickWon,
    TrumpDeclared,
)
from hokm.engine.scoring import match_winner, next_hakem, round_winner, score_round
from hokm.engine.state import (
    MatchState,
    Phase,
    Play,
    RoundResult,
    RoundState,
    Trick,
    replace_at,
    sorted_cards,
)
from hokm.engine.variants import (
    MatchConfig,
    Mode,
    Seat,
    next_seat,
    seat_index,
    seats,
    side_index,
    side_of,
    sides,
)

FIRST_DEAL = 5  # R4.1, R5.1
LATER_DEALS = (4, 4)  # R4.4
DISCARD_COUNT = 2  # R5.3
DRAW_TURNS = 20  # R5.4
HAND_SIZE = 13  # R4.4, R5.5

type Transition = tuple[MatchState, tuple[Event, ...]]


def deal_order(mode: Mode, hakem: Seat) -> tuple[Seat, ...]:
    """Seats in play order starting with the hakem (R4.1, R4.4, R5.1)."""
    order = seats(mode)
    i = order.index(hakem)
    return order[i:] + order[:i]


# --- match and round start ---------------------------------------------------------------


def new_match(config: MatchConfig) -> Transition:
    """Start a match: seeded first hakem (R3.2), then deal round 1."""
    points = (0,) * len(sides(config.mode))
    state, events = _start_round(config, 1, first_hakem(config), points, ())
    started = MatchStarted(config.mode, config.target_points, seats(config.mode))
    return state, (started, *events)


def _start_round(
    config: MatchConfig,
    number: int,
    hakem: Seat,
    points: tuple[int, ...],
    results: tuple[RoundResult, ...],
) -> Transition:
    mode = config.mode
    deck = shuffled_deck(config, number)  # R3.4
    hands: list[tuple[Card, ...]] = [()] * len(seats(mode))
    # R4.1 / R5.1 five cards each, starting with the hakem, in play order
    for i, seat in enumerate(deal_order(mode, hakem)):
        hands[seat_index(mode, seat)] = sorted_cards(deck[i * FIRST_DEAL : (i + 1) * FIRST_DEAL])
    round_ = RoundState(
        number=number,
        hakem=hakem,
        hands=tuple(hands),
        stock=deck[FIRST_DEAL * len(hands) :],
        discards=((),) * len(hands),
        tricks_won=(0,) * len(sides(mode)),
        to_act=hakem,
    )
    state = MatchState(config, Phase.TRUMP, round_, points, results)
    # R4.2 / R5.2 only the hakem sees their cards before trump
    return state, (RoundStarted(number, hakem), CardsDealt(hakem, state.hand(hakem)))


# --- legal actions -----------------------------------------------------------------------


def playable_cards(hand: tuple[Card, ...], trick: Trick) -> tuple[Card, ...]:
    """R7.2 follow the led suit if possible; otherwise (and when leading, R7.5) any card."""
    led = trick.led_suit
    following = tuple(c for c in hand if c.suit == led)
    return following or hand


def legal_actions(state: MatchState, seat: Seat) -> tuple[Action, ...]:
    """Every action `seat` may take now; empty when it is not that seat's turn."""
    r = state.round
    if r.to_act != seat or state.phase in (Phase.ROUND_END, Phase.MATCH_END):
        return ()
    hand = state.hand(seat)
    if state.phase is Phase.TRUMP:
        return tuple(ChooseTrump(seat, s) for s in Suit)  # R6.1 any suit
    if state.phase is Phase.DISCARD:
        return tuple(Discard(seat, pair) for pair in combinations(hand, DISCARD_COUNT))
    if state.phase is Phase.DRAW:
        return (DrawDecision(seat, keep=True), DrawDecision(seat, keep=False))
    assert r.trick is not None
    return tuple(PlayCard(seat, c) for c in playable_cards(hand, r.trick))


# --- apply -------------------------------------------------------------------------------


def apply(state: MatchState, action: Action) -> Transition:
    """Validate `action` and return the new state plus the events it caused.

    Raises MatchOver, BadPhase, NotYourTurn or IllegalAction (checked in that order);
    the input state is never modified.
    """
    if state.phase is Phase.MATCH_END:
        raise MatchOver("the match is over")
    match action:
        case ChooseTrump():
            return _choose_trump(state, action)
        case Discard():
            return _discard(state, action)
        case DrawDecision():
            return _draw(state, action)
        case PlayCard():
            return _play(state, action)
        case NextRound():
            return _next_round(state, action)


def _check_phase(state: MatchState, phase: Phase, action: Action) -> None:
    if state.phase is not phase:
        raise BadPhase(f"{type(action).__name__} is not allowed in phase {state.phase}")


def _check_turn(state: MatchState, phase: Phase, action: Action, seat: Seat) -> None:
    _check_phase(state, phase, action)
    if state.round.to_act != seat:
        raise NotYourTurn(f"it is {state.round.to_act}'s turn, not {seat}'s")


def _with_round(state: MatchState, phase: Phase, round_: RoundState) -> MatchState:
    return replace(state, phase=phase, round=round_)


def _set_hand(
    state: MatchState, seat: Seat, hand: tuple[Card, ...]
) -> tuple[tuple[Card, ...], ...]:
    return replace_at(state.round.hands, seat_index(state.mode, seat), sorted_cards(hand))


def _choose_trump(state: MatchState, action: ChooseTrump) -> Transition:
    # R4.3 / R6 only the hakem chooses; to_act is the hakem during the trump phase
    _check_turn(state, Phase.TRUMP, action, action.seat)
    r = state.round
    events: list[Event] = [TrumpDeclared(r.hakem, action.suit)]  # R6.2 announced to all
    r = replace(r, trump=action.suit)  # R6.1 any suit, fixed for the round
    if state.mode == "2p":
        # R5.2 the opponent may now see their 5; R5.3 opening discard, hakem first
        opponent = next_seat(state.mode, r.hakem)
        events.append(CardsDealt(opponent, state.hand(opponent)))
        return _with_round(state, Phase.DISCARD, r), tuple(events)

    # R4.4 deal 4 more to each, then 4 more, each time starting with the hakem
    order = deal_order(state.mode, r.hakem)
    hands = list(r.hands)
    pos = 0
    for batch in LATER_DEALS:
        for seat in order:
            i = seat_index(state.mode, seat)
            hands[i] = hands[i] + r.stock[pos : pos + batch]
            pos += batch
    if pos != len(r.stock):
        raise AssertionError("R4.4 the stock must be fully dealt")
    new_hands = tuple(sorted_cards(h) for h in hands)
    for seat in order:
        full = new_hands[seat_index(state.mode, seat)]
        seen_before = state.hand(seat) if seat == r.hakem else ()
        # ADR-012 each seat is told every card that just became visible to it
        events.append(CardsDealt(seat, tuple(c for c in full if c not in seen_before)))
    r = replace(r, hands=new_hands, stock=(), trick=Trick(1, r.hakem))  # R7.1 hakem leads
    return _with_round(state, Phase.PLAY, r), tuple(events)


def _discard(state: MatchState, action: Discard) -> Transition:
    _check_turn(state, Phase.DISCARD, action, action.seat)
    seat, cards, hand = action.seat, action.cards, state.hand(action.seat)
    # R5.3 exactly two distinct cards from the hand
    if len(cards) != DISCARD_COUNT or len(set(cards)) != DISCARD_COUNT:
        raise IllegalAction(f"discard exactly {DISCARD_COUNT} distinct cards")
    missing = [str(c) for c in cards if c not in hand]
    if missing:
        raise IllegalAction(f"not in hand: {' '.join(missing)}")
    r = state.round
    i = seat_index(state.mode, seat)
    r = replace(
        r,
        hands=_set_hand(state, seat, tuple(c for c in hand if c not in cards)),
        discards=replace_at(r.discards, i, r.discards[i] + cards),
    )
    events: list[Event] = [CardDiscarded(seat, c) for c in cards]
    if seat == r.hakem:
        # R5.3 hakem first, then the opponent
        r = replace(r, to_act=next_seat(state.mode, seat))
        return _with_round(state, Phase.DISCARD, r), tuple(events)
    # R5.4 draw phase: hakem takes the first turn and is shown the top card
    r = replace(r, to_act=r.hakem)
    events.append(CardShown(r.hakem, r.stock[0]))
    return _with_round(state, Phase.DRAW, r), tuple(events)


def _draw(state: MatchState, action: DrawDecision) -> Transition:
    _check_turn(state, Phase.DRAW, action, action.seat)
    seat, r = action.seat, state.round
    c1, c2 = r.stock[0], r.stock[1]
    # R5.4 keep: C1 to hand, C2 to discards. discard: C1 to discards, C2 to hand.
    kept, dropped = (c1, c2) if action.keep else (c2, c1)
    i = seat_index(state.mode, seat)
    r = replace(
        r,
        hands=_set_hand(state, seat, state.hand(seat) + (kept,)),
        discards=replace_at(r.discards, i, r.discards[i] + (dropped,)),
        stock=r.stock[2:],
        draw_turns_done=r.draw_turns_done + 1,
    )
    events: list[Event] = [DrawResolved(seat, kept, dropped)]
    if r.draw_turns_done < DRAW_TURNS:
        nxt = next_seat(state.mode, seat)  # R5.4 turns alternate
        events.append(CardShown(nxt, r.stock[0]))
        return _with_round(state, Phase.DRAW, replace(r, to_act=nxt)), tuple(events)
    # R5.5 after 20 turns the stock is empty and both hands hold 13
    if r.stock or any(len(h) != HAND_SIZE for h in r.hands):
        raise AssertionError("R5.5 draw phase must end with 13 cards each and no stock")
    r = replace(r, to_act=r.hakem, trick=Trick(1, r.hakem))  # R7.1 hakem leads
    return _with_round(state, Phase.PLAY, r), tuple(events)


def trick_winner(trick: Trick, trump: Suit | None) -> Seat:
    """R7.3 highest trump played; if none, highest card of the led suit."""
    if not trick.plays:
        raise ValueError("empty trick")
    led = trick.led_suit

    def strength(play: Play) -> tuple[bool, bool, int]:
        return (play.card.suit == trump, play.card.suit == led, play.card.rank)

    return max(trick.plays, key=strength).seat


def _play(state: MatchState, action: PlayCard) -> Transition:
    _check_turn(state, Phase.PLAY, action, action.seat)
    seat, card, r = action.seat, action.card, state.round
    trick = r.trick
    assert trick is not None
    hand = state.hand(seat)
    if card not in hand:
        raise IllegalAction(f"{card} is not in {seat}'s hand")
    if card not in playable_cards(hand, trick):
        raise IllegalAction(f"{seat} must follow {trick.led_suit}")  # R7.2
    trick = replace(trick, plays=(*trick.plays, Play(seat, card)))
    r = replace(r, hands=_set_hand(state, seat, tuple(c for c in hand if c != card)))
    events: list[Event] = [CardPlayed(seat, card)]
    if len(trick.plays) < len(seats(state.mode)):
        r = replace(r, trick=trick, to_act=next_seat(state.mode, seat))
        return _with_round(state, Phase.PLAY, r), tuple(events)

    winner = trick_winner(trick, r.trump)  # R7.3
    s = side_index(state.mode, side_of(winner))
    tricks_won = replace_at(r.tricks_won, s, r.tricks_won[s] + 1)
    events.append(TrickWon(trick.number, winner, tricks_won))
    r = replace(r, tricks_won=tricks_won, tricks=(*r.tricks, replace(trick, winner=winner)))
    if round_winner(state.mode, tricks_won) is not None:
        # R8.1 the round ends the moment a side has 7 tricks; remaining cards are not played
        return _end_round(state, replace(r, trick=None, to_act=None), events)
    r = replace(r, trick=Trick(trick.number + 1, winner), to_act=winner)  # R7.4 winner leads
    return _with_round(state, Phase.PLAY, r), tuple(events)


# --- round and match end -----------------------------------------------------------------


def _end_round(state: MatchState, r: RoundState, events: list[Event]) -> Transition:
    mode = state.mode
    assert r.trump is not None
    winner, points, kot = score_round(mode, r.hakem, r.tricks_won)  # R8.2, R8.3
    w = side_index(mode, winner)
    match_points = replace_at(state.points, w, state.points[w] + points)
    result = RoundResult(r.number, r.hakem, r.trump, r.tricks_won, winner, points, kot)
    champion = match_winner(mode, match_points, state.config.target_points)  # R3.5
    successor = None if champion is not None else next_hakem(mode, r.hakem, winner)  # R3.3
    events.append(
        RoundEnded(r.number, r.hakem, r.tricks_won, winner, points, kot, match_points, successor)
    )
    state = replace(state, round=r, points=match_points, results=(*state.results, result))
    if champion is not None:
        events.append(MatchEnded(champion, match_points))
        return replace(state, phase=Phase.MATCH_END, winner=champion), tuple(events)
    return replace(state, phase=Phase.ROUND_END), tuple(events)


def _next_round(state: MatchState, action: NextRound) -> Transition:
    _check_phase(state, Phase.ROUND_END, action)
    last = state.results[-1]
    hakem = next_hakem(state.mode, last.hakem, last.winner)  # R3.3
    # R3.4 every round shuffles the full deck again with its own round seed
    return _start_round(state.config, last.number + 1, hakem, state.points, state.results)
