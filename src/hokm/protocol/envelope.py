"""Server → client messages other than events: snapshot, ack, error (docs/PROTOCOL.md)."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from hokm.engine.state import KotType
from hokm.engine.variants import Seat, Side
from hokm.protocol.errors import ERROR_TEXT, ErrorCode
from hokm.protocol.events import ObserverEventMsg, PlayerEventMsg
from hokm.protocol.types import PROTOCOL_VERSION, CardStr, SuitLetter, WireModel
from hokm.views.schema import SeatView

type MatchPhase = Literal["trump", "discard", "draw", "play", "round_end", "match_end"]
_NO_VIEW_PHASES = ("round_end", "match_end")


class _Msg(WireModel):
    v: Literal[1] = PROTOCOL_VERSION
    match_id: str


class PlayedCard(WireModel):
    seat: Seat
    card: CardStr


class LastTrick(WireModel):
    """The round's last completed trick; every card in it was played face up."""

    number: int
    leader: Seat
    cards: list[PlayedCard]
    winner: Seat


class RoundResult(WireModel):
    number: int
    hakem: Seat
    trump: SuitLetter
    tricks_won: list[int]  # per side
    winner: Side
    points: int
    kot: KotType | None


class _Snapshot(_Msg):
    type: Literal["snapshot"] = "snapshot"
    seq: Annotated[int, Field(ge=0)]  # the last event already reflected here
    phase: MatchPhase
    whose_turn: Seat | None
    last_trick: LastTrick | None
    match_points: list[int]  # per side
    last_round: RoundResult | None  # set between rounds and after the match
    winner: Side | None  # set after the match


class SnapshotMsg(_Snapshot):
    """What one seat sees on (re)connect: its `raw` seat view plus public table state.
    `view` is None between rounds and after the match (no seat view exists then, ADR-013)."""

    seat: Seat
    view: SeatView | None

    @model_validator(mode="after")
    def _own_view_only(self) -> SnapshotMsg:
        if (self.view is None) != (self.phase in _NO_VIEW_PHASES):
            raise ValueError("a seat view exists exactly in the live phases")
        if self.view is not None and self.view["seat"] != self.seat:
            raise ValueError("a snapshot carries only its own seat's view")
        return self


class ObserverSnapshotMsg(_Snapshot):
    """Observers of bot-only matches and replays: every seat's view, so every hand."""

    views: dict[Seat, SeatView]

    @model_validator(mode="after")
    def _views_by_seat(self) -> ObserverSnapshotMsg:
        if (not self.views) != (self.phase in _NO_VIEW_PHASES):
            raise ValueError("seat views exist exactly in the live phases")
        if any(view["seat"] != seat for seat, view in self.views.items()):
            raise ValueError("each view sits under its own seat")
        return self


class AckMsg(_Msg):
    type: Literal["ack"] = "ack"
    intent_id: UUID


class ErrorMsg(_Msg):
    type: Literal["error"] = "error"
    intent_id: UUID | None = None  # None when the payload was too broken to carry one
    code: ErrorCode
    message: str = Field(default_factory=lambda data: ERROR_TEXT[data["code"]])

    @model_validator(mode="after")
    def _fixed_text(self) -> ErrorMsg:
        if self.message != ERROR_TEXT[self.code]:
            raise ValueError("error messages use the fixed text of their code")
        return self


# Player sockets and observer sockets get separate unions, so a bot event cannot be typed as
# a player message.
type PlayerMessage = Annotated[
    SnapshotMsg | AckMsg | ErrorMsg | PlayerEventMsg, Field(discriminator="type")
]
type ObserverMessage = Annotated[
    ObserverSnapshotMsg | AckMsg | ErrorMsg | ObserverEventMsg, Field(discriminator="type")
]
