"""Seat view schema (docs/SEAT_VIEW.md). A view is plain JSON data: strings, ints, lists, dicts.

Each phase has its own TypedDict; `phase` is the discriminator, so `if view["phase"] == "play"`
narrows the type.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from hokm.engine.variants import Mode, Seat

SCHEMA_VERSION = 1
PROFILE_VERSION = 1

type Profile = Literal["raw"]
type SuitName = Literal["spades", "hearts", "diamonds", "clubs"]


class Scores(TypedDict):
    round_tricks: dict[str, int]  # 2p: me / opp; 4p: us / them
    tricks_to_win: int
    match_points: dict[str, int]
    match_target: int


class PlayedCardView(TypedDict):
    seat: Seat
    card: str  # "??" when forgotten (history only)


class TrickView(TypedDict):
    number: int
    leader: Seat
    cards: list[PlayedCardView]


class HistoryTrick(TypedDict):
    trick: int
    cards: list[PlayedCardView]
    winner: Seat


class Header(TypedDict):
    schema_version: int
    profile: Profile
    profile_version: int
    mode: Mode
    seat: Seat
    hakem: Seat
    trump_suit: SuitName | None
    scores: Scores
    partner: NotRequired[Seat]  # 4p only


class TrumpView(Header):
    phase: Literal["trump"]
    hand: list[str]
    options: list[str]


class DiscardView(Header):
    phase: Literal["discard"]
    hand: list[str]
    options: list[str]
    discard_count: int
    own_discards: list[str]


class DrawView(Header):
    phase: Literal["draw"]
    turn: int
    turns_total: int
    hand: list[str]
    own_discards: list[str]
    card_shown: str | None
    stock_left: int
    options: list[str]


class PlayView(Header):
    phase: Literal["play"]
    hand: list[str]
    trick: TrickView
    options: list[str]
    history: list[HistoryTrick]
    own_discards: NotRequired[list[str]]  # 2p only


type SeatView = TrumpView | DiscardView | DrawView | PlayView
