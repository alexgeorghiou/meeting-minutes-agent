"""Structured-output schemas the LLM is asked to fill.

These intentionally differ from the domain models: the model reports deadlines
and owners *as spoken*, and the pipeline normalises them afterwards.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from minutes_agent.models import Priority


class SummaryOutput(BaseModel):
    summary: str = Field(description="A neutral 2-5 sentence summary of the discussion.")
    key_points: list[str] = Field(
        default_factory=list, description="Up to 6 short bullet points of notable discussion."
    )


class ExtractedDecision(BaseModel):
    summary: str = Field(description="The decision, as a single declarative sentence.")
    rationale: str | None = Field(default=None, description="Reason given, if any.")
    made_by: str | None = Field(default=None, description="Speaker who proposed or confirmed it.")


class DecisionList(BaseModel):
    decisions: list[ExtractedDecision] = Field(default_factory=list)


class ExtractedActionItem(BaseModel):
    description: str = Field(description="Imperative task description, e.g. 'Fix CSV export'.")
    owner: str | None = Field(
        default=None, description="Person responsible, exactly as named. Null if nobody."
    )
    due: str | None = Field(
        default=None,
        description="Deadline phrase verbatim from the transcript, e.g. 'by Friday'. Null if none.",
    )
    priority: Priority = Priority.MEDIUM
    speaker: str | None = Field(default=None, description="Who said the line committing to it.")


class ActionItemList(BaseModel):
    items: list[ExtractedActionItem] = Field(default_factory=list)
