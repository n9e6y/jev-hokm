import csv
import json
from pathlib import Path

import pytest

from hokm.bots import Bot, make_bot
from hokm.engine.replay import replay
from hokm.engine.state import Phase
from hokm.engine.variants import MatchConfig, Mode, Seat, seats
from hokm.sim.cli import forget_seeds, main, run, write_records
from hokm.sim.runner import play_match, run_game, side_arms
from hokm.sim.stats import mean_ci, summarize, wilson
from hokm.views import Choice, InvalidChoice, SeatView

MODES: list[Mode] = ["2p", "4p"]


def _bots(mode: Mode, kind: str, seed: int) -> dict[Seat, Bot]:
    return {s: make_bot(kind, f"{seed}:{s}") for s in seats(mode)}


@pytest.mark.parametrize("mode", MODES)
def test_play_match_is_deterministic_and_replays(mode: Mode) -> None:
    config = MatchConfig.new(mode, 3, seed=11)
    final, actions, decisions = play_match(config, _bots(mode, "random", 1))
    again, actions2, _ = play_match(config, _bots(mode, "random", 1))
    assert final == again and actions == actions2
    assert final.phase is Phase.MATCH_END and decisions > 0
    assert replay(config, actions).final == final  # the record replays through the engine


def test_play_match_needs_one_bot_per_seat() -> None:
    with pytest.raises(ValueError):
        play_match(MatchConfig.new("4p", 1, seed=1), _bots("2p", "rule", 1))


class _CheatBot:
    kind = "cheat"

    def decide(self, view: SeatView) -> Choice:
        return "AS" if view["phase"] != "discard" else ["AS", "AS"]


def test_an_invalid_bot_answer_stops_the_match() -> None:
    bots: dict[Seat, Bot] = {s: _CheatBot() for s in seats("2p")}
    with pytest.raises(InvalidChoice):
        play_match(MatchConfig.new("2p", 1, seed=1), bots)


@pytest.mark.parametrize("mode", MODES)
def test_duplicate_mode_swaps_sides_on_the_same_deals(mode: Mode) -> None:
    records = run(
        mode=mode, games=3, seed=40, arm_kinds=("rule", "random"), target=1, duplicate=True
    )
    assert len(records) == 6
    for plain, swapped in zip(records[::2], records[1::2], strict=True):
        assert plain.seed == swapped.seed and not plain.swapped and swapped.swapped
        assert plain.side_arms == side_arms(mode, False)
        assert swapped.side_arms == {side: 1 - arm for side, arm in plain.side_arms.items()}
        # the same seed deals the same first round: the first action (hakem's trump) is by the
        # same seat in both games
        assert type(plain.actions[0]) is type(swapped.actions[0])
        assert plain.actions[0].seat == swapped.actions[0].seat  # type: ignore[union-attr]


def test_seats_flag_maps_bot_kinds_to_sides() -> None:
    record = run_game(
        0, 5, mode="4p", target=1, arm_kinds=("rule", "random"), swapped=False, make_bot=make_bot
    )
    assert record.side_arms == {"NS": 0, "EW": 1}
    assert record.winner_arm == record.side_arms[record.winner_side]
    assert sum(record.points_by_arm) >= 1 and record.rounds == 1


def test_wilson_known_values() -> None:
    low, high = wilson(50, 100)
    assert (round(low, 4), round(high, 4)) == (0.4038, 0.5962)
    low, high = wilson(0, 10)
    assert low == pytest.approx(0.0) and round(high, 4) == 0.2775
    low, high = wilson(10, 10)
    assert round(low, 4) == 0.7225 and high == pytest.approx(1.0)
    assert wilson(0, 0) == (0.0, 1.0)


def test_mean_ci() -> None:
    assert mean_ci([]) == (0.0, 0.0, 0.0)
    assert mean_ci([0.5]) == (0.5, 0.5, 0.5)
    mean, low, high = mean_ci([0.0, 1.0, 0.5, 0.5])
    assert mean == 0.5 and low < 0.5 < high


def test_summarize_counts_wins_pairs_and_points() -> None:
    records = run(
        mode="2p", games=5, seed=1, arm_kinds=("rule", "random"), target=1, duplicate=True
    )
    s = summarize(records)
    assert s.matches == 10 and sum(s.wins) == 10
    assert s.pairs == 5 and s.both_won + s.split + s.both_lost == 5
    assert s.wins[0] == 2 * s.both_won + s.split
    assert sum(s.avg_points) * s.matches == pytest.approx(
        sum(sum(r.points_by_arm) for r in records)
    )
    assert 0.0 <= s.pair_score[1] <= s.pair_score[0] <= s.pair_score[2] <= 1.0
    with pytest.raises(ValueError):
        summarize([])


@pytest.mark.parametrize("suffix", [".csv", ".json"])
def test_output_round_trips(tmp_path: Path, suffix: str) -> None:
    records = run(
        mode="4p", games=2, seed=3, arm_kinds=("random", "rule"), target=1, duplicate=True
    )
    path = tmp_path / f"out{suffix}"
    write_records(records, path)
    if suffix == ".csv":
        with path.open() as f:
            rows = list(csv.DictReader(f))
        assert [int(r["seed"]) for r in rows] == [r.seed for r in records]
        assert [int(r["winner_arm"]) for r in rows] == [r.winner_arm for r in records]
    else:
        rows = json.loads(path.read_text())
        assert rows == [r.row() for r in records]
    assert len(rows) == 4


def test_forget_seeds_never_depend_on_match_seeds() -> None:
    """ADR-014: forget seeds come from --forget-base only; changing --seed changes nothing."""
    a = run(
        mode="2p",
        games=3,
        seed=1,
        arm_kinds=("random", "random"),
        target=1,
        duplicate=False,
        forgetfulness=0.3,
        forget_base=99,
    )
    b = run(
        mode="2p",
        games=3,
        seed=500,
        arm_kinds=("random", "random"),
        target=1,
        duplicate=False,
        forgetfulness=0.3,
        forget_base=99,
    )
    assert [r.forget_seed for r in a] == [r.forget_seed for r in b] == forget_seeds(99, 3)
    assert all(r.forget_seed not in (r.seed, None) for r in a)
    off = run(mode="2p", games=2, seed=1, arm_kinds=("rule", "rule"), target=1, duplicate=False)
    assert all(r.forget_seed is None for r in off)


def test_cli_smoke(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "runs" / "smoke.csv"
    code = main(
        [
            "--games",
            "3",
            "--seed",
            "1",
            "--seats",
            "rule,random",
            "--duplicate",
            "--target",
            "1",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "6 matches" in printed and "95% CI" in printed and "duplicate pairs: 3" in printed
    assert out.exists()


def test_cli_rejects_bad_seats() -> None:
    with pytest.raises(SystemExit):
        main(["--seats", "rule"])
    with pytest.raises(SystemExit):
        main(["--seats", "rule,jev"])
