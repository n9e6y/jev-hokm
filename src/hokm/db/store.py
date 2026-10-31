"""Append-only event store (3.3): write a match's events, rebuild the match from them.

The `events` table is the single record of a match. Payloads are the full, unredacted wire
payloads of `hokm.protocol`; hiding cards from other seats happens when sending (3.4).
To rebuild, the seat actions are read back out of the events (a `CardPlayed` is a `PlayCard`,
and so on) and replayed through the engine; the replay must reproduce every stored event
exactly, or the log is reported as corrupt.

All functions take a `Connection` and never commit: the caller owns the transaction.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any, Literal

from sqlalchemy import Connection, func, insert, select, update

from hokm.db.models import BotProfile, Event, Match, MatchSeat, Player, Round
from hokm.engine import events as ev
from hokm.engine.actions import Action, ChooseTrump, Discard, DrawDecision, NextRound, PlayCard
from hokm.engine.cards import Card, Suit
from hokm.engine.errors import EngineError
from hokm.engine.replay import Replay, replay
from hokm.engine.variants import RULES_VERSION, MatchConfig, Seat, seats, side_of
from hokm.protocol import engine_event_to_wire

type Visibility = Literal["all", "seat", "admin"]

# docs/PROTOCOL.md "Visible to". `seat` rows hold the owner's full payload; what other seats
# get (CardDiscarded, DrawResolved: `{seat}` only) is the sender's redaction.
_SEAT_ONLY = frozenset({"CardsDealt", "CardShown", "CardDiscarded", "DrawResolved"})


class CorruptLog(ValueError):
    """The stored events are not what replaying their own actions produces."""


@dataclass(frozen=True, slots=True)
class SeatAssignment:
    player_id: uuid.UUID
    bot_profile_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class StoredMatch:
    match_id: uuid.UUID
    config: MatchConfig
    forget_seed: int | None
    replay: Replay


# --- setup rows --------------------------------------------------------------------------------


def add_player(conn: Connection, kind: Literal["human", "bot"], name: str) -> uuid.UUID:
    player_id = uuid.uuid4()
    conn.execute(insert(Player).values(id=player_id, kind=kind, name=name))
    return player_id


def add_bot_profile(
    conn: Connection, name: str, bot_type: Literal["random", "rule", "jev"], **settings: Any
) -> uuid.UUID:
    """`settings`: any other `bot_profiles` column (view_profile, model_id, config, ...)."""
    profile_id = uuid.uuid4()
    conn.execute(insert(BotProfile).values(id=profile_id, name=name, bot_type=bot_type, **settings))
    return profile_id


def create_match(
    conn: Connection,
    config: MatchConfig,
    assignments: Mapping[Seat, SeatAssignment],
    *,
    forget_seed: int | None = None,
) -> uuid.UUID:
    """Write the `matches` row and one `match_seats` row per seat. No events yet."""
    if set(assignments) != set(seats(config.mode)):
        raise ValueError(f"{config.mode} needs exactly the seats {seats(config.mode)}")
    match_id = uuid.uuid4()
    conn.execute(
        insert(Match).values(
            id=match_id,
            mode=config.mode,
            target_points=config.target_points,
            seed=config.seed,
            forget_seed=forget_seed,
            removed_cards=[str(c) for c in config.removed_cards],
            rules_version=RULES_VERSION,
            app_version=version("hokm"),
            status="running",
        )
    )
    conn.execute(
        insert(MatchSeat),
        [
            {
                "match_id": match_id,
                "seat": seat,
                "player_id": a.player_id,
                "bot_profile_id": a.bot_profile_id,
                "side": side_of(seat),
            }
            for seat, a in assignments.items()
        ],
    )
    return match_id


# --- writing events ----------------------------------------------------------------------------


def last_seq(conn: Connection, match_id: uuid.UUID) -> int:
    """Seq of the newest stored event, 0 when there is none. Seqs run 1, 2, 3, ..."""
    found = conn.scalar(select(func.max(Event.seq)).where(Event.match_id == match_id))
    return found or 0


def append_events(conn: Connection, match_id: uuid.UUID, events: Iterable[ev.Event]) -> int:
    """Store engine events in order after the existing ones; returns the new last seq.

    Also keeps the summary rows current: a `rounds` row per round (trump, result) and the
    match's status and winner. Those tables are not append-only.
    """
    seq = last_seq(conn, match_id)
    round_id = _current_round(conn, match_id)
    for event in events:
        seq += 1
        name = type(event).__name__
        match event:
            case ev.RoundStarted():
                round_id = uuid.uuid4()
                conn.execute(
                    insert(Round).values(
                        id=round_id, match_id=match_id, number=event.number, hakem_seat=event.hakem
                    )
                )
            case ev.TrumpDeclared():
                conn.execute(
                    update(Round).where(Round.id == round_id).values(trump=event.suit.value)
                )
            case ev.RoundEnded():
                conn.execute(
                    update(Round)
                    .where(Round.id == round_id)
                    .values(
                        tricks=list(event.tricks_won),
                        points=event.points,
                        kot_type=event.kot,
                        winner_side=event.winner,
                    )
                )
            case ev.MatchEnded():
                conn.execute(
                    update(Match)
                    .where(Match.id == match_id)
                    .values(status="ended", winner_side=event.winner, ended_at=func.now())
                )
            case _:
                pass
        owner = _owner(event) if name in _SEAT_ONLY else None
        conn.execute(
            insert(Event).values(
                match_id=match_id,
                round_id=round_id,
                seq=seq,
                name=name,
                visibility="seat" if owner else "all",
                seat=owner,
                payload=engine_event_to_wire(event).model_dump(mode="json"),
            )
        )
    return seq


def _owner(event: ev.Event) -> Seat:
    match event:
        case ev.CardsDealt() | ev.CardShown() | ev.CardDiscarded() | ev.DrawResolved():
            return event.seat
        case _:
            raise AssertionError(f"{type(event).__name__} has no owner")


def _current_round(conn: Connection, match_id: uuid.UUID) -> uuid.UUID | None:
    return conn.scalar(
        select(Round.id).where(Round.match_id == match_id).order_by(Round.number.desc()).limit(1)
    )


# --- rebuilding --------------------------------------------------------------------------------


def rebuild(conn: Connection, match_id: uuid.UUID) -> StoredMatch:
    """Replay a stored match through the engine. Raises `CorruptLog` if the log is wrong."""
    row = conn.execute(select(Match).where(Match.id == match_id)).one()
    config = MatchConfig(
        row.mode, row.target_points, row.seed, tuple(Card.parse(c) for c in row.removed_cards)
    )
    stored = conn.execute(
        select(Event.seq, Event.name, Event.payload)
        .where(Event.match_id == match_id, Event.visibility != "admin")
        .order_by(Event.seq)
    ).all()
    if [r.seq for r in stored] != list(range(1, len(stored) + 1)):
        raise CorruptLog("event seqs are not 1, 2, 3, ...")
    try:
        result = replay(config, actions_from_events([(r.name, r.payload) for r in stored]))
    except (EngineError, KeyError, ValueError) as exc:
        raise CorruptLog(f"stored actions do not replay: {exc}") from exc
    replayed = [
        (type(e).__name__, engine_event_to_wire(e).model_dump(mode="json")) for e in result.events
    ]
    # Exact match: a missing, extra, changed or truncated event is caught here.
    if replayed != [(r.name, r.payload) for r in stored]:
        raise CorruptLog("replaying the stored actions gives different events")
    return StoredMatch(match_id, config, row.forget_seed, result)


def actions_from_events(events: Sequence[tuple[str, dict[str, Any]]]) -> list[Action]:
    """The seat actions (and `NextRound`s) that produced these events, in order."""
    actions: list[Action] = []
    pending_discards: dict[str, list[Card]] = {}
    last_shown: dict[str, str] = {}
    for name, p in events:
        match name:
            case "RoundStarted" if p["number"] > 1:
                actions.append(NextRound())
            case "TrumpDeclared":
                actions.append(ChooseTrump(p["hakem"], Suit(p["suit"])))
            case "CardDiscarded":
                cards = pending_discards.setdefault(p["seat"], [])
                cards.append(Card.parse(p["card"]))
                if len(cards) == 2:  # R5.3 one Discard action emits two CardDiscarded
                    actions.append(Discard(p["seat"], tuple(cards)))
                    del pending_discards[p["seat"]]
            case "CardShown":
                last_shown[p["seat"]] = p["card"]
            case "DrawResolved":
                # R5.4 keep means the shown card went to the hand
                actions.append(DrawDecision(p["seat"], p["kept"] == last_shown[p["seat"]]))
            case "CardPlayed":
                actions.append(PlayCard(p["seat"], Card.parse(p["card"])))
            case _:
                pass
    return actions
