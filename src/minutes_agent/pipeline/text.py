"""Transcript clean-up and chunking.

Raw ASR output is full of fillers ("um", "you know"), stutters ("I I think") and
inconsistent whitespace. Cleaning it before it reaches the LLM cuts tokens and
makes extraction prompts noticeably more reliable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FILLERS = re.compile(
    r"(?<![\w'])(?:u+h+m*|u+m+|e+r+m*|a+h+|hmm+|mm+|you know|i mean|like,)(?![\w'])[,.]?\s*",
    re.IGNORECASE,
)
_STUTTER = re.compile(r"\b(\w+)(?:\s+\1\b)+", re.IGNORECASE)
_SPACES = re.compile(r"[ \t]+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.!?;:])")
_SPEAKER_LINE = re.compile(r"^\s*([A-Z][\w .'-]{0,40}?)\s*:\s*(.+)$")


@dataclass(frozen=True, slots=True)
class Utterance:
    speaker: str | None
    text: str

    def render(self) -> str:
        return f"{self.speaker}: {self.text}" if self.speaker else self.text


def clean_text(text: str) -> str:
    """Remove fillers and stutters from a single line of speech."""
    text = _FILLERS.sub("", text)
    text = _STUTTER.sub(r"\1", text)
    text = _SPACES.sub(" ", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = text.strip(" ,")
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def parse_utterances(transcript: str) -> list[Utterance]:
    """Split a transcript into speaker-attributed utterances.

    Lines of the form ``Name: words`` are attributed to ``Name``; any other
    non-empty line is kept with ``speaker=None``.
    """
    utterances: list[Utterance] = []
    for raw in transcript.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _SPEAKER_LINE.match(line)
        if match:
            speaker, body = match.group(1).strip(), match.group(2)
        else:
            speaker, body = None, line
        cleaned = clean_text(body)
        if cleaned:
            utterances.append(Utterance(speaker=speaker, text=cleaned))
    return utterances


def clean_transcript(transcript: str) -> str:
    return "\n".join(u.render() for u in parse_utterances(transcript))


def detect_speakers(transcript: str) -> list[str]:
    """Return speaker names in order of first appearance."""
    seen: dict[str, None] = {}
    for utterance in parse_utterances(transcript):
        if utterance.speaker:
            seen.setdefault(utterance.speaker, None)
    return list(seen)


def chunk_transcript(transcript: str, *, max_words: int = 1200, overlap_words: int = 100) -> list[str]:
    """Split a cleaned transcript into word-bounded chunks on line boundaries.

    Lines are never split unless a single line is longer than ``max_words``. The
    trailing ``overlap_words`` of each chunk are repeated at the start of the next
    one so that a decision spanning a boundary is visible to both extraction calls.
    """
    if max_words <= 0:
        raise ValueError("max_words must be positive")
    if not 0 <= overlap_words < max_words:
        raise ValueError("overlap_words must be in [0, max_words)")

    lines: list[str] = []
    for line in transcript.splitlines():
        words = line.split()
        if not words:
            continue
        for start in range(0, len(words), max_words):
            lines.append(" ".join(words[start : start + max_words]))

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for line in lines:
        n = len(line.split())
        if current and current_words + n > max_words:
            chunks.append("\n".join(current))
            current = _tail_lines(current, overlap_words)
            current_words = sum(len(x.split()) for x in current)
            if current_words + n > max_words:
                current, current_words = [], 0
        current.append(line)
        current_words += n
    if current:
        chunks.append("\n".join(current))
    return chunks


def _tail_lines(lines: list[str], budget: int) -> list[str]:
    tail: list[str] = []
    used = 0
    for line in reversed(lines):
        n = len(line.split())
        if used + n > budget:
            break
        tail.insert(0, line)
        used += n
    return tail
