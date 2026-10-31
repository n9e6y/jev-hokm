from uuid import uuid4

import pytest
from pydantic import ValidationError

from hokm.protocol import ERROR_TEXT, ErrorMsg


@pytest.mark.parametrize("code", sorted(ERROR_TEXT))
def test_error_message_is_the_fixed_text_of_its_code(code):
    msg = ErrorMsg(match_id="m_1", intent_id=uuid4(), code=code)
    assert msg.message == ERROR_TEXT[code]
    assert ErrorMsg.model_validate_json(msg.model_dump_json()) == msg


def test_error_message_cannot_carry_free_text():
    with pytest.raises(ValidationError):
        ErrorMsg(match_id="m_1", code="illegal_action", message="AS is not in hand [KS, 2H]")
