"""Transcriber protocol and transcript types."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    start: float = Field(ge=0, description="Seconds from the start of the recording.")
    end: float = Field(ge=0)
    text: str
    speaker: str | None = None


class Transcript(BaseModel):
    text: str
    language: str | None = None
    duration: float | None = None
    segments: list[TranscriptSegment] = Field(default_factory=list)

    @classmethod
    def from_text(cls, text: str) -> Transcript:
        return cls(text=text)


class TranscriptionError(RuntimeError):
    """Raised when a backend fails to transcribe an audio file."""


@runtime_checkable
class Transcriber(Protocol):
    """Anything that can turn an audio file into a transcript."""

    name: str

    def transcribe(self, audio_path: Path, *, language: str | None = None) -> Transcript: ...
