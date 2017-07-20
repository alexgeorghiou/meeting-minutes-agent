from __future__ import annotations

from datetime import date

import pytest

from minutes_agent.models import ActionItem, Decision, Minutes, Priority


@pytest.fixture
def minutes() -> Minutes:
    return Minutes(
        title="Release sync",
        meeting_date=date(2026, 11, 18),
        attendees=["Priya", "Marco", "Lena"],
        summary="The team re-planned the 2.4 release.",
        key_points=["QA found two blockers in the export flow"],
        decisions=[
            Decision(
                summary="Push the release to next Wednesday",
                rationale="QA needs time to retest",
                made_by="Priya",
            )
        ],
        action_items=[
            ActionItem(
                id="a1",
                description="Fix the CSV encoding issue",
                owner="Lena",
                due_date=date(2026, 11, 20),
                due_text="by Friday",
                priority=Priority.HIGH,
            ),
            ActionItem(id="a2", description="Book a room for the retro | big one"),
            ActionItem(id="a3", description="Update the changelog", owner="Marco", done=True),
        ],
        review_notes=['"Book a room for the retro" has no owner.'],
    )
