from ai.parseur.whatsapp import parser_export
from ui.simulator import format_simulated_conversation


def test_simulator_formats_messages_as_parseable_whatsapp_export():
    messages = [
        {
            "time": "25/11/2026 10:02",
            "author": "Awa",
            "text": "Bonjour, je veux 2 robes Ayoka.",
        },
        {
            "time": "25/11/2026 10:05",
            "author": "Vendeuse",
            "text": "Bonjour Awa, c'est noté.",
        },
        {
            "time": "25/11/2026 16:40",
            "author": "Livreur",
            "text": "Une robe livrée.",
        },
    ]

    transcript = format_simulated_conversation(messages)
    parsed = parser_export(
        transcript,
        roles={"Vendeuse": "vendeuse", "Livreur": "livreur"},
    )

    assert [message["auteur"] for message in parsed] == ["Awa", "Vendeuse", "Livreur"]
    assert [message["role"] for message in parsed] == ["client", "vendeuse", "livreur"]
    assert [message["texte"] for message in parsed] == [message["text"] for message in messages]
