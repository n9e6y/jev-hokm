"""Shared engine test helpers.

States are only ever produced by the real engine; `play_state` then rigs hands with
`dataclasses.replace` to set up a specific trick. The engine itself is never mocked.
"""

import random
from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace

from hokm.engine.actions import Action, ChooseTrump, Discard, DrawDecision, NextRound, PlayCard
from hokm.engine.cards import Card, Suit, parse_cards
from hokm.engine.errors import EngineError
from hokm.engine.events import Event
from hokm.engine.rules import apply, legal_actions, new_match
from hokm.engine.state import MatchState, Phase, Trick, sorted_cards
from hokm.engine.variants import MatchConfig, Mode, Seat, seats

type Chooser = Callable[[tuple[Action, ...]], Action]


def first(options: tuple[Action, ...]) -> Action:
    return options[0]


def start(mode: Mode, seed: int = 1, target: int = 7) -> MatchState:
    state, _ = new_match(MatchConfig.new(mode, target, seed))
    return state


def advance(
    state: MatchState,
    until: Callable[[MatchState], bool],
    choose: Chooser = first,
) -> tuple[MatchState, list[Event]]:
    """Apply legal actions for whoever is to act until `until(state)` holds.

    Between rounds it sends `NextRound`, as the server will.
    """
    events: list[Event] = []
    while not until(state):
        state, new = apply(state, next_action(state, choose))
        events.extend(new)
    return state, events


def next_action(state: MatchState, choose: Chooser = first) -> Action:
    if state.phase is Phase.ROUND_END:
        return NextRound()
    seat = state.round.to_act
    assert seat is not None
    return choose(legal_actions(state, seat))


@dataclass(frozen=True)
class RecordedMatch:
    config: MatchConfig
    actions: tuple[Action, ...]
    states: tuple[MatchState, ...]  # states[0] is the new match
    events: tuple[Event, ...]


def random_match(mode: Mode, seed: int, target: int = 3) -> RecordedMatch:
    """Play a whole match with seeded random legal actions, recording everything."""
    config = MatchConfig.new(mode, target, seed)
    rng = random.Random(f"test-playout:{seed}")
    state, events = new_match(config)
    actions: list[Action] = []
    states = [state]
    all_events = list(events)
    while state.phase is not Phase.MATCH_END:
        action = next_action(state, rng.choice)
        state, events = apply(state, action)
        actions.append(action)
        states.append(state)
        all_events.extend(events)
    return RecordedMatch(config, tuple(actions), tuple(states), tuple(all_events))


def in_phase(phase: Phase) -> Callable[[MatchState], bool]:
    return lambda s: s.phase is phase


def play_state(
    mode: Mode,
    hands: dict[Seat, str],
    *,
    trump: Suit = Suit.HEARTS,
    leader: Seat | None = None,
    hakem: Seat | None = None,
    tricks_won: tuple[int, int] = (0, 0),
    points: tuple[int, int] = (0, 0),
    target: int = 7,
) -> MatchState:
    """A play-phase state with rigged hands, trick counts and match points.

    Card conservation is not kept; use it only for trick and scoring rules.
    """
    state = start(mode, target=target)
    hakem = hakem or state.round.hakem
    lead = leader or hakem
    round_ = replace(
        state.round,
        hakem=hakem,
        hands=tuple(sorted_cards(parse_cards(hands[s])) for s in seats(mode)),
        stock=(),
        trump=trump,
        tricks_won=tricks_won,
        to_act=lead,
        trick=Trick(sum(tricks_won) + 1, lead),
    )
    return replace(state, phase=Phase.PLAY, round=round_, points=points)


# --- invariants (1.14) ---------------------------------------------------------------------


def played_cards(state: MatchState) -> list[Card]:
    r = state.round
    plays = [p for t in r.tricks for p in t.plays]
    if r.trick is not None:
        plays.extend(r.trick.plays)
    return [p.card for p in plays]


