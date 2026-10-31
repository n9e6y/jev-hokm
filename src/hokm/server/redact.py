"""Per-seat redaction: one function per event type (docs/PROTOCOL.md "Visible to").

Fails closed: an event type without a redactor raises instead of passing through. The
sending path takes only `Redacted` values, so nothing can be sent without coming through here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from hokm.engine.variants import Seat
from hokm.protocol import events as wire

type Viewer = Seat | Literal["observer"]


_TOKEN = object()


@dataclass(frozen=True, slots=True)
class Redacted:
    """A payload already cut down for `viewer`. Only `redact` can make these."""

    viewer: Viewer
    payload: wire.WirePayload
    _token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _TOKEN:
            raise TypeError("Redacted values come only from redact()")


def _public(payload: Any, viewer: Viewer) -> Any:
    return payload


def _owner_only(payload: Any, viewer: Viewer) -> Any:
    # CardsDealt, CardShown: other seats get nothing at all
    return payload if viewer in ("observer", payload.seat) else None


def _discarded(payload: wire.CardDiscardedPayload, viewer: Viewer) -> Any:
    # R5.3 others learn that a card went, never which
    if viewer in ("observer", payload.seat):
        return payload
    return wire.CardDiscardedPayload(seat=payload.seat)


def _draw_resolved(payload: wire.DrawResolvedPayload, viewer: Viewer) -> Any:
    # R5.4 others see the turn happen, not what was kept or dropped
    if viewer in ("observer", payload.seat):
        return payload
    return wire.DrawResolvedPayload(seat=payload.seat)


def _observer_only(payload: Any, viewer: Viewer) -> Any:
    return payload if viewer == "observer" else None


REDACTORS: dict[type[wire.WirePayload], Callable[[Any, Viewer], Any]] = {
    wire.MatchStartedPayload: _public,
    wire.RoundStartedPayload: _public,
    wire.CardsDealtPayload: _owner_only,
    wire.TrumpDeclaredPayload: _public,
    wire.CardDiscardedPayload: _discarded,
    wire.CardShownPayload: _owner_only,
    wire.DrawResolvedPayload: _draw_resolved,
    wire.CardPlayedPayload: _public,
    wire.TrickWonPayload: _public,
    wire.RoundEndedPayload: _public,
    wire.MatchEndedPayload: _public,
    wire.BotDecisionPayload: _observer_only,
    wire.BotPausedPayload: _observer_only,
}


def redact(payload: wire.WirePayload, viewer: Viewer) -> Redacted | None:
    """What `viewer` receives of this event; None when it receives nothing."""
    cut = REDACTORS[type(payload)](payload, viewer)
    return None if cut is None else Redacted(viewer, cut, _TOKEN)
