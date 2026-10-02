import os
from types import SimpleNamespace

from services.ai_service import AIService, build_system_prompt, generate_demo_response


def test_ai_service_has_demo_mode_fallback():
    response = generate_demo_response("I don't want to talk about it.", "talk", "message")
    assert "don't have to talk about it" in response.lower()


def test_builder_uses_mode_and_language_context():
    prompt = build_system_prompt("focus", "en")
    assert "SAATHI" in prompt
    assert "Focus" in prompt
    assert "English" in prompt


def test_service_uses_demo_when_no_api_key_is_configured(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "demo")
    monkeypatch.delenv("AI_API_KEY", raising=False)
    service = AIService()
    assert service.provider_name == "demo"
    assert service.is_demo_mode is True


def test_demo_reply_responds_to_the_user_topic():
    response = generate_demo_response("I'm exhausted after classes at college.", "talk")
    assert "college" in response.lower()
    assert "i'm listening" not in response.lower()


def test_provider_context_does_not_duplicate_current_message():
    current_message = "My final class ran late."
    conversation = SimpleNamespace(messages=[
        SimpleNamespace(sender="user", content="I had a long day."),
        SimpleNamespace(sender="saathi", content="What made it long?"),
        SimpleNamespace(sender="user", content=current_message),
    ])
    service = AIService()

    payload = service._build_payload(current_message, conversation, "talk", "message")
    user_contents = [message["content"] for message in payload if message["role"] == "user"]

    assert user_contents.count(current_message) == 1
    assert "I had a long day." in user_contents
