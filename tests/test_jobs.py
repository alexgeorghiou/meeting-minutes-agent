from __future__ import annotations

from pathlib import Path

import pytest

from minutes_agent.jobs import (
    InMemoryJobStore,
    Job,
    JobNotFoundError,
    JobStatus,
    JobStore,
    SqliteJobStore,
)
from minutes_agent.models import Minutes


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> JobStore:
    if request.param == "memory":
        return InMemoryJobStore()
    return SqliteJobStore(tmp_path / "jobs.sqlite3")


def test_create_get_update(store: JobStore, minutes: Minutes) -> None:
    job = store.create(Job(source="standup.mp3", attendees=["Ana"]))

    store.update(job.id, status=JobStatus.PROCESSING, stage="summarize", progress=0.5)
    done = store.update(job.id, status=JobStatus.COMPLETED, progress=1.0, minutes=minutes)

    fetched = store.get(job.id)
    assert fetched == done
    assert fetched.status.finished
    assert fetched.minutes is not None
    assert fetched.minutes.action_items[0].description == "Fix the CSV encoding issue"
    assert fetched.updated_at >= job.updated_at


def test_returned_jobs_are_copies(store: JobStore) -> None:
    job = store.create(Job(source="x.wav"))
    fetched = store.get(job.id)
    fetched.attendees.append("Mallory")
    assert store.get(job.id).attendees == []


def test_list_is_newest_first(store: JobStore) -> None:
    ids = [store.create(Job(source=f"{i}.wav")).id for i in range(3)]
    assert [j.id for j in store.list()] == list(reversed(ids))
    assert len(store.list(limit=2)) == 2


def test_missing_job_raises(store: JobStore) -> None:
    with pytest.raises(JobNotFoundError):
        store.get("missing")
    with pytest.raises(JobNotFoundError):
        store.update("missing", progress=1.0)


def test_invalid_update_is_rejected(store: JobStore) -> None:
    job = store.create(Job(source="x.wav"))
    with pytest.raises(ValueError, match="progress"):
        store.update(job.id, progress=2.0)


def test_sqlite_store_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "jobs.sqlite3"
    first = SqliteJobStore(path)
    job = first.create(Job(source="retro.m4a"))
    first.update(job.id, status=JobStatus.FAILED, error="boom")
    first.close()

    reopened = SqliteJobStore(path).get(job.id)
    assert reopened.status is JobStatus.FAILED
    assert reopened.error == "boom"
