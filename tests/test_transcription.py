from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from minutes_agent.config import Settings
from minutes_agent.transcription import FakeTranscriber, TranscriptionError, build_transcriber
from minutes_agent.transcription.openai_whisper import OpenAIWhisperTranscriber


@pytest.fixture
def audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "standup.mp3"
    path.write_bytes(b"ID3fake-audio-bytes")
    return path


def _client(handler) -> httpx.Client:
    return httpx.Client(base_url="https://api.test/v1", transport=httpx.MockTransport(handler))


def test_whisper_posts_multipart_and_parses_segments(audio_file: Path) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={
                "text": " Hello team. ",
                "language": "english",
                "duration": 4.2,
                "segments": [
                    {"start": 0.0, "end": 1.5, "text": " Hello"},
                    {"start": 1.5, "end": 4.2, "text": " team."},
                ],
            },
        )

    transcriber = OpenAIWhisperTranscriber("sk-test", client=_client(handler))
    transcript = transcriber.transcribe(audio_file, language="en")

    assert seen["path"] == "/v1/audio/transcriptions"
    assert seen["auth"] == "Bearer sk-test"
    body = seen["body"]
    assert isinstance(body, bytes)
    assert b'name="model"' in body
    assert b"verbose_json" in body
    assert b'filename="standup.mp3"' in body
    assert transcript.text == "Hello team."
    assert [s.text for s in transcript.segments] == ["Hello", "team."]
    assert transcript.duration == pytest.approx(4.2)


def test_whisper_surfaces_api_errors(audio_file: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    transcriber = OpenAIWhisperTranscriber("bad", client=_client(handler))
    with pytest.raises(TranscriptionError, match="401: Invalid API key"):
        transcriber.transcribe(audio_file)


def test_whisper_rejects_oversized_files(tmp_path: Path) -> None:
    big = tmp_path / "long.wav"
    with big.open("wb") as fh:
        fh.seek(26 * 1024 * 1024)
        fh.write(b"\0")

    transcriber = OpenAIWhisperTranscriber("sk", client=_client(lambda r: httpx.Response(500)))
    with pytest.raises(TranscriptionError, match="25 MB"):
        transcriber.transcribe(big)


def test_fake_transcriber_reads_text_uploads(tmp_path: Path) -> None:
    notes = tmp_path / "meeting.txt"
    notes.write_text("Ana: We decided to ship.", encoding="utf-8")

    transcript = FakeTranscriber().transcribe(notes)

    assert transcript.text == "Ana: We decided to ship."


def test_fake_transcriber_missing_file(tmp_path: Path) -> None:
    with pytest.raises(TranscriptionError):
        FakeTranscriber().transcribe(tmp_path / "nope.wav")


def test_factory_requires_key_for_openai() -> None:
    with pytest.raises(TranscriptionError, match="OPENAI_API_KEY"):
        build_transcriber(Settings(transcriber="openai", openai_api_key=None))


def test_factory_defaults_to_fake() -> None:
    assert build_transcriber(Settings()).name == "fake"
