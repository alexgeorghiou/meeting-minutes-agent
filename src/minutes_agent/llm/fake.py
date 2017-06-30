"""A deterministic, rule-based stand-in for a real chat model.

``FakeLLM`` lets the whole pipeline (and the API) run offline and in CI. It
understands the same prompts the real providers receive: it reads the
``<transcript>`` / ``<summaries>`` block and applies simple linguistic patterns
("we decided to ...", "I'll ... by Friday", "Marco, can you ...?").

Tests can also queue exact responses per schema with :meth:`FakeLLM.queue`.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from typing import cast

from pydantic import BaseModel

from minutes_agent.llm.base import LLMError, T
from minutes_agent.llm.schemas import (
    ActionItemList,
    DecisionList,
    ExtractedActionItem,
    ExtractedDecision,
    SummaryOutput,
)
from minutes_agent.models import Priority
from minutes_agent.pipeline.dates import parse_due_date
from minutes_agent.pipeline.text import Utterance, parse_utterances

_DECISION = re.compile(
    r"\b(?:we(?:'ve| have)? (?:decided|agreed)|the decision is|let's go with|we're going with)"
    r"(?:\s+(?:to|that|on))?\s+(?P<body>.+)",
    re.IGNORECASE,
)
_RATIONALE_SPLIT = re.compile(r"\s+(?:so that|so|because|since)\s+", re.IGNORECASE)
_SELF_COMMIT = re.compile(
    r"\b(?:I will|I'll|I can|I'm going to|I am going to)\s+(?P<task>.+)", re.IGNORECASE
)
_REQUEST = re.compile(
    r"^(?P<owner>[A-Z][a-z]+),\s+(?:can|could|would) you(?: please)?\s+(?P<task>.+?)\?$"
)
_UNOWNED = re.compile(
    r"\b(?:someone|somebody|we) (?:needs? to|should|has to|have to)\s+(?P<task>.+)",
    re.IGNORECASE,
)
_DUE = re.compile(
    r"\s+(?P<due>(?:by|before|until|no later than|on)\s+[\w ,/-]+|tomorrow|today|tonight|"
    r"next week|this week|end of (?:the )?(?:day|week|month))$",
    re.IGNORECASE,
)
_URGENT = re.compile(r"\b(?:urgent|asap|critical|blocker|immediately)\b", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_SMALL_TALK = re.compile(
    r"^(?:okay|ok|great|thanks|thank you|sure|right|hi|hello|let's (?:get started|wrap up))\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class FakeCall:
    schema: type[BaseModel]
    system: str
    prompt: str


class FakeLLM:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[FakeCall] = []
        self._queued: dict[type[BaseModel], deque[BaseModel]] = defaultdict(deque)

    def queue(self, *responses: BaseModel) -> FakeLLM:
        """Return these objects (per schema, FIFO) before falling back to heuristics."""
        for response in responses:
            self._queued[type(response)].append(response)
        return self

    def calls_for(self, schema: type[BaseModel]) -> list[FakeCall]:
        return [call for call in self.calls if call.schema is schema]

    def invoke_structured(self, schema: type[T], *, system: str, prompt: str) -> T:
        self.calls.append(FakeCall(schema=schema, system=system, prompt=prompt))
        queued = self._queued.get(schema)
        if queued:
            return cast(T, queued.popleft())

        if schema is SummaryOutput:
            return cast(T, _summarise(prompt))
        if schema is DecisionList:
            return cast(T, _decisions(_utterances(prompt)))
        if schema is ActionItemList:
            return cast(T, _action_items(_utterances(prompt)))
        raise LLMError(f"FakeLLM has no handler for {schema.__name__}")


def _block(prompt: str, tag: str) -> str | None:
    match = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", prompt, re.DOTALL)
    return match.group(1) if match else None


def _utterances(prompt: str) -> list[Utterance]:
    return parse_utterances(_block(prompt, "transcript") or prompt)


def _sentences(utterances: list[Utterance]) -> list[tuple[str | None, str]]:
    out: list[tuple[str | None, str]] = []
    for utterance in utterances:
        for sentence in _SENTENCE.split(utterance.text):
            sentence = sentence.strip()
            if sentence:
                out.append((utterance.speaker, sentence))
    return out


def _sentence_case(text: str) -> str:
    text = text.strip().rstrip(".!?,;")
    return text[:1].upper() + text[1:] if text else text


def _summarise(prompt: str) -> SummaryOutput:
    summaries = _block(prompt, "summaries")
    if summaries is not None:
        parts = [p.strip() for p in summaries.split("\n---\n") if p.strip()]
        points: list[str] = []
        for part in parts:
            for line in part.splitlines():
                line = line.strip().removeprefix("- ").strip()
                if line.startswith("Key point:"):
                    point = line.removeprefix("Key point:").strip()
                    if point and point not in points:
                        points.append(point)
        first_sentences = [_SENTENCE.split(p.splitlines()[0])[0] for p in parts]
        return SummaryOutput(summary=" ".join(first_sentences), key_points=points[:6])

    utterances = _utterances(prompt)
    speakers = list(dict.fromkeys(u.speaker for u in utterances if u.speaker))
    substantive = [
        sentence
        for _, sentence in _sentences(utterances)
        if len(sentence.split()) >= 6 and not _SMALL_TALK.match(sentence)
    ]
    if not substantive:
        return SummaryOutput(summary="The meeting had no substantive discussion.", key_points=[])
    who = ", ".join(speakers) if speakers else "The participants"
    summary = f"{who} met. {substantive[0]}"
    if len(substantive) > 1:
        summary += f" {substantive[1]}"
    return SummaryOutput(summary=summary, key_points=[_sentence_case(s) for s in substantive[:6]])


def _decisions(utterances: list[Utterance]) -> DecisionList:
    decisions: list[ExtractedDecision] = []
    for speaker, sentence in _sentences(utterances):
        match = _DECISION.search(sentence)
        if not match:
            continue
        body, *reason = _RATIONALE_SPLIT.split(match.group("body"), maxsplit=1)
        decisions.append(
            ExtractedDecision(
                summary=_sentence_case(body),
                rationale=_sentence_case(reason[0]) if reason else None,
                made_by=speaker,
            )
        )
    return DecisionList(decisions=decisions)


def _split_due(task: str) -> tuple[str, str | None]:
    task = task.strip().rstrip(".!?")
    match = _DUE.search(task)
    if not match or parse_due_date(match.group("due"), date.today()) is None:
        # "fix the bug reported by Marta" - the trailing phrase isn't a deadline.
        return task, None
    return task[: match.start()].strip(), match.group("due").strip()


def _action_items(utterances: list[Utterance]) -> ActionItemList:
    items: list[ExtractedActionItem] = []
    for speaker, sentence in _sentences(utterances):
        owner: str | None
        if match := _REQUEST.match(sentence):
            owner, task = match.group("owner"), match.group("task")
        elif match := _SELF_COMMIT.search(sentence):
            owner, task = speaker, match.group("task")
        elif match := _UNOWNED.search(sentence):
            owner, task = None, match.group("task")
        else:
            continue
        description, due = _split_due(task)
        if len(description.split()) < 2:
            continue
        items.append(
            ExtractedActionItem(
                description=_sentence_case(description),
                owner=owner,
                due=due,
                priority=Priority.HIGH if _URGENT.search(sentence) else Priority.MEDIUM,
                speaker=speaker,
            )
        )
    return ActionItemList(items=items)
