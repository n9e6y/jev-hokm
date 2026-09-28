import pytest

from hokm.engine.actions import ChooseTrump, NextRound, PlayCard
from hokm.engine.cards import Card, Suit
from hokm.engine.deck import shuffled_deck
from hokm.engine.errors import BadPhase, MatchOver
from hokm.engine.events import CardsDealt, MatchEnded, RoundEnded, RoundStarted
from hokm.engine.rules import apply, deal_order
from hokm.engine.scoring import match_winner, next_hakem, score_round
from hokm.engine.state import MatchState, Phase
from hokm.engine.variants import Mode, Seat, Side
from tests.engine.support import play_state, random_match


def _play(state: MatchState, *moves: tuple[Seat, str]) -> tuple[MatchState, list[object]]:
    events: list[object] = []
    for seat, card in moves:
        state, new = apply(state, PlayCard(seat, Card.parse(card)))
        events.extend(new)
    return state, events


def _round_ended(events: list[object]) -> RoundEnded:
    ended = [e for e in events if isinstance(e, RoundEnded)]
    assert len(ended) == 1
    return ended[0]


# --- R8 round end and scoring ------------------------------------------------------------


def test_R8_1_round_ends_the_moment_a_side_has_seven_tricks() -> None:
    hands: dict[Seat, str] = {"S": "AS 2D", "E": "3S 3D", "N": "4S 4D", "W": "5S 5D"}
    state = play_state("4p", hands, hakem="S", trump=Suit.CLUBS, tricks_won=(6, 3))
    state, events = _play(state, ("S", "AS"), ("E", "3S"), ("N", "4S"), ("W", "5S"))
    assert state.phase is Phase.ROUND_END
    assert state.round.tricks_won == (7, 3)
    assert state.round.to_act is None and state.round.trick is None
    # R8.1 remaining cards are not played
    assert all(len(h) == 1 for h in state.round.hands)
    assert _round_ended(events).winner == "NS"


def test_R8_2_one_point_when_the_losers_won_a_trick() -> None:
    state = play_state("2p", {"A": "AS", "B": "KS"}, hakem="A", tricks_won=(6, 3))
    state, events = _play(state, ("A", "AS"), ("B", "KS"))
    ended = _round_ended(events)
    assert (ended.winner, ended.points, ended.kot) == ("A", 1, None)
    assert state.points == (1, 0)


def test_R8_2_kot_two_points_when_the_hakems_side_wins_seven_nil() -> None:
    state = play_state("2p", {"A": "AS", "B": "KS"}, hakem="A", tricks_won=(6, 0))
    state, events = _play(state, ("A", "AS"), ("B", "KS"))
    ended = _round_ended(events)
    assert (ended.winner, ended.points, ended.kot) == ("A", 2, "kot")
    assert state.points == (2, 0)


def test_R8_2_hakem_koti_three_points_when_the_opponents_win_seven_nil() -> None:
    state = play_state("2p", {"A": "KS", "B": "AS"}, hakem="A", leader="B", tricks_won=(0, 6))
    state, events = _play(state, ("B", "AS"), ("A", "KS"))
    ended = _round_ended(events)
    assert (ended.winner, ended.points, ended.kot) == ("B", 3, "hakem_koti")
    assert state.points == (0, 3)


@pytest.mark.parametrize(
    ("mode", "hakem", "tricks", "expected"),
    [
        ("4p", "S", (7, 2), ("NS", 1, None)),
        ("4p", "N", (7, 0), ("NS", 2, "kot")),
        ("4p", "E", (7, 0), ("NS", 3, "hakem_koti")),
        ("4p", "W", (0, 7), ("EW", 2, "kot")),
        ("4p", "S", (1, 7), ("EW", 1, None)),
        ("2p", "B", (0, 7), ("B", 2, "kot")),
        ("2p", "B", (7, 0), ("A", 3, "hakem_koti")),
    ],
)
def test_R8_3_same_scoring_in_both_modes(
    mode: Mode, hakem: Seat, tricks: tuple[int, int], expected: tuple[str, int, str | None]
) -> None:
    assert score_round(mode, hakem, tricks) == expected


def test_R8_2_score_round_rejects_an_unfinished_round() -> None:
    with pytest.raises(ValueError):
        score_round("4p", "S", (6, 6))


# --- R3 hakem rotation and match end -----------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "hakem", "winner", "expected"),
    [
        ("4p", "S", "NS", "S"),  # hakem's side won: same player stays
        ("4p", "S", "EW", "E"),  # otherwise the next player in play order
        ("4p", "W", "NS", "S"),  # wraps around
        ("4p", "N", "NS", "N"),
        ("2p", "A", "B", "B"),  # 2-player: to the opponent
        ("2p", "B", "B", "B"),
    ],
)
def test_R3_3_hakem_rotation(mode: Mode, hakem: Seat, winner: Side, expected: Seat) -> None:
    assert next_hakem(mode, hakem, winner) == expected


def test_R3_3_next_round_is_dealt_by_the_new_hakem() -> None:
    hands: dict[Seat, str] = {"S": "2S", "E": "AS", "N": "3S", "W": "4S"}
    state = play_state("4p", hands, hakem="S", trump=Suit.CLUBS, tricks_won=(0, 6))
    state, events = _play(state, ("S", "2S"), ("E", "AS"), ("N", "3S"), ("W", "4S"))
    assert _round_ended(events).next_hakem == "E"
    state, events2 = apply(state, NextRound())
    assert state.round.number == 2 and state.round.hakem == "E"
    assert state.phase is Phase.TRUMP and state.round.to_act == "E"
    # R3.4 round 2 is a fresh shuffle with the round-2 seed
    deck = shuffled_deck(state.config, 2)
    assert events2 == (RoundStarted(2, "E"), CardsDealt("E", state.hand("E")))
    assert set(state.hand("E")) == set(deck[:5])
    assert deal_order("4p", "E")[0] == "E"
    assert state.points == (0, 3)  # hakem koti carried into the match score


