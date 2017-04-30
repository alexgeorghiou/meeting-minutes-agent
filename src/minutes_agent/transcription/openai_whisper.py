"""OpenAI Whisper API transcriber (``/v1/audio/transcriptions``)."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

import httpx

from minutes_agent.transcription.base import Transcript, TranscriptionError, TranscriptSegment

# The hosted API rejects uploads above 25 MB.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class OpenAIWhisperTranscriber:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "whisper-1",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 300.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def transcribe(self, audio_path: Path, *, language: str | None = None) -> Transcript:
        if not audio_path.exists():
            raise TranscriptionError(f"audio file not found: {audio_path}")
        size = audio_path.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            raise TranscriptionError(
                f"{audio_path.name} is {size / 1_048_576:.1f} MB; the Whisper API accepts 25 MB max"
            )

        content_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
        data: dict[str, str] = {"model": self._model, "response_format": "verbose_json"}
        if language:
            data["language"] = language

        with audio_path.open("rb") as fh:
            try:
                response = self._client.post(
                    "/audio/transcriptions",
                    headers=self._headers,
                    data=data,
                    files={"file": (audio_path.name, fh, content_type)},
                )
            except httpx.HTTPError as exc:
                raise TranscriptionError(f"whisper request failed: {exc}") from exc

        if response.status_code >= 400:
            raise TranscriptionError(
                f"whisper API returned {response.status_code}: {_error_message(response)}"
            )
        return _parse_verbose_json(response.json())


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("message", error))
    return str(body)[:200]


def _parse_verbose_json(payload: dict[str, Any]) -> Transcript:
    segments = [
        TranscriptSegment(
            start=float(seg.get("start", 0.0)),
            end=float(seg.get("end", 0.0)),
            text=str(seg.get("text", "")).strip(),
        )
        for seg in payload.get("segments") or []
    ]
    return Transcript(
        text=str(payload.get("text", "")).strip(),
        language=payload.get("language"),
        duration=payload.get("duration"),
        segments=segments,
    )
