"""Provider-agnostic LLM interface used by the pipeline."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised when a provider cannot produce a valid structured response."""


@runtime_checkable
class StructuredLLM(Protocol):
    """A chat model that returns validated Pydantic objects."""

    name: str

    def invoke_structured(self, schema: type[T], *, system: str, prompt: str) -> T: ...
