from dataclasses import replace

import pytest

from hokm.engine.actions import ChooseTrump, Discard, DrawDecision, NextRound, PlayCard
from hokm.engine.cards import Card, Suit
from hokm.engine.events import CardDiscarded, DrawResolved
from hokm.engine.rules import apply, legal_actions
from hokm.engine.state import MatchState, Phase
from hokm.engine.variants import Mode, next_seat, seats
from hokm.views import InvalidChoice, build_view, to_action, to_json
from hokm.views.forgetfulness import FORGOTTEN
from tests.engine.support import advance, in_phase, random_match, start
from tests.views.support import live_moments

MODES: list[Mode] = ["2p", "4p"]


def _sorted_ok(cards: list[str]) -> bool:
    parsed = [Card.parse(c) for c in cards]
    return parsed == sorted(parsed, key=Card.sort_key)


@pytest.mark.parametrize("mode", MODES)
def test_header_fields_per_mode(mode: Mode) -> None:
    state = start(mode, seed=4, target=5)
    for seat in seats(mode):
        view = build_view(state, seat, decision_seq=0)
        assert view["schema_version"] == 1 and view["profile"] == "raw"
        assert view["profile_version"] == 1 and view["mode"] == mode
        assert view["phase"] == "trump" and view["seat"] == seat
        assert view["hakem"] == state.round.hakem and view["trump_suit"] is None
        me, opp = ("me", "opp") if mode == "2p" else ("us", "them")
        assert view["scores"] == {
            "round_tricks": {me: 0, opp: 0},
            "tricks_to_win": 7,
            "match_points": {me: 0, opp: 0},
            "match_target": 5,
        }
        if mode == "4p":
            assert view.get("partner") == {"S": "N", "N": "S", "E": "W", "W": "E"}[seat]
        else:
            assert "partner" not in view


@pytest.mark.parametrize("mode", MODES)
def test_R4_2_only_the_hakem_sees_cards_in_the_trump_phase(mode: Mode) -> None:
    state = start(mode, seed=2)
    hakem = state.round.hakem
    for seat in seats(mode):
        view = build_view(state, seat, decision_seq=0)
        assert view["phase"] == "trump"
        if seat == hakem:
            assert len(view["hand"]) == 5
            assert view["options"] == ["spades", "hearts", "diamonds", "clubs"]
        else:
            assert view["hand"] == [] and view["options"] == []


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("seed", range(4))
def test_options_are_exactly_the_legal_actions(mode: Mode, seed: int) -> None:
    for state, seq in live_moments(random_match(mode, seed, target=1)):
        for seat in seats(mode):
            view = build_view(state, seat, decision_seq=seq)
            legal = legal_actions(state, seat)
            if not legal:
                assert view["options"] == []  # ADR-013 waiting seats have no options
                continue
            if view["phase"] == "discard":
                assert view["options"] == view["hand"]
                pairs = {frozenset(a.cards) for a in legal if isinstance(a, Discard)}
                opts = view["options"]
                assert (
                    pairs
                    == {
                        frozenset(to_action(view, [a, b]).cards)  # type: ignore[union-attr]
                        for i, a in enumerate(opts)
                        for b in opts[i + 1 :]
                    }
                )
            else:
                assert {to_action(view, o) for o in view["options"]} == set(legal)
            assert _sorted_ok(view["hand"])
            if view["phase"] == "play":
                assert _sorted_ok(view["options"])


@pytest.mark.parametrize("seed", range(4))
def test_draw_view_shows_the_top_card_only_to_the_seat_on_turn(seed: int) -> None:
    for state, seq in live_moments(random_match("2p", seed, target=1)):
        if state.phase is not Phase.DRAW:
            continue
        for seat in seats("2p"):
            view = build_view(state, seat, decision_seq=seq)
            assert view["phase"] == "draw"
            assert view["stock_left"] == len(state.round.stock)
            if seat == state.round.to_act:
                assert view["card_shown"] == str(state.round.stock[0])
                assert view["options"] == ["keep", "discard"]
            else:
                assert view["card_shown"] is None and view["options"] == []


