import random
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from hokm.engine.actions import ChooseTrump as ChooseTrumpAction
from hokm.engine.actions import Discard, DrawDecision, PlayCard
from hokm.engine.rules import apply, legal_actions
from hokm.engine.state import Phase
from hokm.protocol import Intent, intent_to_action
from hokm.protocol.intents import (
    ChooseTrumpIntent,
    DiscardIntent,
    DrawDecisionIntent,
    PlayCardIntent,
    RequestHintIntent,
)
from tests.engine.support import next_action, start

ADAPTER = TypeAdapter(Intent)


def to_intent(action):
    match action:
        case ChooseTrumpAction():
            return ChooseTrumpIntent(intent_id=uuid4(), suit=action.suit.value)
        case Discard():
            return DiscardIntent(intent_id=uuid4(), cards=[str(c) for c in action.cards])
        case DrawDecision():
            return DrawDecisionIntent(intent_id=uuid4(), keep=action.keep)
        case PlayCard():
            return PlayCardIntent(intent_id=uuid4(), card=str(action.card))
    raise AssertionError(action)


@pytest.mark.parametrize("mode", ["2p", "4p"])
@pytest.mark.parametrize("seed", range(3))
def test_every_legal_action_survives_the_wire(mode, seed):
    rng = random.Random(seed)
    state = start(mode, seed=seed, target=3)
    while state.phase is not Phase.MATCH_END:
        if state.phase is not Phase.ROUND_END:
            seat = state.round.to_act
            assert seat is not None
            for action in legal_actions(state, seat):
                intent = ADAPTER.validate_json(to_intent(action).model_dump_json())
                assert not isinstance(intent, RequestHintIntent)
                assert intent_to_action(seat, intent) == action
        state, _ = apply(state, next_action(state, rng.choice))


def test_request_hint_has_no_engine_action():
    intent = ADAPTER.validate_python({"v": 1, "intent": "request_hint", "intent_id": str(uuid4())})
    assert isinstance(intent, RequestHintIntent)


ID = str(uuid4())


@pytest.mark.parametrize(
    "bad",
    [
        {"intent": "play_card", "card": "AS"},  # no intent_id
        {"intent": "play_card", "intent_id": "not-a-uuid", "card": "AS"},
        {"intent": "play_card", "intent_id": ID, "card": "ZZ"},
        {"intent": "discard", "intent_id": ID, "cards": ["AS"]},
        {"intent": "discard", "intent_id": ID, "cards": ["AS", "KS", "QS"]},
        {"intent": "choose_trump", "intent_id": ID, "suit": "X"},
        {"intent": "choose_trump", "intent_id": ID, "suit": "S", "seat": "A"},  # not client data
        {"intent": "cheat", "intent_id": ID},
        {"v": 2, "intent": "draw_decision", "intent_id": ID, "keep": True},
    ],
)
def test_bad_intents_are_rejected(bad):
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(bad)
