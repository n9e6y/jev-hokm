import typing

import pytest
from pydantic import TypeAdapter, ValidationError

from hokm.engine import events as engine_events
from hokm.protocol import ServerMessage, engine_event_to_wire, event_message
from hokm.protocol import events as wire
from tests.engine.support import random_match

ADAPTER = TypeAdapter(ServerMessage)


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


def test_redacted_payload_is_the_same_model_with_none():
    hidden = wire.CardDiscardedPayload(seat="A", card=None)
    msg = event_message("m_1", 3, hidden)
    assert ADAPTER.validate_json(msg.model_dump_json()) == msg


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
