"""Job tracking for asynchronous minutes processing.

Two interchangeable stores: an in-memory one (default, great for dev/tests) and
a SQLite one that survives restarts. Jobs are stored as JSON documents, which
keeps the schema trivial while the Pydantic model evolves.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from minutes_agent.models import Minutes


class JobStatus(StrEnum):
    QUEUED = "queued"
    TRANSCRIBING = "transcribing"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def finished(self) -> bool:
        return self in {JobStatus.COMPLETED, JobStatus.FAILED}


def _now() -> datetime:
    return datetime.now(UTC)


class Job(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    status: JobStatus = JobStatus.QUEUED
    stage: str | None = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    title: str | None = None
    meeting_date: date | None = None
    attendees: list[str] = Field(default_factory=list)
    source: str = Field(description="Original filename, or 'transcript' for pasted text.")
    error: str | None = None
    transcript: str | None = None
    minutes: Minutes | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class JobNotFoundError(KeyError):
    pass


class JobStore(Protocol):
    def create(self, job: Job) -> Job: ...

    def get(self, job_id: str) -> Job: ...

    def update(self, job_id: str, **changes: Any) -> Job: ...

    def list(self, limit: int = 50) -> list[Job]: ...


def _apply(job: Job, changes: dict[str, Any]) -> Job:
    data = job.model_dump()
    data.update(changes)
    data["updated_at"] = _now()
    return Job.model_validate(data)


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, job: Job) -> Job:
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            try:
                return self._jobs[job_id].model_copy(deep=True)
            except KeyError:
                raise JobNotFoundError(job_id) from None

    def update(self, job_id: str, **changes: Any) -> Job:
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)
            updated = _apply(self._jobs[job_id], changes)
            self._jobs[job_id] = updated
            return updated.model_copy(deep=True)

    def list(self, limit: int = 50) -> list[Job]:
        with self._lock:
            # Newest insertion first; the stable sort keeps that order for equal timestamps.
            newest_first = list(self._jobs.values())[::-1]
            jobs = sorted(newest_first, key=lambda j: j.created_at, reverse=True)
            return [j.model_copy(deep=True) for j in jobs[:limit]]


class SqliteJobStore:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                       id TEXT PRIMARY KEY,
                       created_at TEXT NOT NULL,
                       data TEXT NOT NULL
                   )"""
            )

    def create(self, job: Job) -> Job:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO jobs (id, created_at, data) VALUES (?, ?, ?)",
                (job.id, job.created_at.isoformat(), job.model_dump_json()),
            )
        return job

    def _load(self, job_id: str) -> Job:
        row = self._conn.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise JobNotFoundError(job_id)
        return Job.model_validate_json(row[0])

    def get(self, job_id: str) -> Job:
        with self._lock:
            return self._load(job_id)

    def update(self, job_id: str, **changes: Any) -> Job:
        with self._lock, self._conn:
            updated = _apply(self._load(job_id), changes)
            self._conn.execute(
                "UPDATE jobs SET data = ? WHERE id = ?", (updated.model_dump_json(), job_id)
            )
            return updated

    def list(self, limit: int = 50) -> list[Job]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Job.model_validate_json(row[0]) for row in rows]

    def close(self) -> None:
        self._conn.close()
