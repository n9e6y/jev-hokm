"""Intents, client → server. Every intent carries a client-generated `intent_id` so retries are
idempotent. Whether an intent is legal is the engine's decision, not this module's."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from hokm.protocol.types import PROTOCOL_VERSION, CardStr, SuitLetter, WireModel


class _Intent(WireModel):
    v: Literal[1] = PROTOCOL_VERSION
    intent_id: UUID


class ChooseTrumpIntent(_Intent):
    intent: Literal["choose_trump"] = "choose_trump"
    suit: SuitLetter


class DiscardIntent(_Intent):
    intent: Literal["discard"] = "discard"
    cards: Annotated[list[CardStr], Field(min_length=2, max_length=2)]  # R5.3 exactly two


class DrawDecisionIntent(_Intent):
    intent: Literal["draw_decision"] = "draw_decision"
    keep: bool


class PlayCardIntent(_Intent):
    intent: Literal["play_card"] = "play_card"
    card: CardStr


class RequestHintIntent(_Intent):
    """Phase 5+ (task 5.4, advisor). Not in `Intent` yet, so clients cannot send it."""

    intent: Literal["request_hint"] = "request_hint"


type ActionIntent = ChooseTrumpIntent | DiscardIntent | DrawDecisionIntent | PlayCardIntent
type Intent = Annotated[
    ChooseTrumpIntent | DiscardIntent | DrawDecisionIntent | PlayCardIntent,
    Field(discriminator="intent"),
]
