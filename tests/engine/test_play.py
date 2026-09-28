import pytest

from hokm.engine.actions import PlayCard
from hokm.engine.cards import Card, Suit, parse_cards
from hokm.engine.errors import BadPhase, IllegalAction, NotYourTurn
from hokm.engine.events import CardPlayed, TrickWon
from hokm.engine.rules import apply, legal_actions, trick_winner
from hokm.engine.state import MatchState, Phase, Play, Trick
from hokm.engine.variants import Mode, Seat
from tests.engine.support import advance, in_phase, play_state, start


def _card(text: str) -> Card:
    return Card.parse(text)


def _playable(state: MatchState, seat: Seat) -> set[str]:
    return {str(a.card) for a in legal_actions(state, seat) if isinstance(a, PlayCard)}


def _play(state: MatchState, *moves: tuple[Seat, str]) -> MatchState:
    for seat, card in moves:
        state, _ = apply(state, PlayCard(seat, _card(card)))
    return state


@pytest.mark.parametrize("mode", ["2p", "4p"])
@pytest.mark.parametrize("seed", range(4))
def test_R7_1_the_hakem_leads_the_first_trick(mode: Mode, seed: int) -> None:
    state, _ = advance(start(mode, seed), in_phase(Phase.PLAY))
    hakem = state.round.hakem
    assert state.round.to_act == hakem
    assert state.round.trick == Trick(1, hakem)


def test_R7_2_must_follow_the_led_suit_when_able() -> None:
    state = play_state("2p", {"A": "AS 5S KH", "B": "QS 2H 3D"}, leader="A")
    state = _play(state, ("A", "5S"))
    assert _playable(state, "B") == {"QS"}
    with pytest.raises(IllegalAction):
        apply(state, PlayCard("B", _card("2H")))


def test_R7_2_a_void_seat_may_play_any_card() -> None:
    state = play_state("2p", {"A": "AS KH", "B": "2C 3D"}, leader="A")
    state = _play(state, ("A", "KH"))
    assert _playable(state, "B") == {"2C", "3D"}
    state = _play(state, ("B", "2C"))  # discarding off-suit is accepted


def test_R7_2_four_player_follow_suit() -> None:
    hands: dict[Seat, str] = {"S": "AS 2H", "E": "3S 4H", "N": "5D 6H", "W": "7C 8C"}
    state = play_state("4p", hands, leader="S")
    state = _play(state, ("S", "2H"))
    assert _playable(state, "E") == {"4H"}
    state = _play(state, ("E", "4H"))
    assert _playable(state, "N") == {"6H"}
    state = _play(state, ("N", "6H"))
    assert _playable(state, "W") == {"7C", "8C"}


def _trick(leader: Seat, cards: str, order: tuple[Seat, ...]) -> Trick:
    return Trick(
        1, leader, tuple(Play(s, c) for s, c in zip(order, parse_cards(cards), strict=True))
    )


ORDER: tuple[Seat, ...] = ("S", "E", "N", "W")


def test_R7_3_highest_card_of_the_led_suit_wins_without_trump() -> None:
    trick = _trick("S", "10H AS QH 2C", ORDER)  # AS is off-suit and cannot win
    assert trick_winner(trick, Suit.DIAMONDS) == "N"


def test_R7_3_any_trump_beats_the_led_suit() -> None:
    trick = _trick("S", "AH KH QH 2C", ORDER)
    assert trick_winner(trick, Suit.CLUBS) == "W"


def test_R7_3_highest_trump_wins() -> None:
    trick = _trick("S", "AH 3C QH JC", ORDER)
    assert trick_winner(trick, Suit.CLUBS) == "W"
    # trump led: still the highest trump
    trick = _trick("S", "5C AC 2H KH", ORDER)
    assert trick_winner(trick, Suit.CLUBS) == "E"


def test_R7_3_trick_resolution_through_apply() -> None:
    hands: dict[Seat, str] = {"S": "10H 4S", "E": "AS 5S", "N": "QH 6S", "W": "2C 7S"}
    state = play_state("4p", hands, trump=Suit.DIAMONDS, leader="S")
    state, _ = apply(
        _play(state, ("S", "10H"), ("E", "AS"), ("N", "QH")), PlayCard("W", _card("2C"))
    )
    assert state.round.tricks[-1].winner == "N"
    assert state.tricks_of("NS") == 1 and state.tricks_of("EW") == 0


def test_R7_4_the_trick_winner_leads_the_next_trick() -> None:
    state = play_state("2p", {"A": "KS 2D", "B": "AS 3D"}, trump=Suit.CLUBS, leader="A")
    state = _play(state, ("A", "KS"))
    state, events = apply(state, PlayCard("B", _card("AS")))
    assert events == (CardPlayed("B", _card("AS")), TrickWon(1, "B", (0, 1)))
    assert state.round.to_act == "B"
    assert state.round.trick == Trick(2, "B")
    assert state.round.tricks == (
        Trick(1, "A", (Play("A", _card("KS")), Play("B", _card("AS"))), "B"),
    )


def test_R7_5_any_card_may_be_led_including_trump() -> None:
    state = play_state("2p", {"A": "AS 2H 3C", "B": "KS 4H 5C"}, trump=Suit.CLUBS, leader="A")
    assert _playable(state, "A") == {"AS", "2H", "3C"}
    state = _play(state, ("A", "3C"))
    assert _playable(state, "B") == {"5C"}


def test_playing_out_of_turn_is_rejected() -> None:
    state = play_state("2p", {"A": "AS", "B": "KS"}, leader="A")
    assert legal_actions(state, "B") == ()
    with pytest.raises(NotYourTurn):
        apply(state, PlayCard("B", _card("KS")))


def test_playing_a_card_not_in_hand_is_rejected() -> None:
    state = play_state("2p", {"A": "AS", "B": "KS"}, leader="A")
    with pytest.raises(IllegalAction):
        apply(state, PlayCard("A", _card("KS")))


def test_playing_before_the_play_phase_is_rejected() -> None:
    state = start("4p")
    hakem = state.round.hakem
    with pytest.raises(BadPhase):
        apply(state, PlayCard(hakem, state.hand(hakem)[0]))
