import pytest

from hokm.engine.cards import (
    CANONICAL_DECK,
    RANKS_HIGH_TO_LOW,
    Card,
    Rank,
    Suit,
    full_deck,
    parse_cards,
)
from hokm.engine.variants import ConfigError, MatchConfig


def test_R1_1_deck_is_52_distinct_cards_in_four_suits() -> None:
    assert len(CANONICAL_DECK) == 52
    assert len(set(CANONICAL_DECK)) == 52
    assert [s.value for s in Suit] == ["S", "H", "D", "C"]
    for suit in Suit:
        assert sum(c.suit == suit for c in CANONICAL_DECK) == 13


def test_R1_2_rank_order_high_to_low() -> None:
    symbols = [r.symbol for r in RANKS_HIGH_TO_LOW]
    assert symbols == ["A", "K", "Q", "J", "10", "9", "8", "7", "6", "5", "4", "3", "2"]
    assert Rank.ACE > Rank.KING > Rank.TEN > Rank.TWO


def test_R1_3_notation_round_trips_for_every_card() -> None:
    for card in CANONICAL_DECK:
        assert Card.parse(str(card)) == card
    assert str(Card(Rank.TEN, Suit.HEARTS)) == "10H"
    assert Card.parse("AS") == Card(Rank.ACE, Suit.SPADES)
    assert parse_cards("AS 10H 2D") == (
        Card(Rank.ACE, Suit.SPADES),
        Card(Rank.TEN, Suit.HEARTS),
        Card(Rank.TWO, Suit.DIAMONDS),
    )


@pytest.mark.parametrize("text", ["", "A", "1S", "11H", "AX", "as", "10", "S", "TH", "AS "])
def test_R1_3_bad_notation_is_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        Card.parse(text)


def test_R1_4_two_player_removes_the_black_twos_by_default() -> None:
    config = MatchConfig.new("2p", 5, seed=1)
    assert config.removed_cards == parse_cards("2S 2C")
    assert len(config.deck) == 50
    assert not set(parse_cards("2S 2C")) & set(config.deck)


def test_R1_4_removed_cards_are_configurable() -> None:
    config = MatchConfig.new("2p", 5, seed=1, removed_cards=parse_cards("2H 2D"))
    assert set(CANONICAL_DECK) - set(config.deck) == set(parse_cards("2H 2D"))


@pytest.mark.parametrize("removed", ["2S", "2S 2S", "2S 2C 2H", ""])
def test_R1_4_must_remove_exactly_two_distinct_cards(removed: str) -> None:
    with pytest.raises(ConfigError):
        MatchConfig.new("2p", 5, seed=1, removed_cards=parse_cards(removed))


def test_R1_4_four_player_uses_the_full_deck() -> None:
    assert MatchConfig.new("4p", 5, seed=1).deck == CANONICAL_DECK
    with pytest.raises(ConfigError):
        MatchConfig.new("4p", 5, seed=1, removed_cards=parse_cards("2S 2C"))


def test_full_deck_keeps_canonical_order() -> None:
    deck = full_deck(parse_cards("2S 2C"))
    assert list(deck) == sorted(deck, key=Card.sort_key)
