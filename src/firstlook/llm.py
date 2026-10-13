"""The chat model behind the agent."""

import os

# Checked against Groq's model list on 2026-10-13. Override with --model.
DEFAULT_MODEL = "groq:openai/gpt-oss-120b"


def make_model(spec: str = DEFAULT_MODEL):
    """A LangChain chat model from "groq:<model id>". Needs GROQ_API_KEY."""
    provider, _, model = spec.partition(":")
    if provider != "groq" or not model:
        raise ValueError(f"unknown model {spec!r}: use groq:<model id>, or rules for no model")
    if not os.environ.get("GROQ_API_KEY"):
        raise ValueError("GROQ_API_KEY is not set (or use --model rules for the no-model baseline)")
    from langchain_groq import ChatGroq

    return ChatGroq(model=model, temperature=0, max_retries=2)
