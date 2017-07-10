from __future__ import annotations

from datetime import date

import pytest

from minutes_agent.llm import FakeLLM
from minutes_agent.llm.schemas import ActionItemList, ExtractedActionItem, SummaryOutput
from minutes_agent.pipeline.graph import MinutesPipeline, PipelineConfig
from minutes_agent.transcription.fake import SAMPLE_TRANSCRIPT

MEETING_DAY = date(2026, 11, 18)  # Wednesday


def test_end_to_end_minutes_from_sample_transcript() -> None:
    minutes = MinutesPipeline(FakeLLM()).run(
        SAMPLE_TRANSCRIPT, title="Release sync", meeting_date=MEETING_DAY
    )

    assert minutes.title == "Release sync"
    assert minutes.attendees == ["Priya", "Marco", "Lena"]
    assert minutes.summary
    assert [d.summary for d in minutes.decisions] == [
        "Push the release to next Wednesday",
        "Drop the legacy theme from this release",
    ]
    items = {item.description: item for item in minutes.action_items}
    csv = items["Fix the CSV encoding issue"]
    assert (csv.owner, csv.due_date, csv.due_text) == ("Lena", date(2026, 11, 20), "by Friday")
    assert items["Update the release notes and the changelog"].due_date == date(2026, 11, 23)
    assert items["Email the beta customers about the new date"].due_date == date(2026, 11, 19)
    retro = items["Book a room for the release retro"]
    assert retro.owner is None
    assert retro.due_date == date(2026, 11, 27)
    assert minutes.review_notes == ['"Book a room for the release retro" has no owner.']


def test_explicit_attendees_canonicalise_owners() -> None:
    minutes = MinutesPipeline(FakeLLM()).run(
        SAMPLE_TRANSCRIPT,
        meeting_date=MEETING_DAY,
        attendees=["Priya Natarajan", "Marco Rossi", "Lena Weber"],
    )
    owners = {item.owner for item in minutes.action_items}
    assert owners == {"Lena Weber", "Marco Rossi", None}
    assert minutes.decisions[0].made_by == "Priya Natarajan"


def test_review_retries_extraction_with_feedback() -> None:
    bad = ActionItemList(
        items=[ExtractedActionItem(description="Prepare the demo", owner="Jordan", due="Friday")]
    )
    good = ActionItemList(
        items=[ExtractedActionItem(description="Prepare the demo", owner="Lena", due="Friday")]
    )
    llm = FakeLLM().queue(bad, good)

    pipeline = MinutesPipeline(llm, PipelineConfig(max_extraction_attempts=3))
    minutes = pipeline.run(SAMPLE_TRANSCRIPT, meeting_date=MEETING_DAY)

    calls = llm.calls_for(ActionItemList)
    assert len(calls) == 2
    assert "Jordan" not in calls[0].prompt
    assert "previous extraction had these problems" in calls[1].prompt
    assert "'Jordan', who is not an attendee" in calls[1].prompt
    assert minutes.action_items[0].owner == "Lena"
    assert not any(note.startswith("Unresolved") for note in minutes.review_notes)


def test_retry_budget_is_respected_and_issues_reported() -> None:
    bad = ActionItemList(items=[ExtractedActionItem(description="Ship it", due="sometime later")])
    llm = FakeLLM().queue(bad, bad, bad)

    pipeline = MinutesPipeline(llm, PipelineConfig(max_extraction_attempts=2))
    minutes = pipeline.run("Ana: hello there team", meeting_date=MEETING_DAY)

    assert len(llm.calls_for(ActionItemList)) == 2
    assert any("Unresolved" in note and "sometime later" in note for note in minutes.review_notes)


def test_long_transcripts_are_chunked_and_summaries_combined() -> None:
    filler = "\n".join(
        f"Ana: We reviewed backlog item number {i} in detail today." for i in range(60)
    )
    transcript = filler + "\nBen: We decided to freeze scope for the sprint.\n" + filler
    llm = FakeLLM()

    minutes = MinutesPipeline(llm, PipelineConfig(chunk_words=200, chunk_overlap_words=20)).run(
        transcript, meeting_date=MEETING_DAY
    )

    summary_calls = llm.calls_for(SummaryOutput)
    assert len(summary_calls) > 2
    assert "<summaries>" in summary_calls[-1].prompt
    assert [d.summary for d in minutes.decisions] == ["Freeze scope for the sprint"]


def test_overlapping_chunks_do_not_duplicate_action_items() -> None:
    lines = [f"Ana: Status update number {i} is all green." for i in range(30)]
    lines.insert(15, "Ben: I will renew the staging certificate by Friday.")
    pipeline = MinutesPipeline(FakeLLM(), PipelineConfig(chunk_words=80, chunk_overlap_words=40))

    minutes = pipeline.run("\n".join(lines), meeting_date=MEETING_DAY)

    assert [i.description for i in minutes.action_items] == ["Renew the staging certificate"]


def test_stream_reports_every_node_in_order() -> None:
    nodes = [node for node, _ in MinutesPipeline(FakeLLM()).stream(SAMPLE_TRANSCRIPT)]
    assert nodes == [
        "prepare",
        "summarize",
        "extract_decisions",
        "extract_action_items",
        "normalize",
        "review",
        "finalize",
    ]


def test_empty_transcript_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        MinutesPipeline(FakeLLM()).run("  um \n uh  ")
