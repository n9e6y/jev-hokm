"""No steering (CLAUDE.md non-negotiable 2): the raw view has exactly the SEAT_VIEW fields, no
tags, and no word that judges an option."""

import re

import pytest

from hokm.engine.variants import Mode, seats
from hokm.views import build_view
from hokm.views.schema import SeatView
from tests.engine.support import random_match
from tests.views.support import live_moments

HEADER = {
    "schema_version",
    "profile",
    "profile_version",
    "mode",
    "phase",
    "seat",
    "hakem",
    "trump_suit",
    "scores",
}
PHASE_FIELDS = {
    "trump": {"hand", "options"},
    "discard": {"hand", "options", "discard_count", "own_discards"},
    "draw": {"turn", "turns_total", "hand", "own_discards", "card_shown", "stock_left", "options"},
    "play": {"hand", "trick", "options", "history"},
}
SCORES = {"round_tricks", "tricks_to_win", "match_points", "match_target"}
JUDGING = re.compile(r"safe|good|bad|strong|weak|master|best|recommend|risky", re.IGNORECASE)


def _expected_keys(mode: Mode, phase: str) -> set[str]:
    keys = HEADER | PHASE_FIELDS[phase]
    if mode == "4p":
        keys.add("partner")
    if mode == "2p" and phase == "play":
        keys.add("own_discards")
    return keys


def _strings(value: object) -> list[str]:
    """Every dict key and string value, recursively."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for k, v in value.items():  # type: ignore[union-attr]
            out.append(str(k))
            out.extend(_strings(v))
        return out
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]  # type: ignore[union-attr]
    return []


def _all_views(mode: Mode) -> list[SeatView]:
    views: list[SeatView] = []
    for seed in range(4):
        for state, seq in live_moments(random_match(mode, seed, target=1 + 2 * (seed % 2))):
            views.extend(build_view(state, s, decision_seq=seq) for s in seats(mode))
    return views


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_raw_views_have_exactly_the_documented_fields(mode: Mode) -> None:
    for view in _all_views(mode):
        assert set(view) == _expected_keys(mode, view["phase"])
        assert set(view["scores"]) == SCORES
        assert view["profile"] == "raw"
        if view["phase"] == "play":
            assert set(view["trick"]) == {"number", "leader", "cards"}
            for h in view["history"]:
                assert set(h) == {"trick", "cards", "winner"}
                assert all(set(c) == {"seat", "card"} for c in h["cards"])


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_no_judging_words_and_options_are_plain_labels(mode: Mode) -> None:
    for view in _all_views(mode):
        for text in _strings(view):
            assert not JUDGING.search(text), f"judging word in {text!r}"
        # options are bare labels: suit names, keep/discard, or card notation; never tagged
        assert all(isinstance(o, str) and " " not in o for o in view["options"])
