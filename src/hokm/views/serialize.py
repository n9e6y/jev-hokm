"""The canonical byte form of a view: what the leak test compares and what is sent to Jev."""

from __future__ import annotations

import json

from hokm.views.schema import SeatView


def to_json(view: SeatView) -> str:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8 characters kept."""
    return json.dumps(view, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
