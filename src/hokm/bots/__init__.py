"""Bots: they receive a seat view and return a choice; never engine state (docs/SEAT_VIEW.md)."""

from hokm.bots.base import Bot
from hokm.bots.random_bot import RandomBot
from hokm.bots.rule_bot import RuleBot

BOT_KINDS = ("random", "rule")


def make_bot(kind: str, seed: int | str) -> Bot:
    """A fresh bot of `kind`; `seed` feeds the bot's own RNG (ignored by deterministic bots)."""
    if kind == "random":
        return RandomBot(seed)
    if kind == "rule":
        return RuleBot()
    raise ValueError(f"unknown bot kind {kind!r}; choose from {', '.join(BOT_KINDS)}")


__all__ = ["BOT_KINDS", "Bot", "RandomBot", "RuleBot", "make_bot"]
