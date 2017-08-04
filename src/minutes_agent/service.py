"""Orchestrates transcription + pipeline for a job and records progress."""

from __future__ import annotations

import logging
from pathlib import Path

from minutes_agent.jobs import JobStatus, JobStore
from minutes_agent.models import Minutes
from minutes_agent.pipeline.graph import NODES, MinutesPipeline
from minutes_agent.transcription.base import Transcriber

logger = logging.getLogger(__name__)

# Transcription is the slow part for real audio, so it owns the first 40%.
TRANSCRIPTION_SHARE = 0.4
_NODE_PROGRESS = {
    node: TRANSCRIPTION_SHARE + (1 - TRANSCRIPTION_SHARE) * (i + 1) / len(NODES)
    for i, node in enumerate(NODES)
}


class MinutesService:
    def __init__(
        self, *, transcriber: Transcriber, pipeline: MinutesPipeline, store: JobStore
    ) -> None:
        self.transcriber = transcriber
        self.pipeline = pipeline
        self.store = store

    def process_audio(self, job_id: str, audio_path: Path, *, cleanup: bool = True) -> None:
        """Transcribe ``audio_path`` and then run the pipeline. Never raises."""
        try:
            self.store.update(
                job_id, status=JobStatus.TRANSCRIBING, stage="transcribe", progress=0.05
            )
            job = self.store.get(job_id)
            transcript = self.transcriber.transcribe(audio_path)
            self.store.update(job_id, transcript=transcript.text, progress=TRANSCRIPTION_SHARE)
            logger.info(
                "job %s transcribed %s (%d chars)", job_id, job.source, len(transcript.text)
            )
        except Exception as exc:
            self._fail(job_id, exc)
            return
        finally:
            if cleanup:
                audio_path.unlink(missing_ok=True)
        self.process_transcript(job_id, transcript.text)

    def process_transcript(self, job_id: str, transcript: str) -> None:
        """Run the minutes graph over ``transcript``. Never raises."""
        try:
            job = self.store.update(
                job_id,
                status=JobStatus.PROCESSING,
                transcript=transcript,
                progress=max(TRANSCRIPTION_SHARE, self.store.get(job_id).progress),
            )
            minutes: Minutes | None = None
            for node, delta in self.pipeline.stream(
                transcript,
                title=job.title,
                meeting_date=job.meeting_date,
                attendees=job.attendees,
            ):
                self.store.update(job_id, stage=node, progress=_NODE_PROGRESS.get(node, 0.9))
                if "minutes" in delta:
                    minutes = delta["minutes"]
            if minutes is None:
                raise RuntimeError("pipeline finished without producing minutes")
            self.store.update(
                job_id, status=JobStatus.COMPLETED, stage="done", progress=1.0, minutes=minutes
            )
        except Exception as exc:
            self._fail(job_id, exc)

    def _fail(self, job_id: str, exc: Exception) -> None:
        logger.exception("job %s failed", job_id)
        self.store.update(job_id, status=JobStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
