"""Deterministic validation of extracted minutes.

Blocking issues send the graph back to action-item extraction with the issues as
feedback; warnings are surfaced to the user as review notes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from minutes_agent.models import ActionItem, Decision
from minutes_agent.pipeline.owners import is_known_attendee

MIN_DESCRIPTION_WORDS = 2
MAX_HORIZON_DAYS = 366


@dataclass(slots=True)
class ReviewResult:
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def review_minutes(
    action_items: list[ActionItem],
    decisions: list[Decision],
    *,
    attendees: list[str],
    meeting_date: date,
) -> ReviewResult:
    result = ReviewResult()

    for item in action_items:
        label = f'"{item.description}"'
        if len(item.description.split()) < MIN_DESCRIPTION_WORDS:
            result.issues.append(f"{label} is too vague; describe the task in a full phrase.")

        if item.owner is None:
            result.warnings.append(f"{label} has no owner.")
        elif attendees and not is_known_attendee(item.owner, attendees):
            result.issues.append(
                f"{label} is owned by '{item.owner}', who is not an attendee "
                f"({', '.join(attendees)}). Use an attendee or null."
            )

        if item.due_text and item.due_date is None:
            result.issues.append(
                f"{label} has deadline '{item.due_text}' that is not a recognisable date phrase. "
                "Quote the deadline as spoken, or use null."
            )
        if item.due_date is not None:
            if item.due_date < meeting_date:
                result.issues.append(
                    f"{label} is due {item.due_date.isoformat()}, before the meeting date."
                )
            elif (item.due_date - meeting_date).days > MAX_HORIZON_DAYS:
                result.warnings.append(f"{label} is due more than a year out; please confirm.")

    seen: set[str] = set()
    for decision in decisions:
        key = decision.summary.lower().strip(" .")
        if key in seen:
            result.warnings.append(f'Decision "{decision.summary}" was recorded twice.')
        seen.add(key)

    return result
