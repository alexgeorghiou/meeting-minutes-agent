"""Domain models for meeting minutes.

These are the canonical shapes that flow out of the pipeline, get stored on a job,
are edited in the UI and are pushed to exporters.
"""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Decision(BaseModel):
    """Something the group agreed on during the meeting."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=_new_id)
    summary: str = Field(min_length=3, description="One-sentence statement of the decision.")
    rationale: str | None = Field(default=None, description="Why the group decided this.")
    made_by: str | None = Field(default=None, description="Who proposed or confirmed it.")


class ActionItem(BaseModel):
    """A concrete follow-up task with an owner and (optionally) a due date."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=_new_id)
    description: str = Field(min_length=3)
    owner: str | None = Field(default=None, description="Canonical attendee name, if resolved.")
    due_date: date | None = None
    due_text: str | None = Field(
        default=None, description="The due date exactly as it was phrased in the meeting."
    )
    priority: Priority = Priority.MEDIUM
    done: bool = False

    @field_validator("owner")
    @classmethod
    def _blank_owner_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class Minutes(BaseModel):
    """The full structured output for a single meeting."""

    title: str = "Untitled meeting"
    meeting_date: date
    attendees: list[str] = Field(default_factory=list)
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)

    def unassigned_items(self) -> list[ActionItem]:
        return [item for item in self.action_items if item.owner is None]

    def items_for(self, owner: str) -> list[ActionItem]:
        return [item for item in self.action_items if item.owner == owner]