def test_R3_5_match_ends_when_a_side_reaches_the_target() -> None:
    state = play_state(
        "2p", {"A": "AS", "B": "KS"}, hakem="A", tricks_won=(6, 0), points=(4, 2), target=5
    )
    state, events = _play(state, ("A", "AS"), ("B", "KS"))
    ended = _round_ended(events)
    assert ended.match_points == (6, 2) and ended.next_hakem is None
    assert events[-1] == MatchEnded("A", (6, 2))
    assert state.phase is Phase.MATCH_END and state.winner == "A"
    with pytest.raises(MatchOver):
        apply(state, NextRound())
    with pytest.raises(MatchOver):
        apply(state, ChooseTrump("A", Suit.SPADES))


def test_R3_5_match_continues_below_the_target() -> None:
    state = play_state(
        "2p", {"A": "AS", "B": "KS"}, hakem="A", tricks_won=(6, 2), points=(3, 4), target=5
    )
    state, events = _play(state, ("A", "AS"), ("B", "KS"))
    assert state.phase is Phase.ROUND_END and state.points == (4, 4)
    assert not any(isinstance(e, MatchEnded) for e in events)
    assert match_winner("2p", (4, 4), 5) is None
    assert match_winner("2p", (4, 5), 5) == "B"


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_R3_5_target_one_ends_after_the_first_round(mode: Mode) -> None:
    for seed in range(5):
        match = random_match(mode, seed, target=1)
        assert sum(isinstance(e, RoundEnded) for e in match.events) == 1
        assert match.states[-1].phase is Phase.MATCH_END


@pytest.mark.parametrize("mode", ["2p", "4p"])
@pytest.mark.parametrize("seed", range(5))
def test_R3_rounds_scores_and_hakems_are_consistent_over_whole_matches(
    mode: Mode, seed: int
) -> None:
    match = random_match(mode, seed, target=7)
    final = match.states[-1]
    started = [e for e in match.events if isinstance(e, RoundStarted)]
    ended = [e for e in match.events if isinstance(e, RoundEnded)]
    assert len(started) == len(ended) == len(final.results)
    for i, e in enumerate(ended):
        assert max(e.tricks_won) == 7 and min(e.tricks_won) < 7  # R8.1
        assert e.hakem == started[i].hakem
        if i + 1 < len(started):
            assert started[i + 1].hakem == e.next_hakem == next_hakem(mode, e.hakem, e.winner)
    assert sum(r.points for r in final.results) == sum(final.points)
    assert final.winner is not None and final.points_of(final.winner) >= 7
    assert match.events[-1] == MatchEnded(final.winner, final.points)


# --- R9 out of scope ---------------------------------------------------------------------


def test_R9_no_play_after_seven_tricks() -> None:
    state = play_state("2p", {"A": "AS 2H", "B": "KS 3H"}, hakem="A", tricks_won=(6, 1))
    state, _ = _play(state, ("A", "AS"), ("B", "KS"))
    assert state.phase is Phase.ROUND_END
    with pytest.raises(BadPhase):
        apply(state, PlayCard("A", Card.parse("2H")))


# --- full-flow scoring in 4p (through apply, not score_round) ----------------------------

FOUR_TRICK: dict[Seat, str] = {"S": "2S", "E": "3S", "N": "AS", "W": "4S"}  # N wins the trick


def test_R8_2_R3_3_four_player_kot_won_by_the_hakems_partner() -> None:
    state = play_state("4p", FOUR_TRICK, hakem="S", trump=Suit.CLUBS, tricks_won=(6, 0))
    state, events = _play(state, ("S", "2S"), ("E", "3S"), ("N", "AS"), ("W", "4S"))
    ended = _round_ended(events)
    assert (ended.winner, ended.points, ended.kot) == ("NS", 2, "kot")
    assert ended.next_hakem == "S"  # the partner won the last trick, but the hakem's side won
    state, _ = apply(state, NextRound())
    assert state.round.hakem == "S"


def test_R8_2_R3_3_four_player_hakem_koti_passes_the_hakem_on() -> None:
    state = play_state("4p", FOUR_TRICK, hakem="E", trump=Suit.CLUBS, leader="S", tricks_won=(6, 0))
    state, events = _play(state, ("S", "2S"), ("E", "3S"), ("N", "AS"), ("W", "4S"))
    ended = _round_ended(events)
    assert (ended.winner, ended.points, ended.kot) == ("NS", 3, "hakem_koti")
    assert ended.next_hakem == "N" and state.points == (3, 0)


def test_R8_1_two_player_round_ends_at_seven_with_cards_left() -> None:
    state = play_state("2p", {"A": "AS 2H 3H", "B": "KS 4H 5H"}, hakem="A", tricks_won=(6, 4))
    state, _ = _play(state, ("A", "AS"), ("B", "KS"))
    assert state.phase is Phase.ROUND_END and state.round.tricks_won == (7, 4)
    assert len(state.hand("A")) == len(state.hand("B")) == 2
