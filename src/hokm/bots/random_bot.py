"""Random bot (2.4): uniform over the view's options, from its own seeded RNG."""

from __future__ import annotations

import random

from hokm.views import Choice, SeatView


class RandomBot:
    kind = "random"

    def __init__(self, seed: int | str) -> None:
        self._rng = random.Random(seed)

    def decide(self, view: SeatView) -> Choice:
        options = view["options"]
        if not options:
            raise ValueError("no decision to make: the view has no options")
        if view["phase"] == "discard":
            return self._rng.sample(options, view["discard_count"])
        return self._rng.choice(options)
