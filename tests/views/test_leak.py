"""Leak tests (SEAT_VIEW §6, task 2.2).

For seat X at any live moment: every card X cannot see is shuffled among the hidden slots, sizes
kept (other hands, stock, opponent discards; in the trump phase also X's own hand unless X is the
hakem, R4.2). X's view must be byte-identical. Waiting seats are included (ADR-013).
"""

import random
from collections import Counter
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hokm.engine.cards import Card
from hokm.engine.state import MatchState, Phase, sorted_cards
from hokm.engine.variants import Mode, Seat, next_seat, seat_index, seats
from hokm.views import build_view, to_json
from tests.engine.support import advance, in_phase, played_cards, random_match, start
from tests.views.support import live_moments


def hidden_from(state: MatchState, seat: Seat) -> tuple[list[tuple[str, int]], list[Card]]:
    """The hidden slots (kind, index) and the cards in them, for `seat`."""
    r, mode = state.round, state.mode
    slots: list[tuple[str, int]] = []
    for other in seats(mode):
        i = seat_index(mode, other)
        own_hidden = state.phase is Phase.TRUMP and other != r.hakem  # R4.2
        if other != seat or own_hidden:
            slots.append(("hand", i))
        if other != seat and mode == "2p":
            slots.append(("discards", i))  # R5.6 never learns the opponent's discards
    slots.append(("stock", 0))
    pool: list[Card] = []
    for kind, i in slots:
        pool.extend(_slot(state, seat, kind, i))
    return slots, pool


def _slot(state: MatchState, seat: Seat, kind: str, i: int) -> tuple[Card, ...]:
    r = state.round
    if kind == "hand":
        return r.hands[i]
    if kind == "discards":
        return r.discards[i]
    if state.phase is Phase.DRAW and r.to_act == seat:
        return r.stock[1:]  # the top card is shown to the seat on turn
    return r.stock


def permute_hidden(state: MatchState, seat: Seat, rng: random.Random) -> MatchState:
    return permute_hidden_tracked(state, seat, rng)[0]


def permute_hidden_tracked(
    state: MatchState, seat: Seat, rng: random.Random
) -> tuple[MatchState, set[str]]:
    """Permute the hidden cards; also return the slot kinds whose contents changed."""
    slots, pool = hidden_from(state, seat)
    rng.shuffle(pool)
    r = state.round
    hands, discards, stock = list(r.hands), list(r.discards), r.stock
    pos = 0
    for kind, i in slots:
        size = len(_slot(state, seat, kind, i))
        chunk = tuple(pool[pos : pos + size])
        pos += size
        if kind == "hand":
            hands[i] = sorted_cards(chunk)
        elif kind == "discards":
            discards[i] = chunk
        elif state.phase is Phase.DRAW and r.to_act == seat:
            stock = (r.stock[0], *chunk)
        else:
            stock = chunk
    new_round = replace(r, hands=tuple(hands), discards=tuple(discards), stock=stock)
    permuted = replace(state, round=new_round)
    assert _all_cards(permuted) == _all_cards(state)  # still a full, conserved deck
    changed = {
        kind for kind, i in slots if _slot(state, seat, kind, i) != _slot(permuted, seat, kind, i)
    }
    return permuted, changed


def _all_cards(state: MatchState) -> Counter[Card]:
    r = state.round
    every = [c for h in r.hands for c in h] + [c for d in r.discards for c in d]
    return Counter(every + list(r.stock) + played_cards(state))


modes = st.sampled_from(["2p", "4p"])


# every (phase, slot kind) that must be shuffled at least once in a whole match (non-vacuity)
MUST_SHUFFLE: dict[str, set[tuple[str, str]]] = {
    "2p": {
        ("trump", "hand"),
        ("trump", "stock"),
        ("discard", "hand"),
        ("discard", "discards"),
        ("draw", "hand"),
        ("draw", "stock"),
        ("draw", "discards"),
        ("play", "hand"),
        ("play", "discards"),
    },
    "4p": {("trump", "hand"), ("trump", "stock"), ("play", "hand")},
}


@settings(max_examples=60, deadline=None)
@given(
    mode=modes,
    seed=st.integers(0, 2**32),
    perm_seed=st.integers(0, 2**32),
    p=st.sampled_from((0.0, 0.3)),
    target=st.sampled_from((1, 3)),
)
def test_views_do_not_depend_on_any_hidden_card(
    mode: Mode, seed: int, perm_seed: int, p: float, target: int
) -> None:
    rng = random.Random(perm_seed)
    shuffled: set[tuple[str, str]] = set()
    for state, seq in live_moments(random_match(mode, seed, target=target)):
        for seat in seats(mode):
            view = build_view(state, seat, decision_seq=seq, forgetfulness=p, forget_seed=perm_seed)
            permuted, changed = permute_hidden_tracked(state, seat, rng)
            assert to_json(
                build_view(permuted, seat, decision_seq=seq, forgetfulness=p, forget_seed=perm_seed)
            ) == to_json(view), f"{view['phase']} view of {seat} changed when hidden cards moved"
            shuffled |= {(view["phase"], kind) for kind in changed}
    assert MUST_SHUFFLE[mode] <= shuffled, MUST_SHUFFLE[mode] - shuffled


