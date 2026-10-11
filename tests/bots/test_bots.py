import ast
import copy
from dataclasses import replace
from pathlib import Path

import pytest

from hokm.bots import BOT_KINDS, RandomBot, RuleBot, make_bot
from hokm.engine.actions import ChooseTrump, Discard, PlayCard
from hokm.engine.cards import Card, Suit, parse_cards
from hokm.engine.rules import apply, legal_actions
from hokm.engine.state import Phase, replace_at
from hokm.engine.variants import Mode, Seat, next_seat, seat_index
from hokm.views import SeatView, build_view, to_action
from tests.engine.support import advance, in_phase, play_state, random_match, start
from tests.views.support import live_moments

BOTS_DIR = Path(__file__).parents[2] / "src" / "hokm" / "bots"
ALLOWED_HOKM_IMPORTS = ("hokm.views", "hokm.engine.cards", "hokm.engine.variants", "hokm.bots")


# --- 2.3 interface: bots never receive engine state ---------------------------------------


def test_bot_modules_import_only_views_and_card_types() -> None:
    for path in BOTS_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.startswith("hokm"):
                    assert name.startswith(ALLOWED_HOKM_IMPORTS), f"{path.name} imports {name}"


@pytest.mark.parametrize("kind", BOT_KINDS)
@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_every_bot_answer_is_a_valid_option(kind: str, mode: Mode) -> None:
    """100 random matches per mode: every bot answer passes the options gate and is legal."""
    for seed in range(100):
        bot = make_bot(kind, seed)
        for state, seq in live_moments(random_match(mode, seed, target=1)):
            seat = state.round.to_act
            assert seat is not None
            view = build_view(state, seat, decision_seq=seq)
            before = copy.deepcopy(view)
            action = to_action(view, bot.decide(view))
            assert view == before  # bots never mutate their view
            if isinstance(action, Discard):
                legal = {
                    frozenset(a.cards) for a in legal_actions(state, seat) if isinstance(a, Discard)
                }
                assert frozenset(action.cards) in legal
            else:
                assert action in legal_actions(state, seat)


def test_bots_refuse_a_view_without_options() -> None:
    state = start("4p", seed=1)
    waiting = next_seat("4p", state.round.hakem)
    view = build_view(state, waiting, decision_seq=0)
    for bot in (RandomBot(1), RuleBot()):
        with pytest.raises(ValueError):
            bot.decide(view)


# --- 2.4 random bot ---------------------------------------------------------------------


def _first_play_view() -> SeatView:
    state, _ = advance(start("4p", seed=2), in_phase(Phase.PLAY))
    seat = state.round.to_act
    assert seat is not None
    return build_view(state, seat, decision_seq=0)


def test_random_bot_is_seeded_and_deterministic() -> None:
    view = _first_play_view()
    a = [RandomBot("x").decide(view) for _ in range(5)]
    b, c = RandomBot("x"), RandomBot("x")
    assert [b.decide(view) for _ in range(20)] == [c.decide(view) for _ in range(20)]
    assert len(set(map(str, a))) == 1  # a fresh bot with the same seed starts the same way


def test_random_bot_covers_every_option() -> None:
    view = _first_play_view()
    bot = RandomBot(7)
    assert {str(bot.decide(view)) for _ in range(400)} == set(view["options"])
    state = start("2p", seed=3)
    state, _ = apply(state, ChooseTrump(state.round.hakem, Suit.HEARTS))
    dview = build_view(state, state.round.hakem, decision_seq=1)
    picks = {frozenset(bot.decide(dview)) for _ in range(400)}
    assert len(picks) == 10 and all(len(p) == 2 for p in picks)


# --- 2.5 rule bot heuristics -------------------------------------------------------------


def _trump_view(mode: Mode, hand: str) -> SeatView:
    state = start(mode, seed=5)
    hakem = state.round.hakem
    hands = replace_at(state.round.hands, seat_index(mode, hakem), parse_cards(hand))
    state = replace(state, round=replace(state.round, hands=hands))
    return build_view(state, hakem, decision_seq=0)


def test_rule_trump_picks_the_longest_suit() -> None:
    assert RuleBot().decide(_trump_view("4p", "AS 2D 5D KH 3D")) == "diamonds"


def test_rule_trump_ties_go_to_the_higher_total_rank() -> None:
    assert RuleBot().decide(_trump_view("2p", "AS KS QH JH 2C")) == "spades"
    assert RuleBot().decide(_trump_view("2p", "2S 3S QH JH 4C")) == "hearts"


def _discard_view(hand: str, trump: Suit) -> SeatView:
    state = start("2p", seed=6)
    hakem = state.round.hakem
    hands = replace_at(state.round.hands, seat_index("2p", hakem), parse_cards(hand))
    state = replace(state, round=replace(state.round, hands=hands))
    state, _ = apply(state, ChooseTrump(hakem, trump))
    return build_view(state, hakem, decision_seq=1)


def test_rule_discard_drops_the_lowest_non_trumps() -> None:
    assert RuleBot().decide(_discard_view("AH 2H 3S 9S 4C", Suit.HEARTS)) == ["3S", "4C"]


def test_rule_discard_breaks_rank_ties_towards_a_void() -> None:
    # 5S and 5C tie on rank; clubs is the shorter suit, so 5C goes and leaves a club void
    assert RuleBot().decide(_discard_view("4S 5S KS 5C AH", Suit.HEARTS)) == ["4S", "5C"]


