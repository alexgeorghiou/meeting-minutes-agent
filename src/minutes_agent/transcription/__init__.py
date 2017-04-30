"""Speech-to-text backends."""

from __future__ import annotations

from minutes_agent.config import Settings
from minutes_agent.transcription.base import (
    Transcriber,
    Transcript,
    TranscriptionError,
    TranscriptSegment,
)
from minutes_agent.transcription.fake import FakeTranscriber

__all__ = [
    "FakeTranscriber",
    "Transcriber",
    "Transcript",
    "TranscriptSegment",
    "TranscriptionError",
    "build_transcriber",
]


def build_transcriber(settings: Settings) -> Transcriber:
    """Construct the transcriber selected by ``MINUTES_TRANSCRIBER``."""
    if settings.transcriber == "openai":
        from minutes_agent.transcription.openai_whisper import OpenAIWhisperTranscriber

        if settings.openai_api_key is None:
            raise TranscriptionError("MINUTES_OPENAI_API_KEY is required for the openai backend")
        return OpenAIWhisperTranscriber(
            api_key=settings.openai_api_key.get_secret_value(), model=settings.whisper_model
        )
    if settings.transcriber == "local":
        from minutes_agent.transcription.local_whisper import FasterWhisperTranscriber

        return FasterWhisperTranscriber(
            model_size=settings.local_whisper_model, device=settings.local_whisper_device
        )
    return FakeTranscriber()
