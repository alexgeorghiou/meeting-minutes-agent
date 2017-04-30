"""A deterministic transcriber for tests and local demos."""

from __future__ import annotations

from pathlib import Path

from minutes_agent.transcription.base import Transcript, TranscriptionError

SAMPLE_TRANSCRIPT = """\
Priya: Okay, let's get started. Thanks everyone for joining the release planning sync.
Marco: Um, so the main thing is the 2.4 release. QA found two blockers in the export flow.
Priya: Right. We decided to push the release to next Wednesday so QA has time to retest.
Lena: I can take the export bug. I will fix the CSV encoding issue by Friday.
Marco: Uh, I'll update the release notes and the changelog by Monday.
Priya: We agreed to drop the legacy theme from this release because nobody uses it.
Lena: Someone needs to email the beta customers about the new date.
Priya: Marco, can you send that email tomorrow?
Marco: Sure, I will email the beta customers tomorrow.
Priya: Great. Let's wrap up.
"""


class FakeTranscriber:
    """Returns a fixed transcript, or the file's text when the upload is a ``.txt`` file.

    Reading ``.txt`` uploads makes it trivial to drive the full pipeline end to end
    without any audio or network access.
    """

    name = "fake"

    def __init__(self, transcript: str = SAMPLE_TRANSCRIPT) -> None:
        self._transcript = transcript
        self.calls: list[Path] = []

    def transcribe(self, audio_path: Path, *, language: str | None = None) -> Transcript:
        self.calls.append(audio_path)
        if not audio_path.exists():
            raise TranscriptionError(f"audio file not found: {audio_path}")
        if audio_path.suffix.lower() == ".txt":
            text = audio_path.read_text(encoding="utf-8")
        else:
            text = self._transcript
        return Transcript(text=text, language=language or "en")
