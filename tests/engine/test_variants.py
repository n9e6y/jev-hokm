import pytest

from hokm.engine.variants import (
    MATCH_TARGETS,
    ConfigError,
    MatchConfig,
    next_seat,
    seats,
    side_of,
    sides,
)


def test_R2_1_four_player_order_is_counter_clockwise_with_partners_across() -> None:
    assert seats("4p") == ("S", "E", "N", "W")
    assert sides("4p") == ("NS", "EW")
    assert side_of("S") == side_of("N") == "NS"
    assert side_of("E") == side_of("W") == "EW"
    # partners are two seats apart in play order, so play alternates between sides
    order = seats("4p")
    for i, seat in enumerate(order):
        assert side_of(seat) != side_of(order[(i + 1) % 4])


def test_R2_2_two_player_seats_alternate() -> None:
    assert seats("2p") == ("A", "B")
    assert next_seat("2p", "A") == "B"
    assert next_seat("2p", "B") == "A"
    assert side_of("A") == "A" and side_of("B") == "B"


def test_R2_3_next_player_follows_play_order_and_wraps() -> None:
    assert [next_seat("4p", s) for s in ("S", "E", "N", "W")] == ["E", "N", "W", "S"]


@pytest.mark.parametrize("target", MATCH_TARGETS)
def test_R3_1_valid_match_targets(target: int) -> None:
    assert MATCH_TARGETS == (1, 3, 5, 7)
    assert MatchConfig.new("4p", target, seed=0).target_points == target


@pytest.mark.parametrize("target", [0, 2, 4, 6, 8, -1])
def test_R3_1_other_targets_are_rejected(target: int) -> None:
    with pytest.raises(ConfigError):
        MatchConfig.new("4p", target, seed=0)
