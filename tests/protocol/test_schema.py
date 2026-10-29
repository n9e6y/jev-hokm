import json

from hokm.protocol.schema import client_schema, server_schema

FORBIDDEN = {"seed", "forget_seed", "stock", "all_hands", "truth"}


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


def test_no_server_message_has_a_secret_field():
    assert not property_names(server_schema()) & FORBIDDEN


def test_discriminators_for_the_ts_generator():
    server, client = server_schema(), client_schema()
    assert server["discriminator"]["propertyName"] == "type"
    assert client["discriminator"]["propertyName"] == "intent"
    assert len(client["oneOf"]) == 5
    assert json.loads(json.dumps(server)) == server  # plain JSON
    assert json.loads(json.dumps(client)) == client
