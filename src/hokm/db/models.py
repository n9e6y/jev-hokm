"""SQLAlchemy 2 models, one class per table in docs/DATABASE.md.

Nullable columns: those marked `null` in DATABASE.md, plus fields only known later in a
row's life (a match's winner, a round's trump and result, a failed Jev call's response).
`events`, `decisions` and `jev_calls` are append-only; the first migration installs a
trigger that refuses UPDATE and DELETE on them (non-negotiable 6).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    MetaData,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Stable constraint names, so migrations never depend on the database's own naming.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

APPEND_ONLY_TABLES = ("events", "decisions", "jev_calls")

type Json = Any  # jsonb: whatever JSON the writer stores


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {dict[str, Any]: JSONB, Json: JSONB}


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (CheckConstraint("kind in ('human','bot')", name="kind"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str]
    name: Mapped[str]
    created_at: Mapped[datetime] = _created_at()


class BotProfile(Base):
    __tablename__ = "bot_profiles"
    __table_args__ = (CheckConstraint("bot_type in ('random','rule','jev')", name="bot_type"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str]
    bot_type: Mapped[str]
    view_profile: Mapped[str | None]
    profile_version: Mapped[int | None]
    forgetfulness: Mapped[float] = mapped_column(REAL, server_default="0")
    question_set: Mapped[str | None]
    model_id: Mapped[str | None]
    config: Mapped[Json | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("mode in ('2p','4p')", name="mode"),
        CheckConstraint("target_points in (1,3,5,7)", name="target_points"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    mode: Mapped[str]
    target_points: Mapped[int]
    seed: Mapped[int] = mapped_column(BigInteger)
    # ADR-014: drawn independently of `seed`; None when forgetfulness is off
    forget_seed: Mapped[int | None] = mapped_column(BigInteger)
    removed_cards: Mapped[Json] = mapped_column(JSONB)
    rules_version: Mapped[str]
    app_version: Mapped[str]
    status: Mapped[str]
    winner_side: Mapped[str | None]
    started_at: Mapped[datetime] = _created_at()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MatchSeat(Base):
    __tablename__ = "match_seats"

    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    seat: Mapped[str] = mapped_column(primary_key=True)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"))
    bot_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bot_profiles.id"))
    side: Mapped[str]


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"))
    number: Mapped[int]
    hakem_seat: Mapped[str]
    trump: Mapped[str | None]
    tricks: Mapped[Json | None] = mapped_column(JSONB)
    points: Mapped[int | None]
    kot_type: Mapped[str | None]
    winner_side: Mapped[str | None]


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("visibility in ('all','seat','admin')", name="visibility"),
        UniqueConstraint("match_id", "seq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"))
    round_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rounds.id"))
    seq: Mapped[int]
    name: Mapped[str]
    visibility: Mapped[str]
    seat: Mapped[str | None]
    payload: Mapped[Json] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint("role in ('bot','advisor')", name="role"),
        CheckConstraint("decision_type in ('trump','discard','draw','play')", name="decision_type"),
        CheckConstraint("status in ('ok','retried_ok','failed','forced')", name="status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"))
    round_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rounds.id"))
    event_seq: Mapped[int]
    seat: Mapped[str]
    role: Mapped[str]
    bot_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bot_profiles.id"))
    decision_type: Mapped[str]
    view: Mapped[Json] = mapped_column(JSONB)  # exactly the JSON sent to Jev
    question_id: Mapped[str]
    question_text: Mapped[str]
    options: Mapped[Json] = mapped_column(JSONB)
    forced: Mapped[bool]
    final_choice: Mapped[str | None]
    attempts: Mapped[int]
    status: Mapped[str]
    created_at: Mapped[datetime] = _created_at()


class TruthSnapshot(Base):
    """Hidden state at a decision. Never reaches a player's client."""

    __tablename__ = "truth_snapshots"

    decision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decisions.id"), primary_key=True)
    all_hands: Mapped[Json] = mapped_column(JSONB)
    stock: Mapped[Json] = mapped_column(JSONB)
    all_discards: Mapped[Json] = mapped_column(JSONB)


class JevCall(Base):
    __tablename__ = "jev_calls"

    id: Mapped[uuid.UUID] = _uuid_pk()
    decision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decisions.id"))
    attempt: Mapped[int]
    model_id: Mapped[str]
    request: Mapped[Json] = mapped_column(JSONB)
    response: Mapped[Json | None] = mapped_column(JSONB)  # None when the call failed
    probabilities: Mapped[Json | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None]
    http_status: Mapped[int | None]
    error: Mapped[str | None]
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric)
    created_at: Mapped[datetime] = _created_at()


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str]
    hypothesis: Mapped[str | None]
    arms: Mapped[Json] = mapped_column(JSONB)
    seed_set: Mapped[Json] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class ExperimentMatch(Base):
    __tablename__ = "experiment_matches"

    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiments.id"), primary_key=True)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    arm: Mapped[str]
