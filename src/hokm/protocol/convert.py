"""Pure conversions between engine objects and wire models. No redaction here (3.4)."""

from __future__ import annotations

from hokm.engine import actions as act
from hokm.engine import events as ev
from hokm.engine.cards import Card, Suit
from hokm.engine.variants import Seat
from hokm.protocol import events as wire
from hokm.protocol.intents import (
    ActionIntent,
    ChooseTrumpIntent,
    DiscardIntent,
    DrawDecisionIntent,
    PlayCardIntent,
)


def engine_event_to_wire(event: ev.Event) -> wire.WirePayload:
    """The full, unredacted payload for an engine event."""
    match event:
        case ev.MatchStarted():
            return wire.MatchStartedPayload(
                mode=event.mode, target_points=event.target_points, seats=list(event.seats)
            )
        case ev.RoundStarted():
            return wire.RoundStartedPayload(number=event.number, hakem=event.hakem)
        case ev.CardsDealt():
            return wire.CardsDealtPayload(seat=event.seat, cards=[str(c) for c in event.cards])
        case ev.TrumpDeclared():
            return wire.TrumpDeclaredPayload(hakem=event.hakem, suit=event.suit.value)
        case ev.CardDiscarded():
            return wire.CardDiscardedPayload(seat=event.seat, card=str(event.card))
        case ev.CardShown():
            return wire.CardShownPayload(seat=event.seat, card=str(event.card))
        case ev.DrawResolved():
            return wire.DrawResolvedPayload(
                seat=event.seat, kept=str(event.kept), dropped=str(event.dropped)
            )
        case ev.CardPlayed():
            return wire.CardPlayedPayload(seat=event.seat, card=str(event.card))
        case ev.TrickWon():
            return wire.TrickWonPayload(
                number=event.number, winner=event.winner, tricks_won=list(event.tricks_won)
            )
        case ev.RoundEnded():
            return wire.RoundEndedPayload(
                number=event.number,
                hakem=event.hakem,
                tricks_won=list(event.tricks_won),
                winner=event.winner,
                points=event.points,
                kot=event.kot,
                match_points=list(event.match_points),
                next_hakem=event.next_hakem,
            )
        case ev.MatchEnded():
            return wire.MatchEndedPayload(winner=event.winner, points=list(event.points))


def intent_to_action(seat: Seat, intent: ActionIntent) -> act.SeatAction:
    """The engine action for an intent sent by `seat` (the server knows the sender)."""
    match intent:
        case ChooseTrumpIntent():
            return act.ChooseTrump(seat, Suit(intent.suit))
        case DiscardIntent():
            return act.Discard(seat, tuple(Card.parse(c) for c in intent.cards))
        case DrawDecisionIntent():
            return act.DrawDecision(seat, intent.keep)
        case PlayCardIntent():
            return act.PlayCard(seat, Card.parse(intent.card))
