"""Wire protocol: pydantic models for intents, events and server messages (docs/PROTOCOL.md)."""

from hokm.protocol.convert import engine_event_to_wire, intent_to_action
from hokm.protocol.envelope import AckMsg, ErrorMsg, ServerMessage, SnapshotMsg
from hokm.protocol.errors import ErrorCode
from hokm.protocol.events import EventMsg, WirePayload, event_message
from hokm.protocol.intents import ActionIntent, Intent
from hokm.protocol.types import PROTOCOL_VERSION

__all__ = [
    "PROTOCOL_VERSION",
    "AckMsg",
    "ActionIntent",
    "ErrorCode",
    "ErrorMsg",
    "EventMsg",
    "Intent",
    "ServerMessage",
    "SnapshotMsg",
    "WirePayload",
    "engine_event_to_wire",
    "event_message",
    "intent_to_action",
]
