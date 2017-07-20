from __future__ import annotations

import base64
import json
from collections.abc import Callable

import httpx
import pytest

from minutes_agent.config import Settings
from minutes_agent.exporters import (
    ExportError,
    GitHubIssuesExporter,
    JiraExporter,
    MarkdownExporter,
    build_exporters,
)
from minutes_agent.models import Minutes

Handler = Callable[[httpx.Request], httpx.Response]


def _client(base_url: str, handler: Handler) -> httpx.Client:
    return httpx.Client(base_url=base_url, transport=httpx.MockTransport(handler))


# --- markdown ---------------------------------------------------------------


def test_markdown_contains_all_sections(minutes: Minutes) -> None:
    result = MarkdownExporter().export(minutes)
    md = result.content or ""

    assert result.content_type == "text/markdown"
    assert md.startswith("# Release sync\n")
    assert "**Date:** Wednesday 18 November 2026" in md
    assert "1. **Push the release to next Wednesday** (Priya)" in md
    assert "   - _Why:_ QA needs time to retest" in md
    assert "| [ ] | Fix the CSV encoding issue | Lena | Fri 20 Nov 2026 | high |" in md
    assert "Book a room for the retro \\| big one | Unassigned | - |" in md
    assert "| [x] | Update the changelog | Marco |" in md
    assert "## Needs review" in md


def test_markdown_handles_empty_minutes(minutes: Minutes) -> None:
    empty = minutes.model_copy(update={"decisions": [], "action_items": [], "review_notes": []})
    md = MarkdownExporter().export(empty).content or ""
    assert "_No decisions recorded._" in md
    assert "_No action items._" in md
    assert "Needs review" not in md


# --- github -----------------------------------------------------------------


def test_github_creates_issue_per_open_item(minutes: Minutes) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        n = len(requests)
        return httpx.Response(
            201, json={"number": 40 + n, "html_url": f"https://github.com/acme/app/issues/{40 + n}"}
        )

    exporter = GitHubIssuesExporter(
        token="ghp_test",
        repo="acme/app",
        labels=["action-item"],
        assignees={"Lena": "lena-dev"},
        client=_client("https://api.github.com", handler),
    )
    result = exporter.export(minutes)

    assert [i.key for i in result.issues] == ["#41", "#42"]
    assert result.skipped == ["a3"]
    first = requests[0]
    assert first.url.path == "/repos/acme/app/issues"
    assert first.headers["authorization"] == "Bearer ghp_test"
    assert first.headers["x-github-api-version"] == "2022-11-28"
    body = json.loads(first.content)
    assert body["title"] == "Fix the CSV encoding issue"
    assert body["labels"] == ["action-item"]
    assert body["assignees"] == ["lena-dev"]
    assert "**Due:** 2026-11-20" in body["body"]
    assert "Push the release to next Wednesday" in body["body"]
    assert "assignees" not in json.loads(requests[1].content)


def test_github_error_is_reported(minutes: Minutes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    exporter = GitHubIssuesExporter(
        token="t", repo="acme/missing", client=_client("https://api.github.com", handler)
    )
    with pytest.raises(ExportError, match="HTTP 404: Not Found"):
        exporter.export(minutes)


def test_github_validates_repo_name() -> None:
    with pytest.raises(ValueError, match="owner/name"):
        GitHubIssuesExporter(token="t", repo="just-a-name")


# --- jira -------------------------------------------------------------------


def test_jira_posts_adf_description_and_due_date(minutes: Minutes) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "1000", "key": f"REL-{len(requests)}"})

    exporter = JiraExporter(
        base_url="https://acme.atlassian.net/",
        email="bot@acme.test",
        api_token="jira-token",
        project_key="REL",
        account_ids={"Lena": "5b10ac8d82e05b22cc7d4ef5"},
        client=_client("https://acme.atlassian.net", handler),
    )
    result = exporter.export(minutes)

    assert [(i.key, i.url) for i in result.issues] == [
        ("REL-1", "https://acme.atlassian.net/browse/REL-1"),
        ("REL-2", "https://acme.atlassian.net/browse/REL-2"),
    ]
    request = requests[0]
    assert request.url.path == "/rest/api/3/issue"
    expected_auth = base64.b64encode(b"bot@acme.test:jira-token").decode()
    assert request.headers["authorization"] == f"Basic {expected_auth}"

    fields = json.loads(request.content)["fields"]
    assert fields["project"] == {"key": "REL"}
    assert fields["issuetype"] == {"name": "Task"}
    assert fields["duedate"] == "2026-11-20"
    assert fields["assignee"] == {"id": "5b10ac8d82e05b22cc7d4ef5"}
    assert fields["labels"] == ["meeting-minutes"]

    description = fields["description"]
    assert description["type"] == "doc"
    assert description["version"] == 1
    assert description["content"][0] == {
        "type": "paragraph",
        "content": [{"type": "text", "text": "Fix the CSV encoding issue"}],
    }
    bullets = description["content"][1]
    assert bullets["type"] == "bulletList"
    owner_line = bullets["content"][1]["content"][0]["content"]
    assert owner_line[0] == {"type": "text", "text": "Owner: ", "marks": [{"type": "strong"}]}

    second = json.loads(requests[1].content)["fields"]
    assert "duedate" not in second
    assert "assignee" not in second


def test_jira_error_messages_are_surfaced(minutes: Minutes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"errorMessages": [], "errors": {"project": "valid project is required"}},
        )

    exporter = JiraExporter(
        base_url="https://acme.atlassian.net",
        email="e",
        api_token="t",
        project_key="NOPE",
        client=_client("https://acme.atlassian.net", handler),
    )
    with pytest.raises(ExportError, match="project: valid project is required"):
        exporter.export(minutes)


# --- registry ---------------------------------------------------------------


def test_build_exporters_only_enables_configured_targets() -> None:
    assert set(build_exporters(Settings())) == {"markdown"}

    settings = Settings(
        github_token="t",
        github_repo="acme/app",
        jira_base_url="https://acme.atlassian.net",
        jira_email="e@acme.test",
        jira_api_token="t",
        jira_project_key="REL",
    )
    assert set(build_exporters(settings)) == {"markdown", "github", "jira"}
