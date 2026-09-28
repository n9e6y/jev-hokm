import pytest

from hokm.engine.actions import ChooseTrump
from hokm.engine.cards import Suit
from hokm.engine.deck import shuffled_deck
from hokm.engine.errors import NotYourTurn
from hokm.engine.events import CardsDealt, MatchStarted, RoundStarted, TrumpDeclared
from hokm.engine.rules import apply, deal_order, legal_actions, new_match
from hokm.engine.state import Phase
from hokm.engine.variants import MatchConfig, Mode, Seat, seats

SEEDS = range(8)


@pytest.mark.parametrize("seed", SEEDS)
def test_R4_1_deal_five_each_from_the_hakem_in_play_order(seed: int) -> None:
    config = MatchConfig.new("4p", 5, seed)
    state, _ = new_match(config)
    deck = shuffled_deck(config, 1)
    order = deal_order("4p", state.round.hakem)
    assert order[0] == state.round.hakem
    assert set(order) == set(seats("4p"))
    for i, seat in enumerate(order):
        assert set(state.hand(seat)) == set(deck[5 * i : 5 * i + 5])
    assert state.round.stock == deck[20:]
    assert state.phase is Phase.TRUMP


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_R4_2_only_the_hakem_sees_cards_before_trump(mode: Mode) -> None:
    for seed in SEEDS:
        state, events = new_match(MatchConfig.new(mode, 5, seed))
        hakem = state.round.hakem
        assert events == (
            MatchStarted(state.mode, 5, seats(state.mode)),
            RoundStarted(1, hakem),
            CardsDealt(hakem, state.hand(hakem)),
        )
        assert len(state.hand(hakem)) == 5


def test_R4_3_only_the_hakem_chooses_trump() -> None:
    state, _ = new_match(MatchConfig.new("4p", 5, seed=2))
    hakem = state.round.hakem
    assert len(legal_actions(state, hakem)) == 4
    for seat in seats("4p"):
        if seat != hakem:
            assert legal_actions(state, seat) == ()
            with pytest.raises(NotYourTurn):
                apply(state, ChooseTrump(seat, Suit.SPADES))


@pytest.mark.parametrize("seed", SEEDS)
def test_R4_4_deal_four_then_four_from_the_hakem(seed: int) -> None:
    config = MatchConfig.new("4p", 5, seed)
    state, _ = new_match(config)
    hakem = state.round.hakem
    first_five = {s: state.hand(s) for s in seats("4p")}
    state, events = apply(state, ChooseTrump(hakem, Suit.CLUBS))

    deck = shuffled_deck(config, 1)
    order = deal_order("4p", hakem)
    for i, seat in enumerate(order):
        second = deck[20 + 4 * i : 24 + 4 * i]
        third = deck[36 + 4 * i : 40 + 4 * i]
        assert set(state.hand(seat)) == set(first_five[seat]) | set(second) | set(third)
        assert len(state.hand(seat)) == 13
    assert state.round.stock == ()
    assert set().union(*(state.hand(s) for s in seats("4p"))) == set(deck)

    # ADR-012: after TrumpDeclared, one CardsDealt per seat with the newly visible cards
    assert events[0] == TrumpDeclared(hakem, Suit.CLUBS)
    dealt = events[1:]
    assert [e.seat for e in dealt if isinstance(e, CardsDealt)] == list(order)
    for e in dealt:
        assert isinstance(e, CardsDealt)
        if e.seat == hakem:
            assert set(e.cards) == set(state.hand(hakem)) - set(first_five[hakem])
            assert len(e.cards) == 8
        else:
            assert e.cards == state.hand(e.seat)
    assert state.phase is Phase.PLAY


@pytest.mark.parametrize("seed", SEEDS)
def test_R5_1_two_player_deal_from_fifty_cards(seed: int) -> None:
    config = MatchConfig.new("2p", 5, seed)
    state, _ = new_match(config)
    deck = shuffled_deck(config, 1)
    assert len(deck) == 50
    hakem = state.round.hakem
    opponent = deal_order("2p", hakem)[1]
    assert set(state.hand(hakem)) == set(deck[0:5])
    assert set(state.hand(opponent)) == set(deck[5:10])
    assert state.round.stock == deck[10:]
    assert len(state.round.stock) == 40


def test_R5_2_opponent_sees_their_five_only_after_trump() -> None:
    state, _ = new_match(MatchConfig.new("2p", 5, seed=4))
    hakem = state.round.hakem
    opponent = deal_order("2p", hakem)[1]
    assert legal_actions(state, opponent) == ()
    state, events = apply(state, ChooseTrump(hakem, Suit.DIAMONDS))
    assert events == (
        TrumpDeclared(hakem, Suit.DIAMONDS),
        CardsDealt(opponent, state.hand(opponent)),
    )
    assert len(state.hand(opponent)) == 5
    assert state.phase is Phase.DISCARD


# Written out by hand from R2.1 (S → E → N → W), not computed with the engine's own helpers.
DEAL_ORDERS: dict[Seat, tuple[Seat, ...]] = {
    "S": ("S", "E", "N", "W"),
    "E": ("E", "N", "W", "S"),
    "N": ("N", "W", "S", "E"),
    "W": ("W", "S", "E", "N"),
}


@pytest.mark.parametrize("hakem", ["S", "E", "N", "W"])
def test_R4_1_R4_4_deal_goes_counter_clockwise_from_the_hakem(hakem: Seat) -> None:
    assert deal_order("4p", hakem) == DEAL_ORDERS[hakem]
    assert deal_order("2p", "A") == ("A", "B") and deal_order("2p", "B") == ("B", "A")
    # find a seeded match with this hakem and check the actual cards against the fixed order
    seed = next(
        s for s in range(200) if new_match(MatchConfig.new("4p", 5, s))[0].round.hakem == hakem
    )
    config = MatchConfig.new("4p", 5, seed)
    state, _ = new_match(config)
    deck = shuffled_deck(config, 1)
    for i, seat in enumerate(DEAL_ORDERS[hakem]):
        assert set(state.hand(seat)) == set(deck[5 * i : 5 * i + 5])
    state, events = apply(state, ChooseTrump(hakem, Suit.HEARTS))
    for i, seat in enumerate(DEAL_ORDERS[hakem]):
        later = set(deck[20 + 4 * i : 24 + 4 * i]) | set(deck[36 + 4 * i : 40 + 4 * i])
        assert set(state.hand(seat)) == set(deck[5 * i : 5 * i + 5]) | later
    assert [e.seat for e in events if isinstance(e, CardsDealt)] == list(DEAL_ORDERS[hakem])
