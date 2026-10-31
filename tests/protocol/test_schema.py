import json

from hokm.protocol.schema import client_schema, observer_schema, player_schema

# Substrings, so variants such as `truth_snapshots`, `all_hands` or `stock_order` are caught too.
SECRET_PARTS = ("seed", "stock", "hand", "deck", "truth", "rng")
# The seat's own hand (SEAT_VIEW.md) and `stock_left`, a count every seat sees (R5.4).
ALLOWED = {"hand", "stock_left"}


def property_names(node) -> set[str]:
    names: set[str] = set()
    if isinstance(node, dict):
        names |= set(node.get("properties", {}))
        for value in node.values():
            names |= property_names(value)
    elif isinstance(node, list):
        for value in node:
            names |= property_names(value)
    return names


def secret_names(schema) -> set[str]:
    names = property_names(schema) - ALLOWED
    return {n for n in names if any(part in n for part in SECRET_PARTS)}


def test_no_server_message_has_a_secret_field():
    assert not secret_names(player_schema())
    assert not secret_names(observer_schema())


def test_bot_events_are_observer_only():
    player = json.dumps(player_schema())
    observer = json.dumps(observer_schema())
    for name in ("BotDecision", "BotPaused"):
        assert name not in player
        assert name in observer


def test_discriminators_for_the_ts_generator():
    player, observer, client = player_schema(), observer_schema(), client_schema()
    assert player["discriminator"]["propertyName"] == "type"
    assert observer["discriminator"]["propertyName"] == "type"
    assert client["discriminator"]["propertyName"] == "intent"
    assert len(client["oneOf"]) == 4  # request_hint arrives in 5.4
    for schema in (player, observer, client):
        assert json.loads(json.dumps(schema)) == schema  # plain JSON
