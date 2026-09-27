from collections import Counter

from hokm.engine.deck import first_hakem, shuffled_deck
from hokm.engine.variants import MatchConfig, seats


def test_R3_4_round_deck_is_a_permutation_of_the_match_deck() -> None:
    for mode in ("2p", "4p"):
        config = MatchConfig.new(mode, 5, seed=42)
        deck = shuffled_deck(config, 1)
        assert Counter(deck) == Counter(config.deck)


def test_R3_4_same_seed_and_round_give_the_same_deck() -> None:
    config = MatchConfig.new("4p", 5, seed=42)
    assert shuffled_deck(config, 3) == shuffled_deck(config, 3)
    assert shuffled_deck(config, 3) == shuffled_deck(MatchConfig.new("4p", 7, seed=42), 3)


def test_R3_4_each_round_and_each_seed_shuffles_differently() -> None:
    config = MatchConfig.new("4p", 5, seed=42)
    decks = {shuffled_deck(config, n) for n in range(1, 21)}
    assert len(decks) == 20
    assert shuffled_deck(config, 1) != shuffled_deck(MatchConfig.new("4p", 5, seed=43), 1)
    assert shuffled_deck(config, 1) != config.deck


def test_R3_4_seeded_deck_is_pinned() -> None:
    # ADR-012: the seed derivation is frozen for rules v1. If this fails, recorded deals changed.
    deck = shuffled_deck(MatchConfig.new("4p", 5, seed=1), 1)
    assert [str(c) for c in deck[:5]] == PINNED_SEED1_ROUND1_TOP5


def test_R3_2_first_hakem_is_seeded_and_covers_every_seat() -> None:
    config = MatchConfig.new("4p", 5, seed=7)
    assert first_hakem(config) == first_hakem(config)
    for mode in ("2p", "4p"):
        chosen = {first_hakem(MatchConfig.new(mode, 5, seed=s)) for s in range(200)}
        assert chosen == set(seats(mode))


PINNED_SEED1_ROUND1_TOP5 = ["4H", "6C", "2S", "5H", "4S"]
