"""Round scoring, hakem rotation and match end (R3.3, R3.5, R8)."""

from __future__ import annotations

from hokm.engine.state import KotType
from hokm.engine.variants import Mode, Seat, Side, next_seat, side_of, sides

TRICKS_TO_WIN = 7  # R8.1


def round_winner(mode: Mode, tricks_won: tuple[int, ...]) -> Side | None:
    """R8.1 the side that has reached 7 tricks, if any."""
    for side, won in zip(sides(mode), tricks_won, strict=True):
        if won >= TRICKS_TO_WIN:
            return side
    return None


def score_round(
    mode: Mode, hakem: Seat, tricks_won: tuple[int, ...]
) -> tuple[Side, int, KotType | None]:
    """R8.2 points to the winning side: 1; 2 for kot; 3 for hakem koti."""
    winner = round_winner(mode, tricks_won)
    if winner is None:
        raise ValueError("the round is not over")
    loser_tricks = min(tricks_won)  # two sides, so the other side
    if loser_tricks > 0:
        return winner, 1, None
    if winner == side_of(hakem):
        return winner, 2, "kot"  # the hakem's side wins 7-0
    return winner, 3, "hakem_koti"  # the hakem's opponents win 7-0


def next_hakem(mode: Mode, hakem: Seat, winner: Side) -> Seat:
    """R3.3 the hakem stays if their side won; otherwise it passes to the next player."""
    return hakem if side_of(hakem) == winner else next_seat(mode, hakem)


def match_winner(mode: Mode, points: tuple[int, ...], target: int) -> Side | None:
    """R3.5 a side with at least `target` points wins the match."""
    for side, p in zip(sides(mode), points, strict=True):
        if p >= target:
            return side
    return None
