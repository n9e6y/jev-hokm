"""Terminal Hokm for manual checks (1.15): one human seat against seeded random opponents.

    uv run hokm --mode 2p --target 3 --seed 7

Output is redacted to what the human's seat would see: other seats' dealt, shown and
discarded cards are never printed. The random opponents live here on purpose; the real
bots (phase 2) only ever receive seat views.
"""

from __future__ import annotations

import argparse
import random
import secrets
from collections.abc import Callable

from hokm.engine.actions import Action, ChooseTrump, Discard, DrawDecision, NextRound, PlayCard
from hokm.engine.cards import Card, Suit
from hokm.engine.events import (
    CardDiscarded,
    CardPlayed,
    CardsDealt,
    CardShown,
    DrawResolved,
    Event,
    MatchEnded,
    MatchStarted,
    RoundEnded,
    RoundStarted,
    TrickWon,
    TrumpDeclared,
)
from hokm.engine.rules import apply, legal_actions, new_match
from hokm.engine.state import MatchState, Phase
from hokm.engine.variants import MatchConfig, Mode, Seat, seats, side_of, sides

type Reader = Callable[[str], str]
type Writer = Callable[[str], None]

SUIT_SYMBOLS = {Suit.SPADES: "♠", Suit.HEARTS: "♥", Suit.DIAMONDS: "♦", Suit.CLUBS: "♣"}
SUIT_NAMES = {
    Suit.SPADES: "spades",
    Suit.HEARTS: "hearts",
    Suit.DIAMONDS: "diamonds",
    Suit.CLUBS: "clubs",
}


class Quit(Exception):
    """The human typed q or closed the input."""


def fmt(card: Card) -> str:
    return f"{card.rank.symbol}{SUIT_SYMBOLS[card.suit]}"


def fmt_cards(cards: tuple[Card, ...]) -> str:
    return " ".join(fmt(c) for c in cards)


def fmt_hand(cards: tuple[Card, ...]) -> str:
    """Hand grouped by suit: `♠ A 10 3   ♥ Q`."""
    groups = [
        f"{SUIT_SYMBOLS[s]} {' '.join(c.rank.symbol for c in cards if c.suit == s)}"
        for s in Suit
        if any(c.suit == s for c in cards)
    ]
    return "   ".join(groups) or "(empty)"


def _who(seat: Seat, me: Seat) -> str:
    return "You" if seat == me else seat


def _score(mode: Mode, values: tuple[int, ...], me: Seat) -> str:
    return "  ".join(
        f"{'us' if side == side_of(me) else side}={v}"
        for side, v in zip(sides(mode), values, strict=True)
    )


def describe(event: Event, me: Seat, mode: Mode) -> str | None:
    """One line for `event` as seen from seat `me`, or None if that seat sees nothing."""
    match event:
        case MatchStarted(target_points=target):
            return f"Match: {mode}, first side to {target} point(s). You are seat {me}."
        case RoundStarted(number=n, hakem=hakem):
            return f"\n=== Round {n} · hakem {_who(hakem, me)} ==="
        case CardsDealt(seat=seat, cards=cards):
            if seat == me:
                return f"You are dealt: {fmt_cards(cards)}"
            return f"{seat} is dealt {len(cards)} card(s)"
        case TrumpDeclared(hakem=hakem, suit=suit):
            return f"Trump ({_who(hakem, me)}): {SUIT_SYMBOLS[suit]} {SUIT_NAMES[suit]}"
        case CardDiscarded(seat=seat, card=card):
            return f"You discard {fmt(card)}" if seat == me else f"{seat} discards a card face down"
        case CardShown():
            return None  # shown to its owner only; the human sees it in their own prompt
        case DrawResolved(seat=seat, kept=kept, dropped=dropped):
            if seat == me:
                return f"You keep {fmt(kept)} and discard {fmt(dropped)}"
            return f"{seat} takes a draw turn"
        case CardPlayed(seat=seat, card=card):
            return f"  {_who(seat, me)}: {fmt(card)}"
        case TrickWon(number=n, winner=winner, tricks_won=tricks):
            return f"  → trick {n} to {_who(winner, me)}   tricks: {_score(mode, tricks, me)}"
        case RoundEnded(winner=winner, points=points, kot=kot, match_points=mp):
            label = {"kot": " (kot!)", "hakem_koti": " (hakem koti!)", None: ""}[kot]
            won = "Your side" if winner == side_of(me) else f"Side {winner}"
            return f"{won} wins the round: +{points}{label}   match: {_score(mode, mp, me)}"
        case MatchEnded(winner=winner, points=points):
            won = "Your side wins" if winner == side_of(me) else f"Side {winner} wins"
            return f"\n*** {won} the match {_score(mode, points, me)} ***"


