"""Error codes the server answers an intent with (docs/PROTOCOL.md)."""

from __future__ import annotations

from typing import Literal

type ErrorCode = Literal[
    "not_your_turn", "bad_phase", "illegal_action", "bad_payload", "match_over"
]
