"""Results summary (2.7): win rates with Wilson 95% intervals, duplicate-deal pairs, points.

Standard library only.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from hokm.sim.runner import MatchRecord

Z95 = 1.959963984540054


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def mean_ci(values: Sequence[float], z: float = Z95) -> tuple[float, float, float]:
    """Mean with a normal-approximation interval."""
    n = len(values)
    if n == 0:
        return (0.0, 0.0, 0.0)
    mean = sum(values) / n
    if n == 1:
        return (mean, mean, mean)
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    half = z * math.sqrt(var / n)
    return (mean, mean - half, mean + half)


def _clamped(ci: tuple[float, float, float]) -> tuple[float, float, float]:
    """A pair score lies in [0, 1]; keep the normal-approximation interval inside it."""
    mean, low, high = ci
    return (mean, max(0.0, low), min(1.0, high))


@dataclass(frozen=True, slots=True)
class Summary:
    arm_kinds: tuple[str, str]
    matches: int
    wins: tuple[int, int]
    win_rate_arm0: float
    ci_arm0: tuple[float, float]
    avg_points: tuple[float, float]
    kots: tuple[int, int]
    hakem_kotis: tuple[int, int]
    rounds: int
    # duplicate mode only: per seed, how arm 0 did over its two games
    pairs: int = 0
    both_won: int = 0
    split: int = 0
    both_lost: int = 0
    pair_score: tuple[float, float, float] = (0.0, 0.0, 0.0)  # mean, low, high (arm 0)


def summarize(records: Sequence[MatchRecord]) -> Summary:
    if not records:
        raise ValueError("no matches to summarize")
    kinds = records[0].arm_kinds
    n = len(records)
    wins0 = sum(r.winner_arm == 0 for r in records)
    by_seed: dict[int, list[MatchRecord]] = defaultdict(list)
    for r in records:
        by_seed[r.seed].append(r)
    pairs = [games for games in by_seed.values() if len(games) == 2]
    pair_wins = [sum(g.winner_arm == 0 for g in games) for games in pairs]
    return Summary(
        arm_kinds=kinds,
        matches=n,
        wins=(wins0, n - wins0),
        win_rate_arm0=wins0 / n,
        ci_arm0=wilson(wins0, n),
        avg_points=(
            sum(r.points_by_arm[0] for r in records) / n,
            sum(r.points_by_arm[1] for r in records) / n,
        ),
        kots=(sum(r.kots_by_arm[0] for r in records), sum(r.kots_by_arm[1] for r in records)),
        hakem_kotis=(
            sum(r.hakem_kotis_by_arm[0] for r in records),
            sum(r.hakem_kotis_by_arm[1] for r in records),
        ),
        rounds=sum(r.rounds for r in records),
        pairs=len(pairs),
        both_won=pair_wins.count(2),
        split=pair_wins.count(1),
        both_lost=pair_wins.count(0),
        pair_score=_clamped(mean_ci([w / 2 for w in pair_wins])) if pairs else (0.0, 0.0, 0.0),
    )


def format_summary(s: Summary) -> str:
    a, b = s.arm_kinds
    if a == b:  # same kind on both arms: label them apart
        a, b = f"{a}#0", f"{b}#1"
    low, high = s.ci_arm0
    lines = [
        f"{s.matches} matches · {s.rounds} rounds · arm 0 = {a}, arm 1 = {b}",
        f"  {a:<8} wins {s.wins[0]:>5} ({s.win_rate_arm0:6.1%})  95% CI [{low:.1%}, {high:.1%}]",
        f"  {b:<8} wins {s.wins[1]:>5} ({1 - s.win_rate_arm0:6.1%})",
        f"  avg points/match: {a} {s.avg_points[0]:.2f} · {b} {s.avg_points[1]:.2f}",
        f"  kot: {a} {s.kots[0]} · {b} {s.kots[1]}   "
        f"hakem koti: {a} {s.hakem_kotis[0]} · {b} {s.hakem_kotis[1]}",
    ]
    if s.pairs:
        mean, plow, phigh = s.pair_score
        lines.append(
            f"  duplicate pairs: {s.pairs} · {a} won both {s.both_won} · split {s.split}"
            f" · lost both {s.both_lost} · pair score {mean:.3f} [{plow:.3f}, {phigh:.3f}]"
        )
    return "\n".join(lines)
