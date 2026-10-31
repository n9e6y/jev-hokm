import json
import typing

import pytest
from pydantic import TypeAdapter, ValidationError

from hokm.engine import events as engine_events
from hokm.protocol import ObserverMessage, PlayerMessage, engine_event_to_wire, event_message
from hokm.protocol import events as wire
from tests.engine.support import random_match

ADAPTER = TypeAdapter(PlayerMessage)
OBSERVER = TypeAdapter(ObserverMessage)


def test_every_engine_event_has_a_wire_message_with_the_same_name():
    engine_names = {cls.__name__ for cls in typing.get_args(engine_events.Event.__value__)}
    wire_names = {msg.model_fields["name"].default for msg in wire.MESSAGE_FOR.values()}
    assert engine_names <= wire_names
    assert wire_names - engine_names == {"BotDecision", "BotPaused"}  # server-only


@pytest.mark.parametrize("mode", ["2p", "4p"])
@pytest.mark.parametrize("seed", range(5))
def test_every_event_of_random_matches_round_trips(mode, seed):
    match = random_match(mode, seed)
    for seq, event in enumerate(match.events):
        msg = event_message("m_1", seq, engine_event_to_wire(event))
        assert msg.model_dump()["name"] == type(event).__name__
        assert ADAPTER.validate_json(msg.model_dump_json()) == msg


@pytest.mark.parametrize(
    "hidden",
    [
        wire.CardDiscardedPayload(seat="A"),
        wire.DrawResolvedPayload(seat="B"),
    ],
)
def test_hidden_cards_are_left_out_so_others_get_seat_only(hidden):
    msg = event_message("m_1", 3, hidden)
    assert json.loads(msg.model_dump_json())["payload"] == {"seat": hidden.seat}
    assert ADAPTER.validate_json(msg.model_dump_json()) == msg


def test_owner_still_sees_the_hidden_cards():
    shown = wire.DrawResolvedPayload(seat="B", kept="AS", dropped="2H")
    payload = json.loads(event_message("m_1", 3, shown).model_dump_json())["payload"]
    assert payload == {"seat": "B", "kept": "AS", "dropped": "2H"}


def test_bot_events_reach_observers_but_not_players():
    for payload in (
        wire.BotDecisionPayload(seat="A", decision_id="d_1"),
        wire.BotPausedPayload(seat="A", reason="transport_error"),
    ):
        text = event_message("m_1", 9, payload).model_dump_json()
        assert OBSERVER.validate_json(text).model_dump_json() == text
        with pytest.raises(ValidationError):
            ADAPTER.validate_json(text)


def test_pause_reason_is_a_fixed_vocabulary():
    with pytest.raises(ValidationError):
        wire.BotPausedPayload(seat="A", reason="HTTP 500: {'hand': ['AS']}")  # type: ignore[arg-type]


def test_bad_card_and_extra_fields_are_rejected():
    ok = '{"v":1,"type":"event","match_id":"m","seq":1,"name":"CardPlayed","payload":%s}'
    ADAPTER.validate_json(ok % '{"seat":"E","card":"QS"}')
    for payload in (
        '{"seat":"E","card":"1S"}',
        '{"seat":"E","card":"qs"}',
        '{"seat":"X","card":"QS"}',
        '{"seat":"E","card":"QS","hand":[]}',
    ):
        with pytest.raises(ValidationError):
            ADAPTER.validate_json(ok % payload)


def test_unknown_version_is_rejected():
    with pytest.raises(ValidationError):
        ADAPTER.validate_json('{"v":2,"type":"ack","match_id":"m","intent_id":"%s"}' % ("0" * 32))
