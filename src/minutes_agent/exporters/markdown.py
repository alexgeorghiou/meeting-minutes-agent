"""Render minutes as a Markdown document."""

from __future__ import annotations

from minutes_agent.exporters.base import ExportResult
from minutes_agent.models import ActionItem, Minutes


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _due(item: ActionItem) -> str:
    if item.due_date is None:
        return item.due_text or "-"
    return item.due_date.strftime("%a %d %b %Y")


def render_markdown(minutes: Minutes) -> str:
    lines: list[str] = [f"# {minutes.title}", ""]
    lines.append(f"**Date:** {minutes.meeting_date.strftime('%A %d %B %Y')}  ")
    if minutes.attendees:
        lines.append(f"**Attendees:** {', '.join(minutes.attendees)}")
    lines.append("")

    lines += ["## Summary", "", minutes.summary or "_No summary._", ""]

    if minutes.key_points:
        lines += ["## Key points", ""]
        lines += [f"- {point}" for point in minutes.key_points]
        lines.append("")

    lines += ["## Decisions", ""]
    if minutes.decisions:
        for i, decision in enumerate(minutes.decisions, start=1):
            line = f"{i}. **{decision.summary}**"
            if decision.made_by:
                line += f" ({decision.made_by})"
            lines.append(line)
            if decision.rationale:
                lines.append(f"   - _Why:_ {decision.rationale}")
    else:
        lines.append("_No decisions recorded._")
    lines.append("")

    lines += ["## Action items", ""]
    if minutes.action_items:
        lines += ["| Done | Task | Owner | Due | Priority |", "| :--: | --- | --- | --- | --- |"]
        for item in minutes.action_items:
            lines.append(
                f"| {'[x]' if item.done else '[ ]'} | {_cell(item.description)} | "
                f"{_cell(item.owner or 'Unassigned')} | {_cell(_due(item))} | {item.priority} |"
            )
    else:
        lines.append("_No action items._")
    lines.append("")

    if minutes.review_notes:
        lines += ["## Needs review", ""]
        lines += [f"- {note}" for note in minutes.review_notes]
        lines.append("")

    return "\n".join(lines)


class MarkdownExporter:
    name = "markdown"

    def export(self, minutes: Minutes) -> ExportResult:
        return ExportResult(
            target=self.name, content=render_markdown(minutes), content_type="text/markdown"
        )
