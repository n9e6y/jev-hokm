"""Seeded shuffling and seeded first hakem (R3.2, R3.4).

Seed strings are frozen for rules v1 (ADR-012): changing them changes every recorded deal.
String seeds are hashed with SHA-512 by `random.Random`, so they are stable across runs and
independent of PYTHONHASHSEED.
"""

from __future__ import annotations

import random

from hokm.engine.cards import Card
from hokm.engine.variants import MatchConfig, Seat, seats


def round_rng(seed: int, round_number: int) -> random.Random:
    """R3.4 round seed derived from the match seed and the round number."""
    return random.Random(f"hokm:{seed}:round:{round_number}")


def shuffled_deck(config: MatchConfig, round_number: int) -> tuple[Card, ...]:
    """R3.4 shuffle the full deck (minus removed cards) for one round; index 0 is the top."""
    cards = list(config.deck)
    round_rng(config.seed, round_number).shuffle(cards)
    return tuple(cards)


def first_hakem(config: MatchConfig) -> Seat:
    """R3.2 the first hakem is chosen at random (seeded)."""
    return random.Random(f"hokm:{config.seed}:hakem").choice(seats(config.mode))
