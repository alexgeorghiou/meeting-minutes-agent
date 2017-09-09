from __future__ import annotations

import json
from pathlib import Path

import pytest

from minutes_agent.cli import main
from minutes_agent.transcription.fake import SAMPLE_TRANSCRIPT


@pytest.fixture
def transcript_file(tmp_path: Path) -> Path:
    path = tmp_path / "release_sync.txt"
    path.write_text(SAMPLE_TRANSCRIPT, encoding="utf-8")
    return path


def test_process_prints_markdown(transcript_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["process", str(transcript_file), "--date", "2026-11-18"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Release Sync")
    assert "Fix the CSV encoding issue" in out


def test_process_prints_json(transcript_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["process", str(transcript_file), "--format", "json", "--attendees", "Priya, Marco, Lena"]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["attendees"] == ["Priya", "Marco", "Lena"]
    assert len(data["action_items"]) == 4


def test_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["process", str(tmp_path / "nope.wav")]) == 2
    assert "does not exist" in capsys.readouterr().err