@settings(max_examples=40, deadline=None)
@given(
    mode=modes,
    seed=st.integers(0, 2**32),
    other_seed=st.integers(0, 2**63),
    p=st.sampled_from((0.0, 0.3, 1.0)),
)
def test_views_do_not_depend_on_the_seed(mode: Mode, seed: int, other_seed: int, p: float) -> None:
    """The deal seed must not reach a view by any channel, forgetfulness included (ADR-014)."""
    for state, seq in live_moments(random_match(mode, seed, target=3)):
        reseeded = replace(state, config=replace(state.config, seed=other_seed))
        for seat in seats(mode):
            before = build_view(state, seat, decision_seq=seq, forgetfulness=p, forget_seed=1234)
            after = build_view(reseeded, seat, decision_seq=seq, forgetfulness=p, forget_seed=1234)
            assert to_json(before) == to_json(after)


# --- controls: the test above must be able to fail ----------------------------------------


def test_control_a_visible_card_change_does_change_the_view() -> None:
    state, _ = advance(start("4p", seed=3), in_phase(Phase.PLAY))
    r = state.round
    s_i, e_i = seat_index("4p", "S"), seat_index("4p", "E")
    # swap one card between S's hand (visible to S) and E's hand (hidden from S)
    s_hand, e_hand = list(r.hands[s_i]), list(r.hands[e_i])
    s_hand[0], e_hand[0] = e_hand[0], s_hand[0]
    hands = list(r.hands)
    hands[s_i], hands[e_i] = sorted_cards(tuple(s_hand)), sorted_cards(tuple(e_hand))
    moved = replace(state, round=replace(r, hands=tuple(hands)))
    before, after = build_view(state, "S", decision_seq=0), build_view(moved, "S", decision_seq=0)
    assert to_json(before) != to_json(after)
    # N sees neither hand, so N's view is unchanged
    assert to_json(build_view(state, "N", decision_seq=0)) == to_json(
        build_view(moved, "N", decision_seq=0)
    )


def test_control_shown_card_is_visible_on_turn_and_hidden_while_waiting() -> None:
    state, _ = advance(start("2p", seed=4), in_phase(Phase.DRAW))
    r = state.round
    on_turn = r.to_act
    assert on_turn is not None
    waiting = next_seat("2p", on_turn)
    swapped = replace(state, round=replace(r, stock=(r.stock[1], r.stock[0], *r.stock[2:])))
    assert to_json(build_view(state, on_turn, decision_seq=0)) != to_json(
        build_view(swapped, on_turn, decision_seq=0)
    )
    assert to_json(build_view(state, waiting, decision_seq=0)) == to_json(
        build_view(swapped, waiting, decision_seq=0)
    )


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_control_hakem_sees_own_cards_before_trump_others_do_not(mode: Mode) -> None:
    state = start(mode, seed=8)
    r = state.round
    for seat in seats(mode):
        i = seat_index(mode, seat)
        other = seat_index(mode, next_seat(mode, seat))
        hands = list(r.hands)
        # swap this seat's first card with another seat's
        mine, theirs = list(hands[i]), list(hands[other])
        mine[0], theirs[0] = theirs[0], mine[0]
        hands[i], hands[other] = sorted_cards(tuple(mine)), sorted_cards(tuple(theirs))
        moved = replace(state, round=replace(r, hands=tuple(hands)))
        same = to_json(build_view(state, seat, decision_seq=0)) == to_json(
            build_view(moved, seat, decision_seq=0)
        )
        assert same == (seat != r.hakem)


def test_control_own_discards_are_visible_opponent_discards_are_not() -> None:
    state, _ = advance(start("2p", seed=5), in_phase(Phase.PLAY))
    r = state.round
    a, b = seat_index("2p", "A"), seat_index("2p", "B")
    # swap one of A's discards with one of B's discards
    da, db = list(r.discards[a]), list(r.discards[b])
    da[0], db[0] = db[0], da[0]
    discards = list(r.discards)
    discards[a], discards[b] = tuple(da), tuple(db)
    moved = replace(state, round=replace(r, discards=tuple(discards)))
    for seat in ("A", "B"):
        # each seat's own pile changed, so each view changes...
        assert to_json(build_view(state, seat, decision_seq=0)) != to_json(
            build_view(moved, seat, decision_seq=0)
        )
    # ...but only moving the *opponent's* pile around leaves a view unchanged
    db2 = list(r.discards[b])
    db2[0], db2[1] = db2[1], db2[0]
    discards2 = list(r.discards)
    discards2[b] = tuple(db2)
    reordered = replace(state, round=replace(r, discards=tuple(discards2)))
    assert to_json(build_view(state, "A", decision_seq=0)) == to_json(
        build_view(reordered, "A", decision_seq=0)
    )
    assert to_json(build_view(state, "B", decision_seq=0)) != to_json(
        build_view(reordered, "B", decision_seq=0)
    )
