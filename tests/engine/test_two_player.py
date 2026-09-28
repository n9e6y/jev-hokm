import random
from itertools import pairwise

import pytest

from hokm.engine.actions import ChooseTrump, Discard, DrawDecision
from hokm.engine.cards import Card, Suit, parse_cards
from hokm.engine.errors import IllegalAction, NotYourTurn
from hokm.engine.events import CardDiscarded, CardsDealt, CardShown, DrawResolved
from hokm.engine.rules import apply, deal_order, legal_actions, new_match
from hokm.engine.state import MatchState, Phase
from hokm.engine.variants import MatchConfig, Seat
from tests.engine.support import Chooser, advance, in_phase, start


def _discard_phase(seed: int = 5) -> MatchState:
    state = start("2p", seed)
    state, _ = apply(state, ChooseTrump(state.round.hakem, Suit.HEARTS))
    return state


def _draw_phase(seed: int = 5) -> MatchState:
    state, _ = advance(_discard_phase(seed), in_phase(Phase.DRAW))
    return state


def _opponent(state: MatchState) -> Seat:
    return deal_order("2p", state.round.hakem)[1]


def test_R5_3_hakem_discards_first() -> None:
    state = _discard_phase()
    opponent = _opponent(state)
    assert legal_actions(state, opponent) == ()
    with pytest.raises(NotYourTurn):
        apply(state, Discard(opponent, state.hand(opponent)[:2]))


def test_R5_3_legal_discards_are_all_ten_pairs() -> None:
    state = _discard_phase()
    options = legal_actions(state, state.round.hakem)
    assert len(options) == 10
    assert len({frozenset(a.cards) for a in options if isinstance(a, Discard)}) == 10


@pytest.mark.parametrize("pick", ["one", "three", "duplicate", "not_in_hand"])
def test_R5_3_must_discard_exactly_two_distinct_cards_from_hand(pick: str) -> None:
    state = _discard_phase()
    hakem = state.round.hakem
    hand = state.hand(hakem)
    outsider = next(c for c in state.hand(_opponent(state)))
    cards: tuple[Card, ...] = {
        "one": hand[:1],
        "three": hand[:3],
        "duplicate": (hand[0], hand[0]),
        "not_in_hand": (hand[0], outsider),
    }[pick]
    with pytest.raises(IllegalAction):
        apply(state, Discard(hakem, cards))


def test_R5_3_both_discard_two_then_hands_hold_three_and_stock_forty() -> None:
    state = _discard_phase()
    hakem, opponent = state.round.hakem, _opponent(state)
    h_cards, o_cards = state.hand(hakem)[1:3], state.hand(opponent)[:2]
    state, events = apply(state, Discard(hakem, h_cards))
    assert events == tuple(CardDiscarded(hakem, c) for c in h_cards)
    assert state.phase is Phase.DISCARD and state.round.to_act == opponent
    state, events = apply(state, Discard(opponent, o_cards))
    assert events[:2] == tuple(CardDiscarded(opponent, c) for c in o_cards)
    assert state.discards(hakem) == h_cards
    assert state.discards(opponent) == o_cards
    assert len(state.hand(hakem)) == len(state.hand(opponent)) == 3
    assert len(state.round.stock) == 40
    # R5.4 the draw phase starts with the hakem shown the top card
    assert state.phase is Phase.DRAW and state.round.to_act == hakem
    assert events[2] == CardShown(hakem, state.round.stock[0])


@pytest.mark.parametrize("keep", [True, False])
def test_R5_4_keep_or_discard_the_shown_card(keep: bool) -> None:
    state = _draw_phase()
    seat = state.round.hakem
    assert state.round.to_act == seat
    c1, c2 = state.round.stock[:2]
    before_hand, before_discards = state.hand(seat), state.discards(seat)
    state, events = apply(state, DrawDecision(seat, keep))
    kept, dropped = (c1, c2) if keep else (c2, c1)
    assert set(state.hand(seat)) == {*before_hand, kept}
    assert state.discards(seat) == (*before_discards, dropped)
    assert len(state.round.stock) == 38
    nxt = _opponent(state)
    assert events == (DrawResolved(seat, kept, dropped), CardShown(nxt, state.round.stock[0]))
    assert state.round.to_act == nxt


def _random_keep(rng: random.Random) -> Chooser:
    return lambda options: rng.choice(options)


@pytest.mark.parametrize("seed", range(6))
def test_R5_4_twenty_turns_alternate_starting_with_the_hakem(seed: int) -> None:
    state = _draw_phase(seed)
    hakem, opponent = state.round.hakem, _opponent(state)
    state, events = advance(state, in_phase(Phase.PLAY), _random_keep(random.Random(seed)))
    turns = [e.seat for e in events if isinstance(e, DrawResolved)]
    assert len(turns) == 20
    assert turns[0] == hakem
    assert all(a != b for a, b in pairwise(turns))
    assert turns.count(hakem) == turns.count(opponent) == 10


@pytest.mark.parametrize("seed", range(6))
def test_R5_5_draw_ends_with_thirteen_each_and_an_empty_stock(seed: int) -> None:
    state, _ = advance(_draw_phase(seed), in_phase(Phase.PLAY), _random_keep(random.Random(seed)))
    for seat in ("A", "B"):
        assert len(state.hand(seat)) == 13
        assert len(state.discards(seat)) == 12  # 2 opening + 10 draw turns
    assert state.round.stock == ()
    assert state.round.draw_turns_done == 20
    assert state.round.to_act == state.round.hakem
    assert state.round.trick is not None and state.round.trick.leader == state.round.hakem


@pytest.mark.parametrize("seed", range(6))
def test_R5_6_each_seat_knows_exactly_its_hand_discards_and_shown_cards(seed: int) -> None:
    state, opening = new_match(MatchConfig.new("2p", 7, seed))
    state, rest = advance(state, in_phase(Phase.PLAY), _random_keep(random.Random(seed)))
    for seat in ("A", "B"):
        told: set[Card] = set()
        for e in (*opening, *rest):
            match e:
                case CardsDealt(seat=s, cards=cards) if s == seat:
                    told |= set(cards)
                case CardShown(seat=s, card=card) | CardDiscarded(seat=s, card=card) if s == seat:
                    told.add(card)
                case DrawResolved(seat=s, kept=kept, dropped=dropped) if s == seat:
                    told |= {kept, dropped}
                case _:
                    pass
        # every card a seat holds or discarded was dealt or shown to it, and nothing else
        assert set(state.hand(seat)) | set(state.discards(seat)) == told


def test_removed_cards_never_appear() -> None:
    state, _ = advance(_draw_phase(1), in_phase(Phase.PLAY))
    everything = {c for s in ("A", "B") for c in (*state.hand(s), *state.discards(s))}
    assert len(everything) == 50
    assert not everything & set(parse_cards("2S 2C"))
