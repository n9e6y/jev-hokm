"""Play one match between bots through the same path every bot will use (2.6).

state → build_view (seat view only) → bot.decide → to_action (options gate) → engine.apply.
Between rounds the runner sends `NextRound`, as the server will.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from hokm.bots import Bot
from hokm.engine.actions import Action, NextRound
from hokm.engine.rules import apply, new_match
from hokm.engine.state import MatchState, Phase
from hokm.engine.variants import MatchConfig, Mode, Seat, Side, seats, side_of, sides
from hokm.views import build_view, to_action

type BotFactory = Callable[[str, int | str], Bot]


@dataclass(frozen=True, slots=True)
class MatchRecord:
    """One finished match. Arms are the positions in `--seats` (arm 0, arm 1)."""

    game: int
    seed: int
    mode: Mode
    target: int
    swapped: bool  # duplicate mode: arms swapped between sides
    arm_kinds: tuple[str, str]  # bot kind per arm
    side_arms: dict[Side, int]  # side -> arm
    winner_side: Side
    winner_arm: int
    points_by_arm: tuple[int, int]
    rounds: int
    kots_by_arm: tuple[int, int]
    hakem_kotis_by_arm: tuple[int, int]
    decisions: int
    forget_seed: int | None
    actions: tuple[Action, ...]

    def row(self) -> dict[str, object]:
        """A flat row for JSON/CSV output (actions left out; the match replays from its seed)."""
        return {
            "game": self.game,
            "seed": self.seed,
            "mode": self.mode,
            "target": self.target,
            "swapped": self.swapped,
            "arm0": self.arm_kinds[0],
            "arm1": self.arm_kinds[1],
            "sides": ";".join(f"{side}={self.side_arms[side]}" for side in sorted(self.side_arms)),
            "winner_side": self.winner_side,
            "winner_arm": self.winner_arm,
            "points_arm0": self.points_by_arm[0],
            "points_arm1": self.points_by_arm[1],
            "rounds": self.rounds,
            "kots_arm0": self.kots_by_arm[0],
            "kots_arm1": self.kots_by_arm[1],
            "hakem_kotis_arm0": self.hakem_kotis_by_arm[0],
            "hakem_kotis_arm1": self.hakem_kotis_by_arm[1],
            "decisions": self.decisions,
            "forget_seed": self.forget_seed,
        }


def play_match(
    config: MatchConfig,
    bots: Mapping[Seat, Bot],
    *,
    forgetfulness: float = 0.0,
    forget_seed: int | None = None,
) -> tuple[MatchState, tuple[Action, ...], int]:
    """Play to the end. Returns the final state, every action applied, and the bot decisions.

    An `InvalidChoice` from `to_action` is a bot bug and propagates.
    """
    if set(bots) != set(seats(config.mode)):
        raise ValueError(f"need one bot per seat {seats(config.mode)}")
    state, _ = new_match(config)
    actions: list[Action] = []
    decisions = 0
    while state.phase is not Phase.MATCH_END:
        if state.phase is Phase.ROUND_END:
            action: Action = NextRound()
        else:
            seat = state.round.to_act
            assert seat is not None
            view = build_view(
                state,
                seat,
                decision_seq=len(actions),  # ADR-013 actions applied before this decision
                forgetfulness=forgetfulness,
                forget_seed=forget_seed,
            )
            action = to_action(view, bots[seat].decide(view))
            decisions += 1
        state, _ = apply(state, action)
        actions.append(action)
    return state, tuple(actions), decisions


def side_arms(mode: Mode, swapped: bool) -> dict[Side, int]:
    """Arm 0 plays the first side (A / NS) unless swapped."""
    first, second = sides(mode)
    return {first: 1, second: 0} if swapped else {first: 0, second: 1}


def run_game(
    game: int,
    seed: int,
    *,
    mode: Mode,
    target: int,
    arm_kinds: tuple[str, str],
    swapped: bool,
    make_bot: BotFactory,
    forgetfulness: float = 0.0,
    forget_seed: int | None = None,
) -> MatchRecord:
    config = MatchConfig.new(mode, target, seed)
    arms = side_arms(mode, swapped)
    bots: dict[Seat, Bot] = {}
    for seat in seats(config.mode):
        kind = arm_kinds[arms[side_of(seat)]]
        bots[seat] = make_bot(kind, f"bot:{kind}:{seat}:{seed}:{int(swapped)}")
    final, actions, decisions = play_match(
        config, bots, forgetfulness=forgetfulness, forget_seed=forget_seed
    )
    assert final.winner is not None
    points = [0, 0]
    kots = [0, 0]
    hakem_kotis = [0, 0]
    for result in final.results:
        arm = arms[result.winner]
        points[arm] += result.points
        kots[arm] += result.kot == "kot"
        hakem_kotis[arm] += result.kot == "hakem_koti"
    return MatchRecord(
        game=game,
        seed=seed,
        mode=mode,
        target=target,
        swapped=swapped,
        arm_kinds=arm_kinds,
        side_arms=dict(arms),
        winner_side=final.winner,
        winner_arm=arms[final.winner],
        points_by_arm=(points[0], points[1]),
        rounds=len(final.results),
        kots_by_arm=(kots[0], kots[1]),
        hakem_kotis_by_arm=(hakem_kotis[0], hakem_kotis[1]),
        decisions=decisions,
        forget_seed=forget_seed,
        actions=actions,
    )
