from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from minutes_agent.api import create_app
from minutes_agent.config import Settings
from minutes_agent.exporters import GitHubIssuesExporter, MarkdownExporter
from minutes_agent.jobs import InMemoryJobStore
from minutes_agent.llm import FakeLLM
from minutes_agent.transcription import FakeTranscriber, Transcript, TranscriptionError
from minutes_agent.transcription.fake import SAMPLE_TRANSCRIPT


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(upload_dir=tmp_path / "uploads", max_upload_mb=1)


@pytest.fixture
def store() -> InMemoryJobStore:
    return InMemoryJobStore()


@pytest.fixture
def github_requests() -> list[httpx.Request]:
    return []


@pytest.fixture
def client(
    settings: Settings, store: InMemoryJobStore, github_requests: list[httpx.Request]
) -> TestClient:
    def handler(request: httpx.Request) -> httpx.Response:
        github_requests.append(request)
        n = len(github_requests)
        return httpx.Response(201, json={"number": n, "html_url": f"https://gh.test/issues/{n}"})

    github = GitHubIssuesExporter(
        token="t",
        repo="acme/app",
        client=httpx.Client(
            base_url="https://api.github.com", transport=httpx.MockTransport(handler)
        ),
    )
    app = create_app(
        settings,
        transcriber=FakeTranscriber(),
        llm=FakeLLM(),
        store=store,
        exporters={"markdown": MarkdownExporter(), "github": github},
    )
    return TestClient(app)


