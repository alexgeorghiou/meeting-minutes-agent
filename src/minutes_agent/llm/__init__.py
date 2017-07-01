"""LLM abstraction: a fake for tests, LangChain-backed providers for real use."""

from __future__ import annotations

from minutes_agent.config import Settings
from minutes_agent.llm.base import LLMError, StructuredLLM
from minutes_agent.llm.fake import FakeLLM

__all__ = ["FakeLLM", "LLMError", "StructuredLLM", "build_llm"]


def build_llm(settings: Settings) -> StructuredLLM:
    """Construct the provider selected by ``MINUTES_LLM_PROVIDER``."""
    if settings.llm_provider == "anthropic":
        from minutes_agent.llm.langchain_provider import build_anthropic

        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        return build_anthropic(settings.llm_model, key, settings.llm_temperature)
    if settings.llm_provider == "openai":
        from minutes_agent.llm.langchain_provider import build_openai

        key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        return build_openai(settings.llm_model, key, settings.llm_temperature)
    return FakeLLM()
