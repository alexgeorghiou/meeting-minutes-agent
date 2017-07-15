"""Create one GitHub issue per open action item via the REST API."""

from __future__ import annotations

import httpx

from minutes_agent.exporters.base import (
    ExportedIssue,
    ExportError,
    ExportResult,
    describe_http_error,
    issue_title,
)
from minutes_agent.models import ActionItem, Minutes

API_VERSION = "2022-11-28"


class GitHubIssuesExporter:
    name = "github"

    def __init__(
        self,
        *,
        token: str,
        repo: str,
        api_url: str = "https://api.github.com",
        labels: list[str] | None = None,
        assignees: dict[str, str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if repo.count("/") != 1:
            raise ValueError("repo must look like 'owner/name'")
        self._repo = repo
        self._labels = labels or []
        self._assignees = assignees or {}
        self._client = client or httpx.Client(base_url=api_url, timeout=30.0)
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
        }

    def _body(self, item: ActionItem, minutes: Minutes) -> str:
        lines = [
            item.description,
            "",
            f"- **Meeting:** {minutes.title} ({minutes.meeting_date.isoformat()})",
            f"- **Owner:** {item.owner or 'Unassigned'}",
        ]
        if item.due_date:
            lines.append(f"- **Due:** {item.due_date.isoformat()}")
        elif item.due_text:
            lines.append(f"- **Due:** {item.due_text}")
        lines.append(f"- **Priority:** {item.priority}")
        if minutes.decisions:
            lines += ["", "<details><summary>Decisions from this meeting</summary>", ""]
            lines += [f"- {d.summary}" for d in minutes.decisions]
            lines += ["", "</details>"]
        return "\n".join(lines)

    def export(self, minutes: Minutes) -> ExportResult:
        result = ExportResult(target=self.name)
        for item in minutes.action_items:
            if item.done:
                result.skipped.append(item.id)
                continue
            payload: dict[str, object] = {
                "title": issue_title(item),
                "body": self._body(item, minutes),
                "labels": self._labels,
            }
            login = self._assignees.get(item.owner or "")
            if login:
                payload["assignees"] = [login]

            try:
                response = self._client.post(
                    f"/repos/{self._repo}/issues", json=payload, headers=self._headers
                )
            except httpx.HTTPError as exc:
                raise ExportError(f"GitHub request failed: {exc}") from exc
            if response.status_code != 201:
                raise ExportError(
                    f"GitHub rejected issue '{item.description}': {describe_http_error(response)}"
                )
            data = response.json()
            result.issues.append(
                ExportedIssue(
                    action_item_id=item.id, key=f"#{data['number']}", url=data["html_url"]
                )
            )
        return result
