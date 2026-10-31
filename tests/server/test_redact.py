import json

import pytest

from hokm.engine import events as ev
from hokm.engine.variants import seats
from hokm.protocol import engine_event_to_wire
from hokm.protocol import events as wire
from hokm.server.redact import REDACTORS, Redacted, redact
from tests.engine.support import random_match


def hidden_cards(event: ev.Event) -> tuple[str | None, list[str]]:
    """(owner, cards only the owner may see) for one engine event."""
    match event:
        case ev.CardsDealt():
            return event.seat, [str(c) for c in event.cards]
        case ev.CardShown() | ev.CardDiscarded():
            return event.seat, [str(event.card)]
        case ev.DrawResolved():
            return event.seat, [str(event.kept), str(event.dropped)]
        case _:
            return None, []


def test_every_payload_type_has_its_own_redactor():
    assert set(REDACTORS) == set(wire.MESSAGE_FOR)


@pytest.mark.parametrize("mode", ["2p", "4p"])
@pytest.mark.parametrize("seed", range(6))
def test_no_seat_receives_a_card_hidden_from_it(mode, seed):
    for event in random_match(mode, seed).events:
        payload = engine_event_to_wire(event)
        owner, hidden = hidden_cards(event)
        for viewer in seats(mode):
            got = redact(payload, viewer)
            if viewer == owner or not hidden:
                assert got is not None and got.payload == payload
                continue
            text = "" if got is None else got.payload.model_dump_json()
            if isinstance(event, ev.CardDiscarded | ev.DrawResolved):
                assert json.loads(text) == {"seat": owner}  # who, never what
            for card in hidden:
                assert f'"{card}"' not in text, f"{viewer} saw {card} in {type(event).__name__}"


@pytest.mark.parametrize("mode", ["2p", "4p"])
def test_observer_receives_everything(mode):
    for event in random_match(mode, 2).events:
        payload = engine_event_to_wire(event)
        got = redact(payload, "observer")
        assert got is not None and got.payload == payload


def test_others_learn_who_discarded_and_drew_but_not_what():
    discarded = redact(wire.CardDiscardedPayload(seat="A", card="QS"), "B")
    drawn = redact(wire.DrawResolvedPayload(seat="A", kept="QS", dropped="2H"), "B")
    assert discarded is not None and drawn is not None
    assert json.loads(discarded.payload.model_dump_json()) == {"seat": "A"}
    assert json.loads(drawn.payload.model_dump_json()) == {"seat": "A"}


def test_owner_only_events_are_not_sent_to_others():
    assert redact(wire.CardsDealtPayload(seat="A", cards=["AS"]), "B") is None
    assert redact(wire.CardShownPayload(seat="A", card="AS"), "B") is None


def test_bot_events_go_to_observers_only():
    for payload in (
        wire.BotDecisionPayload(seat="A", decision_id="d"),
        wire.BotPausedPayload(seat="A", reason="transport_error"),
    ):
        assert redact(payload, "A") is None
        assert redact(payload, "B") is None
        assert redact(payload, "observer") is not None


def test_redacted_values_cannot_be_made_by_hand():
    with pytest.raises(TypeError):
        Redacted("B", wire.CardsDealtPayload(seat="A", cards=["AS"]))
