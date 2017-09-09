"""Command-line entry point.

Examples::

    minutes-agent process standup.m4a --attendees "Priya, Marco, Lena"
    minutes-agent process notes.txt --format json > minutes.json
    minutes-agent serve --port 8000
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from minutes_agent.config import get_settings
from minutes_agent.exporters.markdown import render_markdown
from minutes_agent.llm import build_llm
from minutes_agent.pipeline.graph import MinutesPipeline, PipelineConfig
from minutes_agent.transcription import build_transcriber


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="minutes-agent", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    process = sub.add_parser("process", help="Generate minutes for a recording or .txt transcript")
    process.add_argument("path", type=Path)
    process.add_argument("--title")
    process.add_argument("--date", type=date.fromisoformat, help="Meeting date (YYYY-MM-DD)")
    process.add_argument("--attendees", help="Comma-separated attendee names")
    process.add_argument("--format", choices=["markdown", "json"], default="markdown")

    serve = sub.add_parser("serve", help="Run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = get_settings()

    if args.command == "serve":
        import uvicorn

        uvicorn.run("minutes_agent.main:app", host=args.host, port=args.port)
        return 0

    if not args.path.exists():
        print(f"error: {args.path} does not exist", file=sys.stderr)
        return 2

    transcript = build_transcriber(settings).transcribe(args.path).text
    pipeline = MinutesPipeline(
        build_llm(settings),
        PipelineConfig(
            chunk_words=settings.chunk_words,
            chunk_overlap_words=settings.chunk_overlap_words,
            max_extraction_attempts=settings.max_review_attempts,
        ),
    )
    attendees = [a.strip() for a in (args.attendees or "").split(",") if a.strip()]
    minutes = pipeline.run(
        transcript,
        title=args.title or args.path.stem.replace("_", " ").title(),
        meeting_date=args.date,
        attendees=attendees,
    )
    if args.format == "json":
        print(minutes.model_dump_json(indent=2))
    else:
        print(render_markdown(minutes))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
