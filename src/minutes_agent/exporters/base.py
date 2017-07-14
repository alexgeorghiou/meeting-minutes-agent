"""Exporter interface shared by every export target."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, Field

from minutes_agent.models import ActionItem, Minutes


class ExportError(RuntimeError):
    """Raised when an export target rejects the request."""


class ExportedIssue(BaseModel):
    action_item_id: str
    key: str
    url: str


class ExportResult(BaseModel):
    target: str
    content: str | None = Field(default=None, description="Rendered document, for file targets.")
    content_type: str | None = None
    issues: list[ExportedIssue] = Field(default_factory=list)
    skipped: list[str] = Field(
        default_factory=list, description="Action item ids that were not exported."
    )


@runtime_checkable
class Exporter(Protocol):
    name: str

    def export(self, minutes: Minutes) -> ExportResult: ...


def issue_title(item: ActionItem) -> str:
    title = item.description
    return title if len(title) <= 120 else title[:117] + "..."


def describe_http_error(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:200]}"
    if isinstance(body, dict):
        # GitHub: {"message": ...}; Jira: {"errorMessages": [...], "errors": {...}}
        parts: list[str] = []
        if body.get("message"):
            parts.append(str(body["message"]))
        parts.extend(str(m) for m in body.get("errorMessages") or [])
        parts.extend(f"{k}: {v}" for k, v in (body.get("errors") or {}).items())
        if parts:
            return f"HTTP {response.status_code}: {'; '.join(parts)}"
    return f"HTTP {response.status_code}"
