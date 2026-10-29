"""Shared wire types (docs/PROTOCOL.md). Cards travel as strings like `10H`."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict

from hokm.engine.cards import Card

PROTOCOL_VERSION = 1


class WireModel(BaseModel):
    """Base of every message: immutable, and unknown fields are an error."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_card(text: str) -> str:
    return str(Card.parse(text))  # R1.3 rejects anything that is not rank + suit


type CardStr = Annotated[str, AfterValidator(_check_card)]
type SuitLetter = Literal["S", "H", "D", "C"]
