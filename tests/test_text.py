from __future__ import annotations

import itertools

import pytest

from minutes_agent.pipeline.text import (
    chunk_transcript,
    clean_text,
    clean_transcript,
    detect_speakers,
    parse_utterances,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Um, so the main thing is the release.", "So the main thing is the release."),
        ("I I think we we should ship.", "I think we should ship."),
        ("uh you know it's   fine , really", "It's fine, really"),
        ("Ummm okay.", "Okay."),
        ("The umbrella is here.", "The umbrella is here."),
    ],
)
def test_clean_text(raw: str, expected: str) -> None:
    assert clean_text(raw) == expected


def test_parse_utterances_attributes_speakers() -> None:
    transcript = "Priya: Okay, let's start.\n\nsomething inaudible\nMarco:   Uh, sure."

    utterances = parse_utterances(transcript)

    assert [(u.speaker, u.text) for u in utterances] == [
        ("Priya", "Okay, let's start."),
        (None, "Something inaudible"),
        ("Marco", "Sure."),
    ]


def test_clean_transcript_drops_filler_only_lines() -> None:
    assert clean_transcript("Ana: um\nBen: We ship Friday.") == "Ben: We ship Friday."


def test_detect_speakers_in_first_appearance_order() -> None:
    transcript = "Lena: hi\nMarco: hey\nLena: again\nPriya: hello"
    assert detect_speakers(transcript) == ["Lena", "Marco", "Priya"]


def test_chunk_small_transcript_is_single_chunk() -> None:
    assert chunk_transcript("A: one two\nB: three", max_words=50, overlap_words=5) == [
        "A: one two\nB: three"
    ]


def test_chunk_respects_budget_and_overlap() -> None:
    lines = [f"S{i}: " + " ".join(["word"] * 9) for i in range(10)]  # 10 words per line
    chunks = chunk_transcript("\n".join(lines), max_words=30, overlap_words=10)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.split()) <= 30
    # the last line of each chunk is repeated at the start of the next
    for prev, nxt in itertools.pairwise(chunks):
        assert nxt.splitlines()[0] == prev.splitlines()[-1]
    assert chunks[-1].splitlines()[-1].startswith("S9:")


def test_chunk_splits_overlong_lines() -> None:
    chunks = chunk_transcript(" ".join(["w"] * 25), max_words=10, overlap_words=0)
    assert [len(c.split()) for c in chunks] == [10, 10, 5]


def test_chunk_validates_arguments() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_transcript("x", max_words=10, overlap_words=10)
