"""Engine errors. `code` matches the error codes in docs/PROTOCOL.md."""

from typing import ClassVar


class EngineError(Exception):
    code: ClassVar[str] = "engine_error"


class NotYourTurn(EngineError):
    code = "not_your_turn"


class BadPhase(EngineError):
    code = "bad_phase"


class IllegalAction(EngineError):
    code = "illegal_action"


class MatchOver(EngineError):
    code = "match_over"
