"""Real providers via LangChain chat models (Anthropic or OpenAI)."""

from __future__ import annotations

from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from minutes_agent.llm.base import LLMError, T

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
}


class LangChainLLM:
    """Adapts any LangChain chat model that supports ``with_structured_output``."""

    def __init__(self, chat_model: Any, *, name: str, retries: int = 1) -> None:
        self._model = chat_model
        self._retries = retries
        self.name = name

    def invoke_structured(self, schema: type[T], *, system: str, prompt: str) -> T:
        runnable = self._model.with_structured_output(schema)
        messages = [SystemMessage(content=system), HumanMessage(content=prompt)]
        last_error: Exception | None = None
        for _ in range(self._retries + 1):
            try:
                result = runnable.invoke(messages)
            except ValidationError as exc:
                last_error = exc
                continue
            except Exception as exc:  # provider/network errors surface uniformly
                raise LLMError(f"{self.name} request failed: {exc}") from exc
            if isinstance(result, schema):
                return result
            if isinstance(result, dict):
                try:
                    return cast(T, schema.model_validate(result))
                except ValidationError as exc:
                    last_error = exc
                    continue
            last_error = LLMError(f"unexpected structured output type {type(result).__name__}")
        raise LLMError(f"{self.name} returned invalid {schema.__name__}: {last_error}")


def build_anthropic(model: str | None, api_key: str | None, temperature: float) -> LangChainLLM:
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:  # pragma: no cover - optional extra
        raise LLMError("MINUTES_LLM_PROVIDER=anthropic needs the 'anthropic' extra") from exc

    kwargs: dict[str, Any] = {
        "model": model or DEFAULT_MODELS["anthropic"],
        "temperature": temperature,
        "max_tokens": 4096,
    }
    if api_key:
        kwargs["api_key"] = api_key
    return LangChainLLM(ChatAnthropic(**kwargs), name=f"anthropic:{kwargs['model']}")


def build_openai(model: str | None, api_key: str | None, temperature: float) -> LangChainLLM:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - optional extra
        raise LLMError("MINUTES_LLM_PROVIDER=openai needs the 'openai' extra") from exc

    kwargs: dict[str, Any] = {
        "model": model or DEFAULT_MODELS["openai"],
        "temperature": temperature,
    }
    if api_key:
        kwargs["api_key"] = api_key
    return LangChainLLM(ChatOpenAI(**kwargs), name=f"openai:{kwargs['model']}")
