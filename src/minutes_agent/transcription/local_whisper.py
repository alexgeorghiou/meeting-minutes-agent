"""Offline transcription with faster-whisper (install the ``local`` extra)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from minutes_agent.transcription.base import Transcript, TranscriptionError, TranscriptSegment


class FasterWhisperTranscriber:
    """Runs a CTranslate2 Whisper model in-process.

    The model is loaded lazily on first use so that importing the module (and
    starting the API) stays cheap even when the extra is installed.
    """

    name = "local"

    def __init__(
        self, model_size: str = "small", *, device: str = "auto", compute_type: str = "default"
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover - depends on optional extra
                raise TranscriptionError(
                    "faster-whisper is not installed; run `pip install meeting-minutes-agent[local]`"
                ) from exc
            self._model = WhisperModel(
                self._model_size, device=self._device, compute_type=self._compute_type
            )
        return self._model

    def transcribe(self, audio_path: Path, *, language: str | None = None) -> Transcript:
        if not audio_path.exists():
            raise TranscriptionError(f"audio file not found: {audio_path}")
        model = self._load()
        raw_segments, info = model.transcribe(str(audio_path), language=language, vad_filter=True)
        segments = [
            TranscriptSegment(start=seg.start, end=seg.end, text=seg.text.strip())
            for seg in raw_segments
        ]
        return Transcript(
            text=" ".join(seg.text for seg in segments),
            language=getattr(info, "language", language),
            duration=getattr(info, "duration", None),
            segments=segments,
        )
