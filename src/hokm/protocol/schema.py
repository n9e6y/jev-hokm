"""JSON Schema of the protocol, the input for the TypeScript generator (3.7)."""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from hokm.protocol.envelope import ObserverMessage, PlayerMessage
from hokm.protocol.intents import Intent


def player_schema() -> dict[str, Any]:
    """Schema of every message the server sends to a player socket."""
    return TypeAdapter(PlayerMessage).json_schema(mode="serialization")


def observer_schema() -> dict[str, Any]:
    """Schema of every message the server sends to an observer socket."""
    return TypeAdapter(ObserverMessage).json_schema(mode="serialization")


def client_schema() -> dict[str, Any]:
    """Schema of every intent a client sends."""
    return TypeAdapter(Intent).json_schema()
