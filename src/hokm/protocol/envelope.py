"""Server → client messages other than events: snapshot, ack, error (docs/PROTOCOL.md)."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from hokm.engine.variants import Seat
from hokm.protocol.errors import ERROR_TEXT, ErrorCode
from hokm.protocol.events import ObserverEventMsg, PlayerEventMsg
from hokm.protocol.types import PROTOCOL_VERSION, WireModel


class _Msg(WireModel):
    v: Literal[1] = PROTOCOL_VERSION
    match_id: str


class SnapshotMsg(_Msg):
    """State of one seat (or an observer) at `seq`. The view layout is settled with the server
    in 3.4; until then `view` is the seat view JSON, passed through as data."""

    type: Literal["snapshot"] = "snapshot"
    seq: Annotated[int, Field(ge=0)]
    view: dict[str, JsonValue]
    whose_turn: Seat | None = None


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
    SnapshotMsg | AckMsg | ErrorMsg | ObserverEventMsg, Field(discriminator="type")
]