def _label(action: Action, state: MatchState) -> str:
    match action:
        case ChooseTrump(suit=suit):
            return f"{SUIT_SYMBOLS[suit]} {SUIT_NAMES[suit]}"
        case Discard(cards=cards):
            return fmt_cards(cards)
        case DrawDecision(keep=keep):
            shown = fmt(state.round.stock[0])
            if keep:
                return f"keep {shown} (the next card goes to your discards)"
            return f"discard {shown} (you keep the next card)"
        case PlayCard(card=card):
            return fmt(card)
        case NextRound():
            return "next round"


def _status(state: MatchState, me: Seat) -> str:
    r, mode = state.round, state.mode
    trump = f"{SUIT_SYMBOLS[r.trump]} {SUIT_NAMES[r.trump]}" if r.trump else "not chosen"
    lines = [
        f"\nRound {r.number} · hakem {_who(r.hakem, me)} · trump {trump}",
        f"tricks: {_score(mode, r.tricks_won, me)}   match: {_score(mode, state.points, me)}",
        f"your hand: {fmt_hand(state.hand(me))}",
    ]
    if mode == "2p" and state.discards(me):
        lines.append(f"your discards: {fmt_cards(state.discards(me))}")
    if state.phase is Phase.DRAW:
        lines.append(f"draw turn · stock {len(r.stock)} · you are shown {fmt(r.stock[0])}")
    if r.trick is not None:
        played = "  ".join(f"{_who(p.seat, me)}:{fmt(p.card)}" for p in r.trick.plays)
        lines.append(f"trick {r.trick.number}: {played or '(you lead)'}")
    return "\n".join(lines)


def _ask(state: MatchState, me: Seat, read: Reader, write: Writer) -> Action:
    options = legal_actions(state, me)
    write(_status(state, me))
    for i, action in enumerate(options, 1):
        write(f"  {i:>2}) {_label(action, state)}")
    while True:
        try:
            answer = read(f"{state.phase.value}> ").strip().lower()
        except EOFError:
            raise Quit from None
        if answer in ("q", "quit"):
            raise Quit
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        write(f"  type a number from 1 to {len(options)}, or q to quit")


def play(
    config: MatchConfig,
    me: Seat,
    opponents: random.Random,
    read: Reader | None = None,
    write: Writer = print,
) -> MatchState:
    """Play one match in the terminal; returns the final state."""
    read = read or (lambda prompt: input(prompt))  # looked up at call time, so tests can patch
    state, events = new_match(config)
    while True:
        for event in events:
            line = describe(event, me, config.mode)
            if line is not None:
                write(line)
        if state.phase is Phase.MATCH_END:
            return state
        if state.phase is Phase.ROUND_END:
            action: Action = NextRound()
        elif state.round.to_act == me:
            action = _ask(state, me, read, write)
        else:
            seat = state.round.to_act
            assert seat is not None
            action = opponents.choice(legal_actions(state, seat))
        state, events = apply(state, action)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hokm", description="Play Hokm in the terminal.")
    parser.add_argument("--mode", choices=("2p", "4p"), default="2p")
    parser.add_argument("--target", type=int, choices=(1, 3, 5, 7), default=3)
    parser.add_argument("--seed", type=int, default=None, help="match seed (default: random)")
    parser.add_argument("--seat", default=None, help="your seat (default: A in 2p, S in 4p)")
    args = parser.parse_args(argv)

    mode: Mode = args.mode
    seed: int = args.seed if args.seed is not None else secrets.randbelow(1_000_000)
    wanted: str = args.seat or seats(mode)[0]
    by_name: dict[str, Seat] = {s: s for s in seats(mode)}
    me = by_name.get(wanted)
    if me is None:
        parser.error(f"--seat must be one of {', '.join(seats(mode))} in {mode}")
    config = MatchConfig.new(mode, args.target, seed)
    print(f"seed {seed} (replay this match with --seed {seed})")
    try:
        play(config, me, random.Random(f"terminal-opponents:{seed}"))
    except Quit:
        print("\nbye")
    return 0
