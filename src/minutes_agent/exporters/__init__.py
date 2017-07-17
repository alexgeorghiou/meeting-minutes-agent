"""Export targets for finished minutes."""

from __future__ import annotations

from minutes_agent.config import Settings
from minutes_agent.exporters.base import ExportedIssue, Exporter, ExportError, ExportResult
from minutes_agent.exporters.github import GitHubIssuesExporter
from minutes_agent.exporters.jira import JiraExporter
from minutes_agent.exporters.markdown import MarkdownExporter, render_markdown

__all__ = [
    "ExportError",
    "ExportResult",
    "ExportedIssue",
    "Exporter",
    "GitHubIssuesExporter",
    "JiraExporter",
    "MarkdownExporter",
    "build_exporters",
    "render_markdown",
]


def build_exporters(settings: Settings) -> dict[str, Exporter]:
    """Return the exporters whose credentials are configured (Markdown is always on)."""
    exporters: dict[str, Exporter] = {"markdown": MarkdownExporter()}
    if settings.github_token and settings.github_repo:
        exporters["github"] = GitHubIssuesExporter(
            token=settings.github_token.get_secret_value(),
            repo=settings.github_repo,
            api_url=settings.github_api_url,
            labels=settings.github_labels,
        )
    if (
        settings.jira_base_url
        and settings.jira_email
        and settings.jira_api_token
        and settings.jira_project_key
    ):
        exporters["jira"] = JiraExporter(
            base_url=settings.jira_base_url,
            email=settings.jira_email,
            api_token=settings.jira_api_token.get_secret_value(),
            project_key=settings.jira_project_key,
            issue_type=settings.jira_issue_type,
        )
    return exporters
