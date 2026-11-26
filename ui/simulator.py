"""Helpers for composing a WhatsApp-like text transcript in the UI."""


def format_simulated_conversation(messages: list[dict[str, str]]) -> str:
    """Serialize simulated chat messages into the WhatsApp export format accepted by the API."""
    return "\n".join(
        f"{message['time']} - {message['author']}: {message['text']}"
        for message in messages
    )
