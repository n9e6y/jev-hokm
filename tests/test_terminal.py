import random
from collections.abc import Iterator

import pytest

from hokm.engine.cards import parse_cards
from hokm.engine.events import CardDiscarded, CardsDealt, CardShown, DrawResolved
from hokm.engine.state import Phase
from hokm.engine.variants import MatchConfig, Mode, seats
from hokm.terminal import describe, main, play


def _always(answer: str) -> Iterator[str]:
    while True:
        yield answer


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_a_scripted_human_plays_a_whole_match(mode: Mode) -> None:
    answers = _always("1")
    out: list[str] = []
    config = MatchConfig.new(mode, 3, seed=5)
    final = play(config, seats(mode)[0], random.Random(0), lambda _: next(answers), out.append)
    assert final.phase is Phase.MATCH_END
    assert any("wins the match" in line for line in out)


def test_other_seats_hidden_cards_are_never_printed() -> None:
    secret = parse_cards("AS KH")
    for event in (
        CardsDealt("B", secret),
        CardDiscarded("B", secret[0]),
        CardShown("B", secret[0]),
        DrawResolved("B", secret[0], secret[1]),
    ):
        line = describe(event, "A", "2p") or ""
        assert "A♠" not in line and "K♥" not in line
    assert "A♠" in (describe(CardsDealt("A", secret), "A", "2p") or "")


def test_quit_and_bad_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter(["x", "99", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["--mode", "2p", "--seed", "1", "--seat", "A"]) == 0
    out = capsys.readouterr().out
    assert "type a number" in out and "bye" in out
