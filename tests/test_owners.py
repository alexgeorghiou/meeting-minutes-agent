from __future__ import annotations

import pytest

from minutes_agent.pipeline.owners import is_known_attendee, resolve_owner

ATTENDEES = ["Priya Natarajan", "Marco Rossi", "Lena", "Marta Silva"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Lena", "Lena"),
        ("lena", "Lena"),
        ("@lena", "Lena"),
        ("Priya", "Priya Natarajan"),
        ("marco rossi", "Marco Rossi"),
        ("Marko", "Marco Rossi"),
        ("Pria", "Priya Natarajan"),
        ("someone", None),
        ("The team", None),
        ("", None),
        (None, None),
        ("jordan", "Jordan"),
    ],
)
def test_resolve_owner(raw: str | None, expected: str | None) -> None:
    assert resolve_owner(raw, ATTENDEES) == expected


def test_first_person_resolves_to_speaker() -> None:
    assert resolve_owner("I", ATTENDEES, speaker="Marco") == "Marco Rossi"
    assert resolve_owner("me", ATTENDEES) is None


def test_ambiguous_first_name_is_not_guessed() -> None:
    attendees = ["Sam Lee", "Sam Patel"]
    assert resolve_owner("Sam", attendees) == "Sam"
    assert not is_known_attendee("Sam", attendees)


def test_is_known_attendee() -> None:
    assert is_known_attendee("Lena", ATTENDEES)
    assert not is_known_attendee(None, ATTENDEES)
