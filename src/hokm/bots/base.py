"""Bot interface (2.3): a bot sees one seat view and answers with one choice.

Bots never receive engine state. Their only input is the JSON seat view (docs/SEAT_VIEW.md); the
answer must be one of `view["options"]` (a discard: `discard_count` of them), and is checked by
`hokm.views.to_action` before it reaches the engine. A bot module may import only `hokm.views`,
`hokm.engine.cards` (to read card strings) and `hokm.engine.variants` (seat types); a test
enforces this.
"""

from __future__ import annotations

from typing import Protocol

from hokm.views import Choice, SeatView


class Bot(Protocol):
    kind: str  # "random", "rule", later "jev"

    def decide(self, view: SeatView) -> Choice: ...
