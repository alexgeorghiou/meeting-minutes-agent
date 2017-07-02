from __future__ import annotations

from typing import Any

import pytest
from langchain_core.runnables import RunnableLambda

from minutes_agent.config import Settings
from minutes_agent.llm import FakeLLM, LLMError, build_llm
from minutes_agent.llm.langchain_provider import LangChainLLM
from minutes_agent.llm.schemas import ActionItemList, DecisionList, SummaryOutput
from minutes_agent.models import Priority
from minutes_agent.transcription.fake import SAMPLE_TRANSCRIPT


def _prompt(text: str) -> str:
    return f"Extract.\n<transcript>\n{text}\n</transcript>"


def test_fake_extracts_decisions_with_rationale() -> None:
    result = FakeLLM().invoke_structured(DecisionList, system="", prompt=_prompt(SAMPLE_TRANSCRIPT))

    assert [(d.summary, d.rationale, d.made_by) for d in result.decisions] == [
        ("Push the release to next Wednesday", "QA has time to retest", "Priya"),
        ("Drop the legacy theme from this release", "Nobody uses it", "Priya"),
    ]


def test_fake_extracts_action_items_with_owner_and_due_phrase() -> None:
    result = FakeLLM().invoke_structured(
        ActionItemList, system="", prompt=_prompt(SAMPLE_TRANSCRIPT)
    )

    assert [(i.description, i.owner, i.due) for i in result.items] == [
        ("Fix the CSV encoding issue", "Lena", "by Friday"),
        ("Update the release notes and the changelog", "Marco", "by Monday"),
        ("Email the beta customers about the new date", "Marco", "tomorrow"),
        ("Book a room for the release retro", None, "next week"),
    ]


def test_fake_keeps_non_deadline_by_phrase_in_description() -> None:
    result = FakeLLM().invoke_structured(
        ActionItemList, system="", prompt=_prompt("Ana: I'll fix the bug reported by Marta.")
    )
    assert result.items[0].description == "Fix the bug reported by Marta"
    assert result.items[0].due is None


def test_fake_flags_urgent_items_as_high_priority() -> None:
    result = FakeLLM().invoke_structured(
        ActionItemList,
        system="",
        prompt=_prompt("Ben: This is a blocker, I will patch the login redirect today."),
    )
    assert result.items[0].priority is Priority.HIGH
    assert result.items[0].due == "today"


def test_fake_summary_mentions_speakers() -> None:
    result = FakeLLM().invoke_structured(
        SummaryOutput, system="", prompt=_prompt(SAMPLE_TRANSCRIPT)
    )
    assert result.summary.startswith("Priya, Marco, Lena met.")
    assert 0 < len(result.key_points) <= 6


def test_fake_queue_takes_precedence_and_records_calls() -> None:
    llm = FakeLLM().queue(SummaryOutput(summary="Scripted.", key_points=[]))

    first = llm.invoke_structured(SummaryOutput, system="s", prompt="p")
    second = llm.invoke_structured(SummaryOutput, system="s", prompt=_prompt("A: hi"))

    assert first.summary == "Scripted."
    assert second.summary != "Scripted."
    assert len(llm.calls_for(SummaryOutput)) == 2


class _StubChatModel:
    def __init__(self, outputs: list[Any]) -> None:
        self._outputs = outputs
        self.schemas: list[type] = []

    def with_structured_output(self, schema: type) -> RunnableLambda:
        self.schemas.append(schema)
        return RunnableLambda(lambda _messages: self._outputs.pop(0))


def test_langchain_adapter_validates_dict_output() -> None:
    model = _StubChatModel([{"summary": "Done.", "key_points": ["a"]}])
    llm = LangChainLLM(model, name="stub")

    result = llm.invoke_structured(SummaryOutput, system="sys", prompt="hi")

    assert result == SummaryOutput(summary="Done.", key_points=["a"])
    assert model.schemas == [SummaryOutput]


def test_langchain_adapter_retries_then_fails() -> None:
    model = _StubChatModel([{"nope": 1}, {"still": "bad"}])
    llm = LangChainLLM(model, name="stub", retries=1)

    with pytest.raises(LLMError, match="invalid SummaryOutput"):
        llm.invoke_structured(SummaryOutput, system="sys", prompt="hi")


def test_langchain_adapter_wraps_provider_errors() -> None:
    def boom(_messages: Any) -> Any:
        raise ConnectionError("network down")

    class Model:
        def with_structured_output(self, schema: type) -> RunnableLambda:
            return RunnableLambda(boom)

    with pytest.raises(LLMError, match="network down"):
        LangChainLLM(Model(), name="stub").invoke_structured(SummaryOutput, system="", prompt="")


def test_build_llm_defaults_to_fake() -> None:
    assert isinstance(build_llm(Settings()), FakeLLM)


def test_build_llm_respects_model_override() -> None:
    pytest.importorskip("langchain_anthropic")
    llm = build_llm(
        Settings(llm_provider="anthropic", llm_model="claude-test", anthropic_api_key="sk-x")
    )
    assert llm.name == "anthropic:claude-test"
