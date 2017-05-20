from __future__ import annotations

from datetime import date

import pytest

from minutes_agent.pipeline.dates import add_business_days, add_months, parse_due_date

# A Wednesday.
REF = date(2026, 11, 18)


def test_reference_is_wednesday() -> None:
    assert REF.strftime("%A") == "Wednesday"


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("today", date(2026, 11, 18)),
        ("EOD", date(2026, 11, 18)),
        ("by tomorrow", date(2026, 11, 19)),
        ("the day after tomorrow", date(2026, 11, 20)),
        ("by Friday", date(2026, 11, 20)),
        ("Fri", date(2026, 11, 20)),
        ("this Monday", date(2026, 11, 23)),
        ("Wednesday", date(2026, 11, 25)),
        ("next Wednesday", date(2026, 11, 25)),
        ("next Friday", date(2026, 11, 27)),
        ("next Monday", date(2026, 11, 23)),
        ("before Thursday.", date(2026, 11, 19)),
        ("end of the week", date(2026, 11, 20)),
        ("next week", date(2026, 11, 27)),
        ("by end of month", date(2026, 11, 30)),
        ("next month", date(2026, 12, 31)),
        ("end of quarter", date(2026, 12, 31)),
        ("in 3 days", date(2026, 11, 21)),
        ("within two weeks", date(2026, 12, 2)),
        ("in a couple of weeks", date(2026, 12, 2)),
        ("in 2 business days", date(2026, 11, 20)),
        ("in one month", date(2026, 12, 18)),
        ("2026-12-01", date(2026, 12, 1)),
        ("12/5", date(2026, 12, 5)),
        ("1/15/27", date(2027, 1, 15)),
        ("December 3rd", date(2026, 12, 3)),
        ("Jan 9", date(2027, 1, 9)),
        ("on the 5th of March", date(2027, 3, 5)),
        ("March 5, 2027", date(2027, 3, 5)),
        ("the 25th", date(2026, 11, 25)),
        ("the 2nd", date(2026, 12, 2)),
        ("no later than Friday at the latest", date(2026, 11, 20)),
    ],
)
def test_parse_due_date(phrase: str, expected: date) -> None:
    assert parse_due_date(phrase, REF) == expected


@pytest.mark.parametrize("phrase", [None, "", "ASAP", "soon", "whenever", "2026-02-30", "Smarch 4"])
def test_unresolvable_phrases_return_none(phrase: str | None) -> None:
    assert parse_due_date(phrase, REF) is None


def test_same_weekday_rolls_to_next_week() -> None:
    friday = date(2026, 11, 20)
    assert parse_due_date("Friday", friday) == date(2026, 11, 27)


def test_end_of_week_on_weekend_means_following_friday() -> None:
    saturday = date(2026, 11, 21)
    assert parse_due_date("end of week", saturday) == date(2026, 11, 27)


def test_add_months_clamps_day() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)


def test_add_business_days_skips_weekend() -> None:
    assert add_business_days(date(2026, 11, 20), 1) == date(2026, 11, 23)
