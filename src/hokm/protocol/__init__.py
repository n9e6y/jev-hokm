"""Wire protocol: pydantic models for intents, events and server messages (docs/PROTOCOL.md)."""

from hokm.protocol.convert import engine_event_to_wire, intent_to_action
from hokm.protocol.envelope import (
    AckMsg,
    ErrorMsg,
    ObserverMessage,
    ObserverSnapshotMsg,
    PlayerMessage,
    SnapshotMsg,
)
from hokm.protocol.errors import ERROR_TEXT, ErrorCode
from hokm.protocol.events import ObserverEventMsg, PlayerEventMsg, WirePayload, event_message
from hokm.protocol.intents import ActionIntent, Intent
from hokm.protocol.types import PROTOCOL_VERSION

__all__ = [
    "ERROR_TEXT",
    "PROTOCOL_VERSION",
    "AckMsg",
    "ActionIntent",
    "ErrorCode",
    "ErrorMsg",
    "Intent",
    "ObserverEventMsg",
    "ObserverMessage",
    "ObserverSnapshotMsg",
    "PlayerEventMsg",
    "PlayerMessage",
    "SnapshotMsg",
    "WirePayload",
    "engine_event_to_wire",
    "event_message",
    "intent_to_action",
]
