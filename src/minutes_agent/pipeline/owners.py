"""Map owner mentions ("lena", "Marko", "me") to canonical attendee names."""

from __future__ import annotations

import difflib

UNASSIGNED_TOKENS = frozenset(
    {
        "",
        "someone",
        "somebody",
        "anyone",
        "everyone",
        "we",
        "us",
        "team",
        "the team",
        "all",
        "tbd",
        "unassigned",
        "unknown",
        "none",
        "n/a",
    }
)
SELF_TOKENS = frozenset({"i", "me", "myself"})


def resolve_owner(
    raw: str | None, attendees: list[str], *, speaker: str | None = None
) -> str | None:
    """Return the canonical attendee for ``raw``.

    Resolution order: exact (case-insensitive) match, first-name match, fuzzy match
    for transcription misspellings. A first-person owner resolves to ``speaker``.
    Unrecognised but name-like owners are returned title-cased so the reviewer can
    flag them; vague owners ("someone", "the team") resolve to ``None``.
    """
    if raw is None:
        return None
    value = " ".join(raw.replace("@", "").split()).strip(" .,")
    lowered = value.lower()

    if lowered in UNASSIGNED_TOKENS:
        return None
    if lowered in SELF_TOKENS:
        return resolve_owner(speaker, attendees) if speaker else None

    by_lower = {name.lower(): name for name in attendees}
    if lowered in by_lower:
        return by_lower[lowered]

    first_names: dict[str, list[str]] = {}
    for name in attendees:
        first_names.setdefault(name.split()[0].lower(), []).append(name)
    candidates = first_names.get(lowered.split()[0], [])
    if len(candidates) == 1:
        return candidates[0]

    close = difflib.get_close_matches(lowered, list(by_lower), n=1, cutoff=0.8)
    if close:
        return by_lower[close[0]]
    close_first = difflib.get_close_matches(lowered, list(first_names), n=1, cutoff=0.8)
    if close_first and len(first_names[close_first[0]]) == 1:
        return first_names[close_first[0]][0]

    return value.title()


def is_known_attendee(owner: str | None, attendees: list[str]) -> bool:
    return owner is not None and owner in attendees
