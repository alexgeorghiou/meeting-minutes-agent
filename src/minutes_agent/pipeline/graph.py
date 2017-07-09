"""The LangGraph state machine that turns a transcript into :class:`Minutes`.

::

    prepare -> summarize -> extract_decisions -> extract_action_items
            -> normalize -> review --(issues & attempts left)--> extract_action_items
                                   \\-> finalize -> END
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from minutes_agent.llm.base import StructuredLLM
from minutes_agent.llm.schemas import (
    ActionItemList,
    DecisionList,
    ExtractedActionItem,
    SummaryOutput,
)
from minutes_agent.models import ActionItem, Decision, Minutes
from minutes_agent.pipeline import prompts
from minutes_agent.pipeline.dates import parse_due_date
from minutes_agent.pipeline.owners import resolve_owner
from minutes_agent.pipeline.review import review_minutes
from minutes_agent.pipeline.text import chunk_transcript, clean_transcript, detect_speakers

NODES = (
    "prepare",
    "summarize",
    "extract_decisions",
    "extract_action_items",
    "normalize",
    "review",
    "finalize",
)


class MinutesState(TypedDict, total=False):
    # inputs
    transcript: str
    title: str
    meeting_date: date
    attendees: list[str]
    # intermediate
    chunks: list[str]
    summary: str
    key_points: list[str]
    decisions: list[Decision]
    raw_action_items: list[ExtractedActionItem]
    action_items: list[ActionItem]
    review_issues: list[str]
    review_warnings: list[str]
    attempts: int
    # output
    minutes: Minutes


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    chunk_words: int = 1200
    chunk_overlap_words: int = 100
    max_extraction_attempts: int = 2


def _key(text: str) -> str:
    return " ".join(text.lower().strip(" .!").split())


class MinutesPipeline:
    """Builds and runs the minutes graph against a :class:`StructuredLLM`."""

    def __init__(self, llm: StructuredLLM, config: PipelineConfig | None = None) -> None:
        self.llm = llm
        self.config = config or PipelineConfig()
        self.graph = self._build().compile()

    # -- graph wiring -------------------------------------------------------

    def _build(self) -> StateGraph:
        builder = StateGraph(MinutesState)
        builder.add_node("prepare", self.prepare)
        builder.add_node("summarize", self.summarize)
        builder.add_node("extract_decisions", self.extract_decisions)
        builder.add_node("extract_action_items", self.extract_action_items)
        builder.add_node("normalize", self.normalize)
        builder.add_node("review", self.review)
        builder.add_node("finalize", self.finalize)

        builder.add_edge(START, "prepare")
        builder.add_edge("prepare", "summarize")
        builder.add_edge("summarize", "extract_decisions")
        builder.add_edge("extract_decisions", "extract_action_items")
        builder.add_edge("extract_action_items", "normalize")
        builder.add_edge("normalize", "review")
        builder.add_conditional_edges(
            "review",
            self.route_after_review,
            {"retry": "extract_action_items", "finalize": "finalize"},
        )
        builder.add_edge("finalize", END)
        return builder

    def route_after_review(self, state: MinutesState) -> Literal["retry", "finalize"]:
        if state.get("review_issues") and state.get("attempts", 0) < (
            self.config.max_extraction_attempts
        ):
            return "retry"
        return "finalize"

    # -- nodes ------------------------------------------------------------------

    def prepare(self, state: MinutesState) -> dict[str, Any]:
        cleaned = clean_transcript(state["transcript"])
        if not cleaned:
            raise ValueError("transcript is empty after cleaning")
        attendees = state.get("attendees") or detect_speakers(cleaned)
        chunks = chunk_transcript(
            cleaned,
            max_words=self.config.chunk_words,
            overlap_words=self.config.chunk_overlap_words,
        )
        return {
            "transcript": cleaned,
            "attendees": attendees,
            "chunks": chunks,
            "attempts": 0,
            "title": state.get("title") or "Untitled meeting",
            "meeting_date": state.get("meeting_date") or date.today(),
        }

    def summarize(self, state: MinutesState) -> dict[str, Any]:
        chunks, title = state["chunks"], state["title"]
        partials = [
            self.llm.invoke_structured(
                SummaryOutput,
                system=prompts.SYSTEM,
                prompt=prompts.summarize_chunk(chunk, title=title, part=i, total=len(chunks)),
            )
            for i, chunk in enumerate(chunks, start=1)
        ]
        if len(partials) == 1:
            final = partials[0]
        else:
            rendered = [
                p.summary + "".join(f"\n- Key point: {kp}" for kp in p.key_points) for p in partials
            ]
            final = self.llm.invoke_structured(
                SummaryOutput,
                system=prompts.SYSTEM,
                prompt=prompts.combine_summaries(rendered, title=title),
            )
        return {"summary": final.summary.strip(), "key_points": final.key_points[:6]}

    def extract_decisions(self, state: MinutesState) -> dict[str, Any]:
        decisions: list[Decision] = []
        seen: set[str] = set()
        for chunk in state["chunks"]:
            result = self.llm.invoke_structured(
                DecisionList,
                system=prompts.SYSTEM,
                prompt=prompts.extract_decisions(chunk, attendees=state["attendees"]),
            )
            for extracted in result.decisions:
                key = _key(extracted.summary)
                if not key or key in seen:
                    continue  # chunk overlap produces repeats
                seen.add(key)
                decisions.append(
                    Decision(
                        summary=extracted.summary,
                        rationale=extracted.rationale,
                        made_by=resolve_owner(extracted.made_by, state["attendees"]),
                    )
                )
        return {"decisions": decisions}

    def extract_action_items(self, state: MinutesState) -> dict[str, Any]:
        feedback = state.get("review_issues") or None
        raw: list[ExtractedActionItem] = []
        for chunk in state["chunks"]:
            result = self.llm.invoke_structured(
                ActionItemList,
                system=prompts.SYSTEM,
                prompt=prompts.extract_action_items(
                    chunk,
                    attendees=state["attendees"],
                    meeting_date=state["meeting_date"],
                    feedback=feedback,
                ),
            )
            raw.extend(result.items)
        return {"raw_action_items": raw, "attempts": state.get("attempts", 0) + 1}

    def normalize(self, state: MinutesState) -> dict[str, Any]:
        attendees, meeting_date = state["attendees"], state["meeting_date"]
        items: list[ActionItem] = []
        by_key: dict[str, ActionItem] = {}
        for raw in state["raw_action_items"]:
            description = raw.description.strip().rstrip(".")
            key = _key(description)
            if not key:
                continue
            item = ActionItem(
                description=description,
                owner=resolve_owner(raw.owner, attendees, speaker=raw.speaker),
                due_text=raw.due,
                due_date=parse_due_date(raw.due, meeting_date),
                priority=raw.priority,
            )
            existing = by_key.get(key)
            if existing is not None:
                # Same task seen twice (chunk overlap): keep the most complete copy.
                existing.owner = existing.owner or item.owner
                existing.due_date = existing.due_date or item.due_date
                existing.due_text = existing.due_text or item.due_text
                continue
            by_key[key] = item
            items.append(item)
        return {"action_items": items}

    def review(self, state: MinutesState) -> dict[str, Any]:
        result = review_minutes(
            state["action_items"],
            state["decisions"],
            attendees=state["attendees"],
            meeting_date=state["meeting_date"],
        )
        return {"review_issues": result.issues, "review_warnings": result.warnings}

    def finalize(self, state: MinutesState) -> dict[str, Any]:
        notes = list(state.get("review_warnings", []))
        notes.extend(f"Unresolved: {issue}" for issue in state.get("review_issues", []))
        minutes = Minutes(
            title=state["title"],
            meeting_date=state["meeting_date"],
            attendees=state["attendees"],
            summary=state["summary"],
            key_points=state["key_points"],
            decisions=state["decisions"],
            action_items=state["action_items"],
            review_notes=notes,
        )
        return {"minutes": minutes}

    # -- entry points -----------------------------------------------------------

    @staticmethod
    def initial_state(
        transcript: str,
        *,
        title: str | None = None,
        meeting_date: date | None = None,
        attendees: list[str] | None = None,
    ) -> MinutesState:
        state: MinutesState = {"transcript": transcript, "attendees": attendees or []}
        if title:
            state["title"] = title
        if meeting_date:
            state["meeting_date"] = meeting_date
        return state

    def run(self, transcript: str, **kwargs: Any) -> Minutes:
        final = self.graph.invoke(self.initial_state(transcript, **kwargs))
        return final["minutes"]

    def stream(self, transcript: str, **kwargs: Any) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield ``(node_name, state_update)`` as each node completes."""
        for update in self.graph.stream(self.initial_state(transcript, **kwargs)):
            for node, delta in update.items():
                yield node, delta or {}