def test_draw_turn_counts_each_seats_own_turns() -> None:
    state, _ = advance(start("2p", seed=6), in_phase(Phase.DRAW))
    hakem = state.round.hakem
    other = next_seat("2p", hakem)
    seen: dict[str, list[int]] = {hakem: [], other: []}
    while state.phase is Phase.DRAW:
        seat = state.round.to_act
        assert seat is not None
        view = build_view(state, seat, decision_seq=0)
        assert view["phase"] == "draw" and view["turns_total"] == 10
        seen[seat].append(view["turn"])
        state, _ = apply(state, DrawDecision(seat, keep=True))
    assert seen[hakem] == seen[other] == list(range(1, 11))


@pytest.mark.parametrize("seed", range(4))
def test_own_discards_are_exactly_this_seats_discards_in_order(seed: int) -> None:
    match = random_match("2p", seed, target=1)
    play_state = next(s for s in match.states if s.phase is Phase.PLAY)
    seq = match.states.index(play_state)
    for seat in seats("2p"):
        expected: list[str] = []
        for e in match.events:  # target 1: a single round
            if isinstance(e, CardDiscarded) and e.seat == seat:
                expected.append(str(e.card))
            elif isinstance(e, DrawResolved) and e.seat == seat:
                expected.append(str(e.dropped))
        view = build_view(play_state, seat, decision_seq=seq)
        assert view["phase"] == "play"
        assert view.get("own_discards") == expected and len(expected) == 12


def test_four_player_play_view_has_no_own_discards() -> None:
    state, _ = advance(start("4p", seed=1), in_phase(Phase.PLAY))
    view = build_view(state, "S", decision_seq=0)
    assert view["phase"] == "play" and "own_discards" not in view


@pytest.mark.parametrize("mode", MODES)
def test_play_view_trick_and_history_follow_the_engine(mode: Mode) -> None:
    match = random_match(mode, 9, target=1)
    for state, seq in live_moments(match):
        if state.phase is not Phase.PLAY:
            continue
        r = state.round
        assert r.trick is not None
        view = build_view(state, seats(mode)[0], decision_seq=seq)
        assert view["phase"] == "play"
        assert view["trick"] == {
            "number": r.trick.number,
            "leader": r.trick.leader,
            "cards": [{"seat": p.seat, "card": str(p.card)} for p in r.trick.plays],
        }
        assert [h["trick"] for h in view["history"]] == [t.number for t in r.tricks]
        assert [h["winner"] for h in view["history"]] == [t.winner for t in r.tricks]
        assert [[c["card"] for c in h["cards"]] for h in view["history"]] == [
            [str(p.card) for p in t.plays] for t in r.tricks
        ]


def _late_play_state(mode: Mode) -> tuple[MatchState, int]:
    match = random_match(mode, 5, target=1)
    states = [(s, i) for s, i in live_moments(match) if s.phase is Phase.PLAY and s.round.tricks]
    return states[-1]


@pytest.mark.parametrize("mode", MODES)
def test_forgetfulness_only_touches_history(mode: Mode) -> None:
    state, seq = _late_play_state(mode)
    seat = seats(mode)[1]
    base = build_view(state, seat, decision_seq=seq)
    assert to_json(build_view(state, seat, decision_seq=seq, forgetfulness=0.0)) == to_json(base)
    all_gone = build_view(state, seat, decision_seq=seq, forgetfulness=1.0, forget_seed=77)
    assert all_gone["phase"] == "play" and base["phase"] == "play"
    assert all(c["card"] == FORGOTTEN for h in all_gone["history"] for c in h["cards"])
    some = build_view(state, seat, decision_seq=seq, forgetfulness=0.5, forget_seed=77)
    assert some["phase"] == "play"
    # everything except history is identical
    strip = {k: v for k, v in base.items() if k != "history"}
    assert {k: v for k, v in some.items() if k != "history"} == strip
    assert {k: v for k, v in all_gone.items() if k != "history"} == strip
    # seats and winners are never forgotten
    for h_base, h_some in zip(base["history"], some["history"], strict=True):
        assert h_base["winner"] == h_some["winner"]
        assert [c["seat"] for c in h_base["cards"]] == [c["seat"] for c in h_some["cards"]]


