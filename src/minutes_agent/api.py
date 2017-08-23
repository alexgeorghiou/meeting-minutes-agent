"""FastAPI application: upload, job status, minutes editing and export."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from minutes_agent import __version__
from minutes_agent.config import Settings, get_settings
from minutes_agent.exporters import Exporter, ExportError, ExportResult, build_exporters
from minutes_agent.exporters.markdown import render_markdown
from minutes_agent.jobs import (
    InMemoryJobStore,
    Job,
    JobNotFoundError,
    JobStatus,
    JobStore,
    SqliteJobStore,
)
from minutes_agent.llm import StructuredLLM, build_llm
from minutes_agent.models import ActionItem, Minutes, Priority
from minutes_agent.pipeline.graph import MinutesPipeline, PipelineConfig
from minutes_agent.service import MinutesService
from minutes_agent.transcription import Transcriber, build_transcriber

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = frozenset(
    {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg", ".flac", ".txt"}
)


# --- request / response models ----------------------------------------------------


class JobView(BaseModel):
    id: str
    status: JobStatus
    stage: str | None
    progress: float
    title: str | None
    source: str
    error: str | None
    has_minutes: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, job: Job) -> JobView:
        return cls(
            **job.model_dump(include=set(cls.model_fields) - {"has_minutes"}),
            has_minutes=job.minutes is not None,
        )


class TranscriptRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=500_000)
    title: str | None = None
    meeting_date: date | None = None
    attendees: list[str] = Field(default_factory=list)


class ActionItemPatch(BaseModel):
    description: str | None = Field(default=None, min_length=3)
    owner: str | None = None
    due_date: date | None = None
    priority: Priority | None = None
    done: bool | None = None


# --- dependency container ---------------------------------------------------------


@dataclass(slots=True)
class AppContext:
    settings: Settings
    store: JobStore
    service: MinutesService
    exporters: dict[str, Exporter]


def get_context(request: Request) -> AppContext:
    return request.app.state.context  # type: ignore[no-any-return]


Ctx = Annotated[AppContext, Depends(get_context)]


def _job_or_404(ctx: AppContext, job_id: str) -> Job:
    try:
        return ctx.store.get(job_id)
    except JobNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} not found") from None


def _minutes_or_409(job: Job) -> Minutes:
    if job.minutes is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"minutes are not ready (job is {job.status})"
        )
    return job.minutes


def _parse_attendees(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [name.strip() for name in raw.replace(";", ",").split(",") if name.strip()]


# --- routes -----------------------------------------------------------------------

router = APIRouter(prefix="/api")


@router.get("/health")
def health(ctx: Ctx) -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "llm": ctx.service.pipeline.llm.name,
        "transcriber": ctx.service.transcriber.name,
        "exporters": sorted(ctx.exporters),
    }


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
def upload_audio(
    ctx: Ctx,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File(description="Meeting recording (or a .txt transcript)")],
    title: Annotated[str | None, Form()] = None,
    meeting_date: Annotated[date | None, Form()] = None,
    attendees: Annotated[str | None, Form(description="Comma-separated names")] = None,
) -> JobView:
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"unsupported file type '{suffix or filename}'; "
            f"expected one of {', '.join(sorted(AUDIO_EXTENSIONS))}",
        )
    if file.size is not None and file.size > ctx.settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            413,  # Content Too Large
            f"file exceeds {ctx.settings.max_upload_mb} MB",
        )

    job = ctx.store.create(
        Job(
            source=filename,
            title=title or Path(filename).stem.replace("_", " ").replace("-", " ").title(),
            meeting_date=meeting_date,
            attendees=_parse_attendees(attendees),
        )
    )
    ctx.settings.upload_dir.mkdir(parents=True, exist_ok=True)
    destination = ctx.settings.upload_dir / f"{job.id}{suffix}"
    with destination.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    background.add_task(ctx.service.process_audio, job.id, destination)
    return JobView.of(job)


@router.post("/jobs/transcript", status_code=status.HTTP_202_ACCEPTED)
def submit_transcript(ctx: Ctx, background: BackgroundTasks, body: TranscriptRequest) -> JobView:
    job = ctx.store.create(
        Job(
            source="transcript",
            title=body.title,
            meeting_date=body.meeting_date,
            attendees=body.attendees,
        )
    )
    background.add_task(ctx.service.process_transcript, job.id, body.transcript)
    return JobView.of(job)


@router.get("/jobs")
def list_jobs(ctx: Ctx, limit: int = 20) -> list[JobView]:
    return [JobView.of(job) for job in ctx.store.list(limit=min(max(limit, 1), 100))]


@router.get("/jobs/{job_id}")
def get_job(ctx: Ctx, job_id: str) -> JobView:
    return JobView.of(_job_or_404(ctx, job_id))


@router.get("/jobs/{job_id}/transcript", response_class=PlainTextResponse)
def get_transcript(ctx: Ctx, job_id: str) -> str:
    job = _job_or_404(ctx, job_id)
    if job.transcript is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "transcript is not ready")
    return job.transcript


@router.get("/jobs/{job_id}/minutes")
def get_minutes(ctx: Ctx, job_id: str) -> Minutes:
    return _minutes_or_409(_job_or_404(ctx, job_id))


@router.put("/jobs/{job_id}/minutes")
def replace_minutes(ctx: Ctx, job_id: str, minutes: Minutes) -> Minutes:
    _minutes_or_409(_job_or_404(ctx, job_id))
    ctx.store.update(job_id, minutes=minutes)
    return minutes


@router.patch("/jobs/{job_id}/action-items/{item_id}")
def update_action_item(ctx: Ctx, job_id: str, item_id: str, patch: ActionItemPatch) -> ActionItem:
    minutes = _minutes_or_409(_job_or_404(ctx, job_id))
    changes = patch.model_dump(exclude_unset=True)
    for index, item in enumerate(minutes.action_items):
        if item.id == item_id:
            updated = ActionItem.model_validate(item.model_dump() | changes)
            minutes.action_items[index] = updated
            ctx.store.update(job_id, minutes=minutes)
            return updated
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"action item {item_id} not found")


@router.delete("/jobs/{job_id}/action-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_action_item(ctx: Ctx, job_id: str, item_id: str) -> None:
    minutes = _minutes_or_409(_job_or_404(ctx, job_id))
    remaining = [item for item in minutes.action_items if item.id != item_id]
    if len(remaining) == len(minutes.action_items):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"action item {item_id} not found")
    minutes.action_items = remaining
    ctx.store.update(job_id, minutes=minutes)


@router.get("/jobs/{job_id}/minutes.md", response_class=PlainTextResponse)
def download_markdown(ctx: Ctx, job_id: str) -> PlainTextResponse:
    job = _job_or_404(ctx, job_id)
    minutes = _minutes_or_409(job)
    return PlainTextResponse(
        render_markdown(minutes),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="minutes-{job.id[:8]}.md"'},
    )


@router.get("/exporters")
def list_exporters(ctx: Ctx) -> list[str]:
    return sorted(ctx.exporters)


@router.post("/jobs/{job_id}/exports/{target}")
def export_minutes(ctx: Ctx, job_id: str, target: str) -> ExportResult:
    minutes = _minutes_or_409(_job_or_404(ctx, job_id))
    exporter = ctx.exporters.get(target)
    if exporter is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"exporter '{target}' is not configured; available: {', '.join(sorted(ctx.exporters))}",
        )
    try:
        return exporter.export(minutes)
    except ExportError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


# --- factory ----------------------------------------------------------------------


def _build_store(settings: Settings) -> JobStore:
    if settings.job_store == "sqlite":
        return SqliteJobStore(settings.sqlite_path)
    return InMemoryJobStore()


def create_app(
    settings: Settings | None = None,
    *,
    transcriber: Transcriber | None = None,
    llm: StructuredLLM | None = None,
    store: JobStore | None = None,
    exporters: dict[str, Exporter] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    pipeline = MinutesPipeline(
        llm or build_llm(settings),
        PipelineConfig(
            chunk_words=settings.chunk_words,
            chunk_overlap_words=settings.chunk_overlap_words,
            max_extraction_attempts=settings.max_review_attempts,
        ),
    )
    store = store or _build_store(settings)
    service = MinutesService(
        transcriber=transcriber or build_transcriber(settings), pipeline=pipeline, store=store
    )

    app = FastAPI(title="Meeting Minutes Agent", version=__version__)
    app.state.context = AppContext(
        settings=settings,
        store=store,
        service=service,
        exporters=exporters if exporters is not None else build_exporters(settings),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app
