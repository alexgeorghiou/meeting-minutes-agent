"""Normalise spoken due dates ("by Friday", "end of month") to calendar dates.

LLMs are good at spotting *that* something has a deadline and bad at calendar
arithmetic, so extraction asks the model for the deadline phrase verbatim and
this module resolves it deterministically against the meeting date.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

WEEKDAYS = {name.lower(): i for i, name in enumerate(calendar.day_name)}
WEEKDAYS.update({name.lower(): i for i, name in enumerate(calendar.day_abbr)})
WEEKDAYS.update({"tues": 1, "thur": 3, "thurs": 3})

MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
MONTHS["sept"] = 9

NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "a couple of": 2,
    "a couple": 2,
    "couple of": 2,
    "three": 3,
    "a few": 3,
    "few": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

_PREFIX = re.compile(
    r"^(?:(?:no later than|not later than|due|by|before|on|until|till|for|at the latest)\s+)+"
)
_SUFFIX = re.compile(r"\s+(?:at the latest|latest|at the end of the day)$")
_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_SLASH = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$")
_RELATIVE = re.compile(
    r"^(?:in|within)\s+(\d+|[a-z ]+?)\s+(day|business day|working day|week|month)s?(?:'? time)?$"
)
_MONTH_DAY = re.compile(r"^(?:the\s+)?([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?$")
_DAY_MONTH = re.compile(
    r"^(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)\.?(?:,?\s+(\d{4}))?$"
)
_ORDINAL_DAY = re.compile(r"^the\s+(\d{1,2})(?:st|nd|rd|th)$")
_WEEKDAY = re.compile(r"^(?:(this|next|coming|the coming)\s+)?([a-z]+)$")


def parse_due_date(text: str | None, reference: date) -> date | None:
    """Resolve a natural-language deadline relative to ``reference``.

    Returns ``None`` when the phrase has no resolvable date ("ASAP", "soon").
    """
    if not text:
        return None
    phrase = _normalise(text)
    if not phrase:
        return None

    for resolver in (
        _fixed_words,
        _iso,
        _slash,
        _relative,
        _period_end,
        _month_day,
        _day_of_month,
        _weekday,
    ):
        result = resolver(phrase, reference)
        if result is not None:
            return result
    return None


def _normalise(text: str) -> str:
    phrase = text.strip().lower()
    phrase = re.sub(r"[!?]+$", "", phrase).rstrip(". ")
    phrase = re.sub(r"\s+", " ", phrase)
    phrase = _PREFIX.sub("", phrase)
    phrase = _SUFFIX.sub("", phrase)
    return phrase.strip()


def _fixed_words(phrase: str, ref: date) -> date | None:
    table = {
        "today": 0,
        "tonight": 0,
        "end of day": 0,
        "end of the day": 0,
        "eod": 0,
        "close of business": 0,
        "cob": 0,
        "tomorrow": 1,
        "tomorrow morning": 1,
        "end of day tomorrow": 1,
        "the day after tomorrow": 2,
        "day after tomorrow": 2,
    }
    if phrase in table:
        return ref + timedelta(days=table[phrase])
    return None


def _iso(phrase: str, ref: date) -> date | None:
    match = _ISO.match(phrase)
    if not match:
        return None
    return _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _slash(phrase: str, ref: date) -> date | None:
    """``M/D`` or ``M/D/YYYY`` (US ordering, which is what Whisper tends to emit)."""
    match = _SLASH.match(phrase)
    if not match:
        return None
    month, day = int(match.group(1)), int(match.group(2))
    year_text = match.group(3)
    if year_text:
        year = int(year_text) + (2000 if len(year_text) == 2 else 0)
        return _safe_date(year, month, day)
    return _next_occurrence(month, day, ref)


def _relative(phrase: str, ref: date) -> date | None:
    match = _RELATIVE.match(phrase)
    if not match:
        return None
    amount_text, unit = match.group(1).strip(), match.group(2)
    amount = int(amount_text) if amount_text.isdigit() else NUMBER_WORDS.get(amount_text)
    if amount is None:
        return None
    if unit == "day":
        return ref + timedelta(days=amount)
    if unit in {"business day", "working day"}:
        return add_business_days(ref, amount)
    if unit == "week":
        return ref + timedelta(weeks=amount)
    return add_months(ref, amount)


def _period_end(phrase: str, ref: date) -> date | None:
    phrase = phrase.removeprefix("the ")
    # Friday of the current working week (the following Friday on weekends).
    week_end = ref + timedelta(days=(4 - ref.weekday()) % 7)
    table: dict[str, date] = {
        "end of week": week_end,
        "end of the week": week_end,
        "eow": week_end,
        "this week": week_end,
        "next week": week_end + timedelta(weeks=1),
        "end of next week": week_end + timedelta(weeks=1),
        "end of month": _month_end(ref),
        "end of the month": _month_end(ref),
        "eom": _month_end(ref),
        "this month": _month_end(ref),
        "next month": _month_end(add_months(ref, 1)),
        "end of next month": _month_end(add_months(ref, 1)),
        "end of quarter": _quarter_end(ref),
        "end of the quarter": _quarter_end(ref),
        "eoq": _quarter_end(ref),
        "end of year": date(ref.year, 12, 31),
        "end of the year": date(ref.year, 12, 31),
    }
    return table.get(phrase)


def _month_day(phrase: str, ref: date) -> date | None:
    match = _MONTH_DAY.match(phrase)
    if not match or match.group(1) not in MONTHS:
        return None
    month, day = MONTHS[match.group(1)], int(match.group(2))
    if match.group(3):
        return _safe_date(int(match.group(3)), month, day)
    return _next_occurrence(month, day, ref)


def _day_of_month(phrase: str, ref: date) -> date | None:
    """Resolve "5th of March", or a bare "the 15th" meaning the next 15th on/after ``ref``."""
    match = _DAY_MONTH.match(phrase)
    if match and match.group(2) in MONTHS:
        month, day = MONTHS[match.group(2)], int(match.group(1))
        if match.group(3):
            return _safe_date(int(match.group(3)), month, day)
        return _next_occurrence(month, day, ref)
    match = _ORDINAL_DAY.match(phrase)
    if not match:
        return None
    day = int(match.group(1))
    candidate = _safe_date(ref.year, ref.month, day)
    if candidate is not None and candidate >= ref:
        return candidate
    following = add_months(ref.replace(day=1), 1)
    return _safe_date(following.year, following.month, day)


def _weekday(phrase: str, ref: date) -> date | None:
    match = _WEEKDAY.match(phrase)
    if not match:
        return None
    modifier, name = match.group(1), match.group(2)
    if name not in WEEKDAYS:
        return None
    target = WEEKDAYS[name]
    if modifier == "next":
        # "next Friday" = the Friday of next calendar week.
        next_monday = ref + timedelta(days=7 - ref.weekday())
        return next_monday + timedelta(days=target)
    # "Friday" / "this Friday" = the next upcoming Friday (a week out if today is Friday).
    delta = (target - ref.weekday()) % 7
    return ref + timedelta(days=delta or 7)


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def add_business_days(value: date, days: int) -> date:
    current = value
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def _month_end(value: date) -> date:
    return date(value.year, value.month, calendar.monthrange(value.year, value.month)[1])


def _quarter_end(value: date) -> date:
    last_month = ((value.month - 1) // 3 + 1) * 3
    return date(value.year, last_month, calendar.monthrange(value.year, last_month)[1])


def _next_occurrence(month: int, day: int, ref: date) -> date | None:
    candidate = _safe_date(ref.year, month, day)
    if candidate is None:
        return None
    if candidate < ref:
        candidate = _safe_date(ref.year + 1, month, day)
    return candidate


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None
