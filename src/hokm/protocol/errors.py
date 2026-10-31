"""Error codes the server answers an intent with (docs/PROTOCOL.md).

Each code has one fixed message, so no engine exception text (which may name cards) can reach
a client.
"""

from __future__ import annotations

from typing import Literal

type ErrorCode = Literal[
    "not_your_turn", "bad_phase", "illegal_action", "bad_payload", "match_over"
]

ERROR_TEXT: dict[ErrorCode, str] = {
    "not_your_turn": "It is not your turn.",
    "bad_phase": "That action is not possible in this phase.",
    "illegal_action": "That action is not allowed by the rules.",
    "bad_payload": "The message could not be read.",
    "match_over": "The match is over.",
}
