"""Forgetfulness (SEAT_VIEW §5): history cards are forgotten with probability p.

Only `history` is ever degraded. The RNG comes from a per-match `forget_seed`, drawn
independently of the deal seed (ADR-014), plus seat and decision_seq, so a replay produces the
same view and the forgotten pattern carries no information about the deal.
"""

from __future__ import annotations

import random

from hokm.engine.variants import Seat
from hokm.views.schema import HistoryTrick

FORGOTTEN = "??"


def forget(
    history: list[HistoryTrick],
    p: float,
    *,
    forget_seed: int | None,
    seat: Seat,
    decision_seq: int,
) -> list[HistoryTrick]:
    if not 0.0 <= p <= 1.0:
        raise ValueError("forgetfulness must be between 0 and 1")
    if p == 0.0:
        return history
    if forget_seed is None:
        raise ValueError("forgetfulness > 0 needs a forget_seed (never the deal seed, ADR-014)")
    rng = random.Random(f"forget:{forget_seed}:{seat}:{decision_seq}")
    return [
        {
            "trick": t["trick"],
            "cards": [
                {"seat": c["seat"], "card": FORGOTTEN if rng.random() < p else c["card"]}
                for c in t["cards"]
            ],
            "winner": t["winner"],
        }
        for t in history
    ]