def _upload(client: TestClient, **form: str) -> dict:
    response = client.post(
        "/api/jobs",
        files={"file": ("release_sync.mp3", b"ID3-not-really-audio", "audio/mpeg")},
        data={"meeting_date": "2026-11-18", **form},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_health_reports_providers(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["llm"] == "fake"
    assert body["exporters"] == ["github", "markdown"]


def test_upload_runs_pipeline_in_background(client: TestClient, settings: Settings) -> None:
    job = _upload(client)

    # TestClient executes background tasks before returning the response.
    status = client.get(f"/api/jobs/{job['id']}").json()
    assert status["status"] == "completed"
    assert status["progress"] == 1.0
    assert status["has_minutes"] is True
    assert status["title"] == "Release Sync"
    assert list(settings.upload_dir.iterdir()) == []  # upload cleaned up

    minutes = client.get(f"/api/jobs/{job['id']}/minutes").json()
    assert minutes["meeting_date"] == "2026-11-18"
    assert len(minutes["decisions"]) == 2
    due = {i["description"]: i["due_date"] for i in minutes["action_items"]}
    assert due["Fix the CSV encoding issue"] == "2026-11-20"

    transcript = client.get(f"/api/jobs/{job['id']}/transcript")
    assert transcript.text.startswith("Priya:")


def test_upload_with_attendees_form_field(client: TestClient) -> None:
    job = _upload(client, attendees="Priya Natarajan, Marco Rossi; Lena Weber", title="Sync")
    minutes = client.get(f"/api/jobs/{job['id']}/minutes").json()
    assert minutes["title"] == "Sync"
    assert minutes["attendees"] == ["Priya Natarajan", "Marco Rossi", "Lena Weber"]


def test_rejects_unsupported_and_oversized_uploads(client: TestClient) -> None:
    bad_type = client.post("/api/jobs", files={"file": ("notes.pdf", b"%PDF", "application/pdf")})
    assert bad_type.status_code == 415

    too_big = client.post(
        "/api/jobs", files={"file": ("long.wav", b"\0" * (1024 * 1024 + 1), "audio/wav")}
    )
    assert too_big.status_code == 413


def test_transcript_endpoint(client: TestClient) -> None:
    response = client.post(
        "/api/jobs/transcript",
        json={"transcript": SAMPLE_TRANSCRIPT, "title": "Pasted", "meeting_date": "2026-11-18"},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"
    assert client.get("/api/jobs").json()[0]["id"] == job_id


def test_failed_transcription_marks_job_failed(settings: Settings, store: InMemoryJobStore) -> None:
    class BrokenTranscriber:
        name = "broken"

        def transcribe(self, audio_path: Path, *, language: str | None = None) -> Transcript:
            raise TranscriptionError("codec not supported")

    app = create_app(settings, transcriber=BrokenTranscriber(), llm=FakeLLM(), store=store)
    client = TestClient(app)
    job = _upload(client)

    status = client.get(f"/api/jobs/{job['id']}").json()
    assert status["status"] == "failed"
    assert "codec not supported" in status["error"]
    assert client.get(f"/api/jobs/{job['id']}/minutes").status_code == 409


def test_unknown_job_is_404(client: TestClient) -> None:
    assert client.get("/api/jobs/nope").status_code == 404


def test_edit_and_delete_action_items(client: TestClient) -> None:
    job_id = _upload(client)["id"]
    items = client.get(f"/api/jobs/{job_id}/minutes").json()["action_items"]
    retro = next(i for i in items if i["owner"] is None)

    patched = client.patch(
        f"/api/jobs/{job_id}/action-items/{retro['id']}",
        json={"owner": "Lena", "due_date": "2026-11-26", "priority": "high"},
    )
    assert patched.status_code == 200
    assert patched.json()["owner"] == "Lena"

    minutes = client.get(f"/api/jobs/{job_id}/minutes").json()
    stored = next(i for i in minutes["action_items"] if i["id"] == retro["id"])
    assert (stored["owner"], stored["due_date"], stored["priority"]) == (
        "Lena",
        "2026-11-26",
        "high",
    )

    assert client.patch(f"/api/jobs/{job_id}/action-items/x", json={}).status_code == 404
    bad = client.patch(f"/api/jobs/{job_id}/action-items/{retro['id']}", json={"description": ""})
    assert bad.status_code == 422

    assert client.delete(f"/api/jobs/{job_id}/action-items/{retro['id']}").status_code == 204
    remaining = client.get(f"/api/jobs/{job_id}/minutes").json()["action_items"]
    assert retro["id"] not in {i["id"] for i in remaining}


def test_replace_minutes(client: TestClient) -> None:
    job_id = _upload(client)["id"]
    minutes = client.get(f"/api/jobs/{job_id}/minutes").json()
    minutes["summary"] = "Edited by hand."

    assert client.put(f"/api/jobs/{job_id}/minutes", json=minutes).status_code == 200
    assert client.get(f"/api/jobs/{job_id}/minutes").json()["summary"] == "Edited by hand."


def test_markdown_download(client: TestClient) -> None:
    job_id = _upload(client)["id"]
    response = client.get(f"/api/jobs/{job_id}/minutes.md")
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert "## Action items" in response.text


def test_export_to_github_uses_edited_minutes(
    client: TestClient, github_requests: list[httpx.Request]
) -> None:
    job_id = _upload(client)["id"]
    items = client.get(f"/api/jobs/{job_id}/minutes").json()["action_items"]
    client.patch(f"/api/jobs/{job_id}/action-items/{items[0]['id']}", json={"done": True})

    response = client.post(f"/api/jobs/{job_id}/exports/github")

    assert response.status_code == 200
    body = response.json()
    assert body["skipped"] == [items[0]["id"]]
    assert len(body["issues"]) == len(items) - 1
    titles = [json.loads(r.content)["title"] for r in github_requests]
    assert items[0]["description"] not in titles


def test_export_unknown_target_and_not_ready(client: TestClient, store: InMemoryJobStore) -> None:
    job_id = _upload(client)["id"]
    assert client.post(f"/api/jobs/{job_id}/exports/jira").status_code == 404

    from minutes_agent.jobs import Job

    pending = store.create(Job(source="x.wav", meeting_date=date(2026, 11, 18)))
    assert client.post(f"/api/jobs/{pending.id}/exports/markdown").status_code == 409


def test_export_error_maps_to_502(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    github = GitHubIssuesExporter(
        token="bad",
        repo="acme/app",
        client=httpx.Client(
            base_url="https://api.github.com", transport=httpx.MockTransport(handler)
        ),
    )
    client = TestClient(
        create_app(
            settings, transcriber=FakeTranscriber(), llm=FakeLLM(), exporters={"github": github}
        )
    )
    job_id = _upload(client)["id"]

    response = client.post(f"/api/jobs/{job_id}/exports/github")
    assert response.status_code == 502
    assert "Bad credentials" in response.json()["detail"]
