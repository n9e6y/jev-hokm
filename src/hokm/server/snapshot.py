"""Snapshots: the full picture a socket gets on (re)connect (docs/PROTOCOL.md "Snapshot").

A player snapshot is the seat's `raw` view plus public table state only: whose turn it is,
the last completed trick (played face up), match points and the last round's result.
"""

from __future__ import annotations

import uuid
from typing import Any

from hokm.engine.state import MatchState, Phase
from hokm.engine.variants import Seat, seats
from hokm.protocol import ObserverSnapshotMsg, SnapshotMsg
from hokm.protocol.envelope import LastTrick, PlayedCard, RoundResult
from hokm.views import SeatView, build_view

_NO_VIEW = (Phase.ROUND_END, Phase.MATCH_END)


def player_snapshot(
    state: MatchState, seat: Seat, *, match_id: uuid.UUID, seq: int, decision_seq: int
) -> SnapshotMsg:
    view = None if state.phase in _NO_VIEW else build_view(state, seat, decision_seq=decision_seq)
    return SnapshotMsg(match_id=str(match_id), seq=seq, seat=seat, view=view, **_table(state))


def observer_snapshot(
    state: MatchState, *, match_id: uuid.UUID, seq: int, decision_seq: int
) -> ObserverSnapshotMsg:
    views: dict[Seat, SeatView] = {}
    if state.phase not in _NO_VIEW:
        views = {s: build_view(state, s, decision_seq=decision_seq) for s in seats(state.mode)}
    return ObserverSnapshotMsg(match_id=str(match_id), seq=seq, views=views, **_table(state))


def _table(state: MatchState) -> dict[str, Any]:
    r = state.round
    last = r.tricks[-1] if r.tricks else None
    result = state.results[-1] if state.results and state.phase in _NO_VIEW else None
    return {
        "phase": state.phase.value,
        "whose_turn": r.to_act,
        "last_trick": None
        if last is None or last.winner is None
        else LastTrick(
            number=last.number,
            leader=last.leader,
            cards=[PlayedCard(seat=p.seat, card=str(p.card)) for p in last.plays],
            winner=last.winner,
        ),
        "match_points": list(state.points),
        "last_round": None
        if result is None
        else RoundResult(
            number=result.number,
            hakem=result.hakem,
            trump=result.trump.value,
            tricks_won=list(result.tricks_won),
            winner=result.winner,
            points=result.points,
            kot=result.kot,
        ),
        "winner": state.winner,
    }
