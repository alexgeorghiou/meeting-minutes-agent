"""Create Jira Cloud issues via REST API v3 (descriptions use Atlassian Document Format)."""

from __future__ import annotations

from typing import Any

import httpx

from minutes_agent.exporters.base import (
    ExportedIssue,
    ExportError,
    ExportResult,
    describe_http_error,
    issue_title,
)
from minutes_agent.models import ActionItem, Minutes

# --- Atlassian Document Format helpers ---------------------------------------


def adf_text(text: str, *, bold: bool = False) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": text}
    if bold:
        node["marks"] = [{"type": "strong"}]
    return node


def adf_paragraph(*content: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "content": list(content)}


def adf_heading(text: str, level: int = 3) -> dict[str, Any]:
    return {"type": "heading", "attrs": {"level": level}, "content": [adf_text(text)]}


def adf_bullets(items: list[list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "type": "bulletList",
        "content": [{"type": "listItem", "content": [adf_paragraph(*item)]} for item in items],
    }


def adf_doc(*content: dict[str, Any]) -> dict[str, Any]:
    return {"type": "doc", "version": 1, "content": list(content)}


def action_item_description(item: ActionItem, minutes: Minutes) -> dict[str, Any]:
    facts: list[list[dict[str, Any]]] = [
        [
            adf_text("Meeting: ", bold=True),
            adf_text(f"{minutes.title} ({minutes.meeting_date.isoformat()})"),
        ],
        [adf_text("Owner: ", bold=True), adf_text(item.owner or "Unassigned")],
    ]
    if item.due_text:
        facts.append([adf_text("Due (as said): ", bold=True), adf_text(item.due_text)])
    blocks = [adf_paragraph(adf_text(item.description)), adf_bullets(facts)]
    if minutes.decisions:
        blocks.append(adf_heading("Decisions from this meeting"))
        blocks.append(adf_bullets([[adf_text(d.summary)] for d in minutes.decisions]))
    return adf_doc(*blocks)


# --- exporter ------------------------------------------------------------------


class JiraExporter:
    name = "jira"

    def __init__(
        self,
        *,
        base_url: str,
        email: str,
        api_token: str,
        project_key: str,
        issue_type: str = "Task",
        labels: list[str] | None = None,
        account_ids: dict[str, str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._project_key = project_key
        self._issue_type = issue_type
        self._labels = labels if labels is not None else ["meeting-minutes"]
        self._account_ids = account_ids or {}
        self._client = client or httpx.Client(base_url=self._base_url, timeout=30.0)
        self._auth = httpx.BasicAuth(email, api_token)

    def build_fields(self, item: ActionItem, minutes: Minutes) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "project": {"key": self._project_key},
            "issuetype": {"name": self._issue_type},
            "summary": issue_title(item),
            "description": action_item_description(item, minutes),
            "labels": self._labels,
        }
        if item.due_date:
            fields["duedate"] = item.due_date.isoformat()
        account_id = self._account_ids.get(item.owner or "")
        if account_id:
            fields["assignee"] = {"id": account_id}
        return fields

    def export(self, minutes: Minutes) -> ExportResult:
        result = ExportResult(target=self.name)
        for item in minutes.action_items:
            if item.done:
                result.skipped.append(item.id)
                continue
            try:
                response = self._client.post(
                    "/rest/api/3/issue",
                    json={"fields": self.build_fields(item, minutes)},
                    auth=self._auth,
                    headers={"Accept": "application/json"},
                )
            except httpx.HTTPError as exc:
                raise ExportError(f"Jira request failed: {exc}") from exc
            if response.status_code != 201:
                raise ExportError(
                    f"Jira rejected issue '{item.description}': {describe_http_error(response)}"
                )
            key = response.json()["key"]
            result.issues.append(
                ExportedIssue(action_item_id=item.id, key=key, url=f"{self._base_url}/browse/{key}")
            )
        return result