def test_rule_discard_uses_trumps_only_when_it_must() -> None:
    # only one non-trump: it goes first, then the lowest trump
    assert RuleBot().decide(_discard_view("AH 3H 2H KS 9H", Suit.HEARTS)) == ["KS", "2H"]


def _draw_view(shown: str, trump: Suit) -> SeatView:
    """A real draw view, with the shown card and trump set for the test."""
    state, _ = advance(start("2p", seed=7), in_phase(Phase.DRAW))
    seat = state.round.to_act
    assert seat is not None
    shown_card = Card.parse(shown)
    stock = (shown_card, *(c for c in state.round.stock if c != shown_card))
    state = replace(state, round=replace(state.round, stock=stock, trump=trump))
    view = build_view(state, seat, decision_seq=0)
    assert view["phase"] == "draw" and view["card_shown"] == shown
    return view


@pytest.mark.parametrize(
    ("shown", "trump", "choice"),
    [
        ("2H", Suit.HEARTS, "keep"),
        ("JS", Suit.HEARTS, "keep"),
        ("AC", Suit.HEARTS, "keep"),
        ("10S", Suit.HEARTS, "discard"),
        ("3D", Suit.CLUBS, "discard"),
    ],
)
def test_rule_draw_keeps_trumps_and_high_cards(shown: str, trump: Suit, choice: str) -> None:
    assert RuleBot().decide(_draw_view(shown, trump)) == choice


def _play_view(
    hands: dict[Seat, str], *, trump: Suit, leader: Seat, plays: list[tuple[Seat, str]], mode: Mode
) -> SeatView:
    state = play_state(mode, hands, trump=trump, leader=leader)
    for seat, card in plays:
        state, _ = apply(state, PlayCard(seat, Card.parse(card)))
    seat = state.round.to_act
    assert seat is not None
    return build_view(state, seat, decision_seq=0)


def test_rule_lead_a_side_ace() -> None:
    view = _play_view(
        {"A": "AS 3S KH 2D", "B": "4S"}, trump=Suit.DIAMONDS, leader="A", plays=[], mode="2p"
    )
    assert RuleBot().decide(view) == "AS"


def test_rule_lead_lowest_of_the_longest_side_suit() -> None:
    view = _play_view(
        {"A": "KS 4S 9S QH 2D", "B": "4C"}, trump=Suit.DIAMONDS, leader="A", plays=[], mode="2p"
    )
    assert RuleBot().decide(view) == "4S"


def test_rule_lead_lowest_trump_when_only_trumps_are_left() -> None:
    view = _play_view(
        {"A": "KD 3D", "B": "4C"}, trump=Suit.DIAMONDS, leader="A", plays=[], mode="2p"
    )
    assert RuleBot().decide(view) == "3D"


def test_rule_follow_wins_as_cheaply_as_possible() -> None:
    view = _play_view(
        {"A": "10S", "B": "AS QS 2S 5H"},
        trump=Suit.HEARTS,
        leader="A",
        plays=[("A", "10S")],
        mode="2p",
    )
    assert RuleBot().decide(view) == "QS"


def test_rule_follow_plays_lowest_when_it_cannot_win() -> None:
    view = _play_view(
        {"A": "AS", "B": "QS 3S 5H"}, trump=Suit.HEARTS, leader="A", plays=[("A", "AS")], mode="2p"
    )
    assert RuleBot().decide(view) == "3S"


def test_rule_follow_does_not_overtake_a_winning_partner() -> None:
    hands: dict[Seat, str] = {"S": "AS", "E": "3S", "N": "KS 4S", "W": "5S"}
    view = _play_view(
        hands, trump=Suit.HEARTS, leader="S", plays=[("S", "AS"), ("E", "3S")], mode="4p"
    )
    assert view["seat"] == "N" and RuleBot().decide(view) == "4S"


def test_rule_void_trumps_in_with_the_lowest_winning_trump() -> None:
    view = _play_view(
        {"A": "AS", "B": "KH 3H 2C"}, trump=Suit.HEARTS, leader="A", plays=[("A", "AS")], mode="2p"
    )
    assert RuleBot().decide(view) == "3H"


def test_rule_void_must_overtrump_or_throw_low() -> None:
    hands: dict[Seat, str] = {"S": "AS", "E": "QH", "N": "4S", "W": "2H 9C 3D"}
    plays: list[tuple[Seat, str]] = [("S", "AS"), ("E", "QH"), ("N", "4S")]
    view = _play_view(hands, trump=Suit.HEARTS, leader="S", plays=plays, mode="4p")
    # E (W's partner) is winning with QH: W throws its lowest non-trump
    assert view["seat"] == "W" and RuleBot().decide(view) == "3D"
    hands = {"S": "AS", "E": "4S", "N": "QH", "W": "2H 9C 3D"}
    plays = [("S", "AS"), ("E", "4S"), ("N", "QH")]
    view = _play_view(hands, trump=Suit.HEARTS, leader="S", plays=plays, mode="4p")
    # the opponents win with QH and 2H cannot beat it: throw the lowest non-trump, keep the trump
    assert RuleBot().decide(view) == "3D"


def test_rule_bot_is_deterministic() -> None:
    match = random_match("4p", 3, target=1)
    for state, seq in live_moments(match):
        seat = state.round.to_act
        assert seat is not None
        view = build_view(state, seat, decision_seq=seq)
        assert RuleBot().decide(view) == RuleBot().decide(view)


def test_make_bot_rejects_unknown_kinds() -> None:
    with pytest.raises(ValueError):
        make_bot("jev", 1)
