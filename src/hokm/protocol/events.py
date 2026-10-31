"""Event payloads and the `event` messages that carry them (docs/PROTOCOL.md).

Names match `hokm.engine.events` exactly. A payload model is also its own redacted form: a
field the receiving seat may not see is left out of the JSON (`HiddenCard`), so others get
`{seat}` only. The redaction functions themselves arrive with the server (3.4).

Bot events go to observers and admins only, so players and observers get separate unions.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from hokm.engine.state import KotType
from hokm.engine.variants import Mode, Seat, Side
from hokm.protocol.types import PROTOCOL_VERSION, CardStr, SuitLetter, WireModel

# A card the receiving seat may not see: None, and left out of the JSON entirely.
HiddenCard = Annotated[CardStr | None, Field(exclude_if=lambda v: v is None)]

# docs/JEV.md guard policy: transport failure after backoff, or 3 invalid answers. A fixed
# vocabulary, so no exception text or Jev response body can reach a client.
type PauseReason = Literal["transport_error", "invalid_answers"]

# --- payloads ----------------------------------------------------------------------------------


class MatchStartedPayload(WireModel):
    mode: Mode
    target_points: int
    seats: list[Seat]  # the seed stays server-side


class RoundStartedPayload(WireModel):
    number: int
    hakem: Seat


class CardsDealtPayload(WireModel):
    seat: Seat
    cards: list[CardStr]  # owner only (ADR-012)


class TrumpDeclaredPayload(WireModel):
    hakem: Seat
    suit: SuitLetter


class CardDiscardedPayload(WireModel):
    seat: Seat
    card: HiddenCard = None  # only `seat` sees it (R5.3)


class CardShownPayload(WireModel):
    seat: Seat
    card: CardStr  # owner only (R5.4)


class DrawResolvedPayload(WireModel):
    seat: Seat
    kept: HiddenCard = None  # only `seat` sees them (R5.4)
    dropped: HiddenCard = None


class CardPlayedPayload(WireModel):
    seat: Seat
    card: CardStr


class TrickWonPayload(WireModel):
    number: int
    winner: Seat
    tricks_won: list[int]  # per side, after this trick


class RoundEndedPayload(WireModel):
    number: int
    hakem: Seat
    tricks_won: list[int]  # per side
    winner: Side
    points: int
    kot: KotType | None
    match_points: list[int]  # per side, after this round
    next_hakem: Seat | None  # None when this round ended the match (R3.5)


class MatchEndedPayload(WireModel):
    winner: Side
    points: list[int]


class BotDecisionPayload(WireModel):
    """Server-only: observers and admins (details through the debug API)."""

    seat: Seat
    decision_id: str


class BotPausedPayload(WireModel):
    """Server-only: a bot could not answer and the game is paused."""

    seat: Seat
    reason: PauseReason


type WirePayload = (
    MatchStartedPayload
    | RoundStartedPayload
    | CardsDealtPayload
    | TrumpDeclaredPayload
    | CardDiscardedPayload
    | CardShownPayload
    | DrawResolvedPayload
    | CardPlayedPayload
    | TrickWonPayload
    | RoundEndedPayload
    | MatchEndedPayload
    | BotDecisionPayload
    | BotPausedPayload
)

# --- messages ----------------------------------------------------------------------------------


class _EventMsg(WireModel):
    v: Literal[1] = PROTOCOL_VERSION
    type: Literal["event"] = "event"
    match_id: str
    seq: Annotated[int, Field(ge=0)]  # +1 per match event, shared by all seats


class MatchStartedMsg(_EventMsg):
    name: Literal["MatchStarted"] = "MatchStarted"
    payload: MatchStartedPayload


class RoundStartedMsg(_EventMsg):
    name: Literal["RoundStarted"] = "RoundStarted"
    payload: RoundStartedPayload


class CardsDealtMsg(_EventMsg):
    name: Literal["CardsDealt"] = "CardsDealt"
    payload: CardsDealtPayload


class TrumpDeclaredMsg(_EventMsg):
    name: Literal["TrumpDeclared"] = "TrumpDeclared"
    payload: TrumpDeclaredPayload


class CardDiscardedMsg(_EventMsg):
    name: Literal["CardDiscarded"] = "CardDiscarded"
    payload: CardDiscardedPayload


class CardShownMsg(_EventMsg):
    name: Literal["CardShown"] = "CardShown"
    payload: CardShownPayload


class DrawResolvedMsg(_EventMsg):
    name: Literal["DrawResolved"] = "DrawResolved"
    payload: DrawResolvedPayload


class CardPlayedMsg(_EventMsg):
    name: Literal["CardPlayed"] = "CardPlayed"
    payload: CardPlayedPayload


class TrickWonMsg(_EventMsg):
    name: Literal["TrickWon"] = "TrickWon"
    payload: TrickWonPayload


class RoundEndedMsg(_EventMsg):
    name: Literal["RoundEnded"] = "RoundEnded"
    payload: RoundEndedPayload


class MatchEndedMsg(_EventMsg):
    name: Literal["MatchEnded"] = "MatchEnded"
    payload: MatchEndedPayload


class BotDecisionMsg(_EventMsg):
    name: Literal["BotDecision"] = "BotDecision"
    payload: BotDecisionPayload


class BotPausedMsg(_EventMsg):
    name: Literal["BotPaused"] = "BotPaused"
    payload: BotPausedPayload


type _GameEventMsg = (
    MatchStartedMsg
    | RoundStartedMsg
    | CardsDealtMsg
    | TrumpDeclaredMsg
    | CardDiscardedMsg
    | CardShownMsg
    | DrawResolvedMsg
    | CardPlayedMsg
    | TrickWonMsg
    | RoundEndedMsg
    | MatchEndedMsg
)
# What a player socket may receive: game events only, never bot internals.
type PlayerEventMsg = Annotated[_GameEventMsg, Field(discriminator="name")]
# Observers and admins also see bot decisions and pauses.
type ObserverEventMsg = Annotated[
    _GameEventMsg | BotDecisionMsg | BotPausedMsg, Field(discriminator="name")
]

MESSAGE_FOR: dict[type[WirePayload], type[_EventMsg]] = {
    MatchStartedPayload: MatchStartedMsg,
    RoundStartedPayload: RoundStartedMsg,
    CardsDealtPayload: CardsDealtMsg,
    TrumpDeclaredPayload: TrumpDeclaredMsg,
    CardDiscardedPayload: CardDiscardedMsg,
    CardShownPayload: CardShownMsg,
    DrawResolvedPayload: DrawResolvedMsg,
    CardPlayedPayload: CardPlayedMsg,
    TrickWonPayload: TrickWonMsg,
    RoundEndedPayload: RoundEndedMsg,
    MatchEndedPayload: MatchEndedMsg,
    BotDecisionPayload: BotDecisionMsg,
    BotPausedPayload: BotPausedMsg,
}


def event_message(match_id: str, seq: int, payload: WirePayload) -> _EventMsg:
    """Wrap a payload in its `event` message."""
    return MESSAGE_FOR[type(payload)](match_id=match_id, seq=seq, payload=payload)  # pyright: ignore[reportCallIssue]
