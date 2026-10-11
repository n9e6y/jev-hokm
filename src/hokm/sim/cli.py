"""Headless simulator CLI (2.6).

    uv run python -m hokm.sim --games 1000 --seed 1 --seats rule,random --duplicate
    uv run python -m hokm.sim --mode 4p --games 500 --seats rule,random --out runs/r.csv

`--seats` gives one bot kind per side (2p: A,B; 4p: NS,EW); both seats of a 4p side use that
kind. Game i uses match seed `seed + i`. `--duplicate` plays every seed twice with the sides
swapped, so each bot plays every deal from both sides. Forgetfulness seeds come from their own
`--forget-base`, never from the match seed (ADR-014).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import secrets
import sys
from collections.abc import Sequence
from pathlib import Path

from hokm.bots import BOT_KINDS, make_bot
from hokm.engine.variants import MATCH_TARGETS, Mode
from hokm.sim.runner import MatchRecord, run_game
from hokm.sim.stats import format_summary, summarize


def forget_seeds(forget_base: int, count: int) -> list[int]:
    """One forget seed per game, drawn from `forget_base` only (independent of match seeds)."""
    rng = random.Random(f"sim-forget:{forget_base}")
    return [rng.randrange(2**63) for _ in range(count)]


def run(
    *,
    mode: Mode,
    games: int,
    seed: int,
    arm_kinds: tuple[str, str],
    target: int,
    duplicate: bool,
    forgetfulness: float = 0.0,
    forget_base: int = 0,
) -> list[MatchRecord]:
    fseeds = forget_seeds(forget_base, games) if forgetfulness > 0 else [None] * games
    records: list[MatchRecord] = []
    for i in range(games):
        for swapped in (False, True) if duplicate else (False,):
            records.append(
                run_game(
                    i,
                    seed + i,
                    mode=mode,
                    target=target,
                    arm_kinds=arm_kinds,
                    swapped=swapped,
                    make_bot=make_bot,
                    forgetfulness=forgetfulness,
                    forget_seed=fseeds[i],
                )
            )
    return records


def write_records(records: Sequence[MatchRecord], path: Path) -> None:
    rows = [r.row() for r in records]
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".csv":
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    elif path.suffix == ".json":
        path.write_text(json.dumps(rows, indent=1) + "\n")
    else:
        raise ValueError("--out must end in .csv or .json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hokm.sim", description="Bot-vs-bot Hokm simulator.")
    parser.add_argument("--mode", choices=("2p", "4p"), default="2p")
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1, help="first match seed")
    parser.add_argument(
        "--seats", default="rule,random", help="bot kind per side, e.g. rule,random"
    )
    parser.add_argument("--target", type=int, choices=MATCH_TARGETS, default=7)
    parser.add_argument(
        "--duplicate", action="store_true", help="replay each seed with sides swapped"
    )
    parser.add_argument("--forgetfulness", type=float, default=0.0)
    parser.add_argument("--forget-base", type=int, default=None, help="seed for forget seeds")
    parser.add_argument("--out", type=Path, default=None, help="write rows to .csv or .json")
    args = parser.parse_args(argv)

    kinds = tuple(args.seats.split(","))
    if len(kinds) != 2 or any(k not in BOT_KINDS for k in kinds):
        parser.error(f"--seats needs two of {', '.join(BOT_KINDS)}, e.g. rule,random")
    if args.games < 1:
        parser.error("--games must be at least 1")
    forget_base = args.forget_base if args.forget_base is not None else secrets.randbelow(2**31)

    records = run(
        mode=args.mode,
        games=args.games,
        seed=args.seed,
        arm_kinds=(kinds[0], kinds[1]),
        target=args.target,
        duplicate=args.duplicate,
        forgetfulness=args.forgetfulness,
        forget_base=forget_base,
    )
    print(
        f"mode {args.mode} · target {args.target} · seeds {args.seed}..{args.seed + args.games - 1}"
        + (
            f" · forgetfulness {args.forgetfulness} (forget base {forget_base})"
            if args.forgetfulness
            else ""
        )
    )
    print(format_summary(summarize(records)))
    if args.out is not None:
        write_records(records, args.out)
        print(f"wrote {len(records)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