def test_forgetfulness_is_reproducible_per_decision() -> None:
    state, seq = _late_play_state("4p")
    once = to_json(build_view(state, "E", decision_seq=seq, forgetfulness=0.5, forget_seed=77))
    again = to_json(build_view(state, "E", decision_seq=seq, forgetfulness=0.5, forget_seed=77))
    assert once == again
    others = {
        to_json(build_view(state, "E", decision_seq=n, forgetfulness=0.5, forget_seed=77))
        for n in range(20)
    }
    assert len(others) > 1  # the pattern depends on decision_seq
    with pytest.raises(ValueError):
        build_view(state, "E", decision_seq=seq, forgetfulness=1.5, forget_seed=77)


def test_invalid_choices_are_rejected() -> None:
    state = start("2p", seed=3)
    hakem = state.round.hakem
    waiting = next_seat("2p", hakem)
    view = build_view(state, hakem, decision_seq=0)
    assert to_action(view, "hearts") == ChooseTrump(hakem, Suit.HEARTS)
    for bad in ("notrumps", "Hearts", ["hearts"], "AS"):
        with pytest.raises(InvalidChoice):
            to_action(view, bad)
    with pytest.raises(InvalidChoice):
        to_action(build_view(state, waiting, decision_seq=0), "hearts")

    state, _ = apply(state, ChooseTrump(hakem, Suit.CLUBS))
    dview = build_view(state, hakem, decision_seq=1)
    h = dview["options"]
    for bad_discard in ([h[0]], [h[0], h[0]], [h[0], h[1], h[2]], h[0], [h[0], "2S"]):
        with pytest.raises(InvalidChoice):
            to_action(dview, bad_discard)
    assert isinstance(to_action(dview, [h[0], h[1]]), Discard)


def test_play_choice_maps_to_play_card() -> None:
    state, _ = advance(start("4p", seed=2), in_phase(Phase.PLAY))
    seat = state.round.to_act
    assert seat is not None
    view = build_view(state, seat, decision_seq=0)
    action = to_action(view, view["options"][0])
    assert action == PlayCard(seat, Card.parse(view["options"][0]))
    with pytest.raises(InvalidChoice):
        to_action(view, "keep")


def test_no_view_between_rounds() -> None:
    state, _ = advance(start("2p", seed=1, target=3), in_phase(Phase.ROUND_END))
    with pytest.raises(ValueError):
        build_view(state, "A", decision_seq=0)
    state, _ = apply(state, NextRound())
    assert build_view(state, "A", decision_seq=0)["phase"] == "trump"
    with pytest.raises(ValueError):
        build_view(replace(state, phase=Phase.MATCH_END), "A", decision_seq=0)
    with pytest.raises(ValueError):
        build_view(state, "S", decision_seq=0)  # not a 2p seat


def test_forgetfulness_needs_its_own_seed() -> None:
    state, seq = _late_play_state("2p")
    with pytest.raises(ValueError, match="forget_seed"):
        build_view(state, "A", decision_seq=seq, forgetfulness=0.5)
    with pytest.raises(ValueError, match="forget_seed"):  # fails at the first decision, not later
        build_view(start("2p"), "A", decision_seq=0, forgetfulness=0.5)
    a = to_json(build_view(state, "A", decision_seq=seq, forgetfulness=0.5, forget_seed=1))
    b = to_json(build_view(state, "A", decision_seq=seq, forgetfulness=0.5, forget_seed=2))
    assert a != b  # the pattern follows forget_seed, not the deal seed
