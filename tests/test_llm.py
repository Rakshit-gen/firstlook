import pytest

from firstlook.llm import DEFAULT_MODEL, make_model


def test_needs_a_key_and_a_known_provider(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        make_model()
    with pytest.raises(ValueError, match="unknown model"):
        make_model("openai:gpt-5")


def test_builds_a_groq_client_without_calling_it(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-used")
    model = make_model()
    assert model.model_name == DEFAULT_MODEL.split(":", 1)[1]
    assert model.temperature < 1e-6  # langchain-groq turns 0 into 1e-8
