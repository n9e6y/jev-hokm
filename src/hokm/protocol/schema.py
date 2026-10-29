"""JSON Schema of the protocol, the input for the TypeScript generator (3.7)."""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from hokm.protocol.envelope import ServerMessage
from hokm.protocol.intents import Intent


def server_schema() -> dict[str, Any]:
    """Schema of every message the server sends."""
    return TypeAdapter(ServerMessage).json_schema()


def client_schema() -> dict[str, Any]:
    """Schema of every intent a client sends."""
    return TypeAdapter(Intent).json_schema()
