from __future__ import annotations

from datetime import date

from minutes_agent.models import ActionItem, Decision
from minutes_agent.pipeline.review import review_minutes

DAY = date(2026, 11, 18)
ATTENDEES = ["Priya", "Marco"]


def _review(*items: ActionItem, decisions: list[Decision] | None = None):
    return review_minutes(list(items), decisions or [], attendees=ATTENDEES, meeting_date=DAY)


def test_clean_items_pass() -> None:
    result = _review(ActionItem(description="Send the invite", owner="Marco", due_date=DAY))
    assert result.ok
    assert result.warnings == []


def test_unknown_owner_is_blocking() -> None:
    result = _review(ActionItem(description="Send the invite", owner="Jordan"))
    assert not result.ok
    assert "'Jordan', who is not an attendee" in result.issues[0]


def test_unknown_owner_allowed_when_attendees_unknown() -> None:
    result = review_minutes(
        [ActionItem(description="Send the invite", owner="Jordan")],
        [],
        attendees=[],
        meeting_date=DAY,
    )
    assert result.ok


def test_unparseable_and_past_due_dates_are_blocking() -> None:
    result = _review(
        ActionItem(description="Write the doc", owner="Priya", due_text="when possible"),
        ActionItem(description="Book travel", owner="Priya", due_date=date(2026, 11, 1)),
    )
    assert len(result.issues) == 2
    assert "not a recognisable date phrase" in result.issues[0]
    assert "before the meeting date" in result.issues[1]


def test_vague_description_is_blocking() -> None:
    assert not _review(ActionItem(description="Followup", owner="Priya")).ok


def test_warnings_for_missing_owner_far_due_date_and_duplicate_decisions() -> None:
    result = _review(
        ActionItem(description="Plan the offsite"),
        ActionItem(description="Renew the domain", owner="Marco", due_date=date(2028, 1, 1)),
        decisions=[Decision(summary="Use Postgres"), Decision(summary="use postgres.")],
    )
    assert result.ok
    assert len(result.warnings) == 3