def check_invariants(state: MatchState) -> None:
    """Assert everything that must hold after every action, in every phase."""
    r, mode, config = state.round, state.mode, state.config
    # card conservation: hands + played + discards + stock == the match deck, no duplicates
    every = [c for h in r.hands for c in h]
    every += played_cards(state) + [c for d in r.discards for c in d] + list(r.stock)
    assert Counter(every) == Counter(config.deck), "cards are not conserved"

    # tricks: counts match the history, nobody passes 7, and 7 means the round is over (R8.1)
    assert sum(r.tricks_won) == len(r.tricks)
    assert all(t.winner is not None and len(t.plays) == len(seats(mode)) for t in r.tricks)
    assert max(r.tricks_won) <= 7
    over = state.phase in (Phase.ROUND_END, Phase.MATCH_END)
    assert (max(r.tricks_won) == 7) == over

    # turn: someone acts in every live phase, nobody between rounds
    assert (r.to_act is None) == over
    assert (r.trick is not None) == (state.phase is Phase.PLAY)

    # hand sizes (R4, R5): 13 cards per seat once play starts, minus what each seat played
    if state.phase is Phase.PLAY or over:
        played_by = Counter(p.seat for t in r.tricks for p in t.plays)
        if r.trick is not None:
            played_by.update(p.seat for p in r.trick.plays)
        for seat in seats(mode):
            assert len(state.hand(seat)) + played_by[seat] == 13
        assert r.stock == ()
    if mode == "2p" and state.phase is Phase.DRAW:
        assert len(r.stock) == 40 - 2 * r.draw_turns_done

    check_tricks_against_rules(state)

    # match score (R3.5, R8.2)
    assert sum(state.points) == sum(res.points for res in state.results)
    target = config.target_points
    if state.phase is Phase.MATCH_END:
        assert state.winner is not None and state.points_of(state.winner) >= target
    else:
        assert state.winner is None and max(state.points) < target


def check_tricks_against_rules(state: MatchState) -> None:
    """Re-check every trick of the round with code independent of the engine's rules."""
    r = state.round
    tricks = list(r.tricks) + ([r.trick] if r.trick is not None and r.trick.plays else [])
    expected_leader = r.hakem  # R7.1
    for i, trick in enumerate(tricks):
        assert trick.leader == expected_leader and trick.plays[0].seat == trick.leader  # R7.4
        led = trick.plays[0].card.suit
        for play in trick.plays[1:]:
            if play.card.suit != led:
                # R7.2 off-suit only when void: rebuild the hand the seat held at that moment
                later = [p.card for t in tricks[i:] for p in t.plays if p.seat == play.seat]
                held = [*state.hand(play.seat), *later]
                assert all(c.suit != led for c in held), f"{play.seat} revoked on {led}"
        if trick.winner is None:
            break
        trumps = [p for p in trick.plays if p.card.suit == r.trump]
        pool = trumps or [p for p in trick.plays if p.card.suit == led]
        best = pool[0]
        for p in pool[1:]:
            if p.card.rank > best.card.rank:
                best = p
        assert trick.winner == best.seat, "wrong trick winner"  # R7.3
        expected_leader = trick.winner


def _listed(state: MatchState, action: Action) -> bool:
    """Is `action` one of the listed legal actions? Discard order does not matter."""
    if isinstance(action, NextRound):
        return state.phase is Phase.ROUND_END
    options = legal_actions(state, action.seat)
    if isinstance(action, Discard):
        return len(set(action.cards)) == len(action.cards) and any(
            isinstance(o, Discard) and set(o.cards) == set(action.cards) for o in options
        )
    return action in options


def random_probe(state: MatchState, rng: random.Random) -> Action:
    """Any action at all, mostly illegal. Biased towards the seat to act and cards from its
    own hand, so near-misses (off-suit plays, wrong discard counts) come up often."""
    to_act = state.round.to_act
    seat = to_act if to_act is not None and rng.random() < 0.6 else rng.choice(seats(state.mode))
    hand = state.hand(seat)
    pool = hand if hand and rng.random() < 0.6 else state.config.deck
    kind = rng.randrange(5)
    if kind == 0:
        return ChooseTrump(seat, rng.choice(list(Suit)))
    if kind == 1:
        count = min(rng.choice((1, 2, 2, 3)), len(pool))
        return Discard(seat, tuple(rng.choices(pool, k=count)))  # may repeat a card
    if kind == 2:
        return DrawDecision(seat, rng.random() < 0.5)
    if kind == 3:
        return PlayCard(seat, rng.choice(pool))
    return NextRound()


def assert_accepts_exactly_legal(state: MatchState, action: Action) -> None:
    """The engine accepts `action` iff it is listed, and never changes the input state."""
    snapshot = deepcopy(state)
    try:
        apply(state, action)
        accepted = True
    except EngineError:
        accepted = False
    assert state == snapshot, "apply modified its input"
    assert accepted == _listed(state, action), f"{action} accepted={accepted}"
