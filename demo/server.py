"""Single-process, session-scoped web demo with owned temporary artifacts."""

from __future__ import annotations

import asyncio
import dataclasses
import mimetypes
import secrets
import shutil
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from time import monotonic
from typing import Any, Literal

from fastapi import (
    Cookie,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from video_context_pipeline import ConfigurationError, MediaArtifact, ValidationError
from video_context_pipeline.logging import request_correlation

from .diagnostics import failure_message
from .observability import Monitor
from .operations import (
    InputError,
    Prepared,
    ReviewedPlan,
    execute,
    prepare,
    steps_for,
    url_digest,
)
from .schema import Action, ArtifactInfo, JobCreated, JobInfo, JobRequest, State

RETENTION_SECONDS = 3600
COOKIE = "vcp_session"
ACTIVE = {"pending", "running", "cancelling"}
Runner = Callable[[Prepared, Monitor], Awaitable[Any]]


async def disk(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Finish owned blocking I/O before cancellation can trigger cleanup."""
    worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        await worker
        raise


def identifier() -> str:
    return secrets.token_urlsafe(24)


@dataclass
class StoredFile:
    id: str
    media: MediaArtifact
    filename: str
    size: int
    expires: float
    kind: str = "media"
    pins: int = 0
    consumed: bool = False

    def info(self) -> ArtifactInfo:
        return ArtifactInfo(
            id=self.id,
            filename=self.filename,
            media_type=self.media.media_type,
            size_bytes=self.size,
            duration_seconds=self.media.duration_seconds,
            download_url=f"/api/artifacts/{self.id}/download",
            preview_url=f"/api/artifacts/{self.id}/preview",
        )


@dataclass
class Job:
    id: str
    action: Action
    directory: Path
    monitor: Monitor
    state: State = "pending"
    task: asyncio.Task[None] | None = None
    result: Any = None
    error: str | None = None
    finished: float | None = None
    inputs: list[StoredFile] = field(default_factory=list)
    plan: ReviewedPlan | None = None
    plan_pins: int = 0
    finalizing: bool = False

    def info(self) -> JobInfo:
        return JobInfo(
            id=self.id,
            action=self.action,
            state=self.state,
            elapsed_seconds=(self.finished or monotonic()) - self.monitor.created,
            steps=[step.info() for step in self.monitor.steps.values()],
            logs=list(self.monitor.logs),
            result=self.result if self.state == "completed" else None,
            error=self.error,
        )


@dataclass
class Session:
    id: str
    root: Path
    files: dict[str, StoredFile] = field(default_factory=dict)
    jobs: dict[str, Job] = field(default_factory=dict)
    touched: float = field(default_factory=monotonic)
    uploads: int = 0
    clearing: bool = False


def prune(directory: Path, keep: set[Path]) -> None:
    if not keep:
        shutil.rmtree(directory, ignore_errors=True)
        return
    for path in directory.rglob("*"):
        if path.is_file() and path not in keep:
            path.unlink(missing_ok=True)
    for path in sorted(
        directory.rglob("*"), key=lambda item: len(item.parts), reverse=True
    ):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


class Store:
    def __init__(self, *, runner: Runner = execute, root: Path | None = None) -> None:
        self.root = root
        self.runner = runner
        self.sessions: dict[str, Session] = {}
        self.executables: dict[str, list[str]] = {}

    async def start(self) -> None:
        if self.root is None:
            self.root = Path(await disk(tempfile.mkdtemp, prefix="vcp-demo-"))
        else:
            await disk(self.root.mkdir, parents=True, exist_ok=True)

        def discover() -> dict[str, list[str]]:
            return {
                name: [path] if (path := shutil.which(name)) else []
                for name in ("ffmpeg", "ffprobe", "node", "deno")
            }

        self.executables = await disk(discover)

    async def session(
        self, cookie: str | None, *, create: bool = False
    ) -> tuple[Session, bool]:
        existing = self.sessions.get(cookie or "")
        if existing:
            if existing.clearing:
                raise HTTPException(409, "Session cleanup is in progress.")
            existing.touched = monotonic()
            return existing, False
        if not create:
            raise HTTPException(404, "Session unavailable; reload the page.")
        assert self.root is not None
        key = identifier()
        session = Session(key, self.root / key)
        await disk(session.root.mkdir, parents=True)
        self.sessions[key] = session
        return session, True

    def file(self, session: Session, key: str, *, cookies: bool = False) -> StoredFile:
        item = session.files.get(key)
        if (
            item is None
            or (item.kind == "cookie" and not cookies)
            or (item.expires <= monotonic() and item.pins == 0)
        ):
            raise HTTPException(404, "Artifact unavailable or expired.")
        return item

    def job(self, session: Session, key: str) -> Job:
        job = session.jobs.get(key)
        if job is None:
            raise HTTPException(404, "Job unavailable.")
        return job

    async def submit(self, session: Session, request: JobRequest) -> Job:
        key = identifier()
        directory = session.root / key
        inputs: dict[str, StoredFile] = {}

        def artifact(artifact_id: str) -> MediaArtifact:
            item = self.file(session, artifact_id, cookies=True)
            is_cookie = (
                request.media is not None
                and request.media.cookie_artifact_id == artifact_id
            )
            if is_cookie != (item.kind == "cookie"):
                raise InputError(
                    "Use a cookie upload for source cookies and a media upload for media inputs."
                )
            inputs[item.id] = item
            return dataclasses.replace(
                item.media, owned=False, owned_directory=None, dependencies=()
            )

        previous = (
            self.job(session, request.plan_job_id) if request.plan_job_id else None
        )
        if previous and (
            previous.state != "completed"
            or previous.plan is None
            or previous.finished is None
            or monotonic() - previous.finished >= RETENTION_SECONDS
        ):
            raise InputError(
                "Review a new completed audio plan before running the workflow."
            )
        try:
            prepared = prepare(
                request,
                directory,
                self.executables,
                artifact,
                previous.plan if previous else None,
            )
        except (ConfigurationError, ValidationError) as exc:
            # These settings errors come from validated primitive fields, never providers.
            raise InputError(str(exc)) from None
        monitor = Monitor(key, steps_for(prepared))
        job = Job(key, request.action, directory, monitor, inputs=list(inputs.values()))
        for item in job.inputs:
            item.pins += 1
            if item.kind == "cookie":
                item.consumed = True
        if previous:
            previous.plan_pins += 1
        session.jobs[key] = job

        async def run() -> None:
            terminal: State = "failed"
            staged: list[StoredFile] = []
            try:
                if job.state == "cancelling":
                    raise asyncio.CancelledError()
                job.state = "running"
                monitor.event("job", "running")
                await disk(directory.mkdir, parents=True)
                if request.media and request.media.cookie_text is not None:
                    await disk(
                        (directory / "cookies.txt").write_text,
                        request.media.cookie_text,
                        encoding="utf-8",
                    )
                with request_correlation(key):
                    value = await self.runner(prepared, monitor)
                result = await self.serialize(value, directory, staged)
                if request.action == "audio_plan":
                    job.plan = ReviewedPlan(
                        url_digest(request.url or ""), value["plan"]
                    )
                # No cancellation interrupts the transaction after this boundary.
                job.finalizing = True
                await disk(prune, directory, {item.media.path for item in staged})
                if request.action == "probe" and request.input_artifact_id:
                    item = session.files[request.input_artifact_id]
                    item.media = dataclasses.replace(
                        item.media,
                        media_type=value.media_type,
                        duration_seconds=value.duration_seconds,
                    )
                job.result = result
                terminal = "completed"
            except asyncio.CancelledError:
                terminal = "cancelled"
            except Exception as error:
                job.error = failure_message(error)
            finally:
                job.finalizing = True
                if terminal != "completed":
                    job.result = None
                    job.plan = None
                    for item in staged:
                        session.files.pop(item.id, None)
                    await disk(shutil.rmtree, directory, True)
                for item in job.inputs:
                    item.pins -= 1
                    if item.kind == "cookie" and item.pins == 0:
                        session.files.pop(item.id, None)
                        await disk(shutil.rmtree, item.media.path.parent, True)
                job.inputs.clear()
                if previous:
                    previous.plan_pins -= 1
                if terminal == "completed":
                    # Publish artifacts together only after all cleanup has finished.
                    completed = monotonic()
                    for item in staged:
                        item.expires = completed + RETENTION_SECONDS
                        session.files[item.id] = item
                monitor.event("cleanup", "completed")
                monitor.finish(terminal)
                job.finished, job.state = monotonic(), terminal

        job.task = asyncio.create_task(run(), name=f"demo-{key}")
        return job

    async def serialize(
        self, value: Any, directory: Path, staged: list[StoredFile]
    ) -> Any:
        if isinstance(value, MediaArtifact):
            resolved = await disk(value.path.resolve)
            if not resolved.is_relative_to(directory):
                raise RuntimeError("Output is outside the owned workspace")
            for item in staged:
                if item.media.path == value.path:
                    return item.info().model_dump()
            size = (await disk(value.path.stat)).st_size
            item = StoredFile(identifier(), value, value.path.name, size, 0)
            staged.append(item)
            return item.info().model_dump()
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {
                item.name: await self.serialize(
                    getattr(value, item.name), directory, staged
                )
                for item in dataclasses.fields(value)
            }
        if isinstance(value, Mapping):
            return {
                str(key): await self.serialize(item, directory, staged)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [await self.serialize(item, directory, staged) for item in value]
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Path):
            return None
        return value

    def cancel(self, job: Job) -> None:
        if job.state in {"pending", "running"} and not job.finalizing:
            running = job.state == "running"
            job.state = "cancelling"
            job.monitor.cancelling()
            # A queued task must enter its finally block to release inputs.
            if running and job.task:
                job.task.cancel()

    async def reap(self) -> None:
        now = monotonic()
        for session in list(self.sessions.values()):
            if session.clearing or session.uploads:
                continue
            for item in list(session.files.values()):
                if item.pins == 0 and item.expires <= now:
                    session.files.pop(item.id, None)
                    await disk(item.media.path.unlink, missing_ok=True)
            for job in list(session.jobs.values()):
                if (
                    job.finished is not None
                    and job.plan_pins == 0
                    and job.finished + RETENTION_SECONDS <= now
                ):
                    if not any(
                        item.media.path.is_relative_to(job.directory)
                        for item in session.files.values()
                    ):
                        session.jobs.pop(job.id, None)
                        await disk(shutil.rmtree, job.directory, True)
            if (
                not session.files
                and not session.jobs
                and session.touched + RETENTION_SECONDS <= now
            ):
                self.sessions.pop(session.id, None)
                await disk(shutil.rmtree, session.root, True)

    async def clear(self, session: Session, *, shutdown: bool = False) -> None:
        reserved: dict[str, int] = {}
        for job in session.jobs.values():
            for item in job.inputs:
                reserved[item.id] = reserved.get(item.id, 0) + 1
        if not shutdown and (
            session.uploads
            or any(
                item.pins > reserved.get(item.id, 0) for item in session.files.values()
            )
        ):
            raise HTTPException(409, "An upload or file transfer is active.")
        session.clearing = True
        try:
            pending = []
            for job in session.jobs.values():
                self.cancel(job)
                if job.task:
                    pending.append(job.task)
            await asyncio.gather(*pending, return_exceptions=True)
            await disk(shutil.rmtree, session.root, True)
            self.sessions.pop(session.id, None)
        finally:
            session.clearing = False

    async def close(self) -> None:
        for session in list(self.sessions.values()):
            await self.clear(session, shutdown=True)
        if self.root:
            await disk(shutil.rmtree, self.root, True)


class Transfer(FileResponse):
    def __init__(self, item: StoredFile, *, preview: bool) -> None:
        super().__init__(
            item.media.path,
            filename=item.filename,
            media_type=item.media.media_type,
            content_disposition_type="inline" if preview else "attachment",
        )
        self.item = item
        item.pins += 1

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.item.pins -= 1


def create_app(store: Store | None = None) -> FastAPI:
    store = store or Store()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await store.start()
        stop = asyncio.Event()

        async def reaper() -> None:
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), 30)
                except TimeoutError:
                    await store.reap()

        task = asyncio.create_task(reaper())
        try:
            yield
        finally:
            stop.set()
            await task
            await store.close()

    app = FastAPI(title="Video Context Pipeline demo", lifespan=lifespan)
    app.state.store = store
    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.middleware("http")
    async def response_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(InputError)
    async def input_error(request: Request, error: InputError) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def schema_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        # Pydantic's input, ctx and message may echo private user values.
        fields = [
            ".".join(str(part) for part in item["loc"] if isinstance(part, (str, int)))
            for item in error.errors()
        ]
        return JSONResponse(
            {
                "detail": "Missing or invalid settings. Check the required fields and supported values.",
                "fields": fields,
            },
            status_code=422,
        )

    async def current(cookie: str | None) -> Session:
        return (await store.session(cookie))[0]

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static / "index.html")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/capabilities")
    async def capabilities(
        response: Response,
        request: Request,
        cookie: str | None = Cookie(None, alias=COOKIE),
    ) -> dict[str, Any]:
        import os

        session, created = await store.session(cookie, create=True)
        if created:
            response.set_cookie(
                COOKIE,
                session.id,
                httponly=True,
                samesite="strict",
                secure=request.url.scheme == "https",
            )
        return {
            "credentials": {
                "gemini": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
                "supadata": bool(os.environ.get("SUPADATA_API_KEY", "").strip()),
            },
            "executables": store.executables,
            "schema": JobRequest.model_json_schema(),
            "retention_seconds": RETENTION_SECONDS,
        }

    @app.post("/api/uploads", response_model=ArtifactInfo)
    async def upload(
        file: UploadFile = File(...),
        duration_seconds: float | None = Form(None),
        kind: Literal["media", "cookie"] = Form("media"),
        cookie: str | None = Cookie(None, alias=COOKIE),
    ) -> ArtifactInfo:
        import math

        session = await current(cookie)
        if duration_seconds is not None and (
            not math.isfinite(duration_seconds) or duration_seconds < 0
        ):
            await file.close()
            raise InputError("duration_seconds must be finite and non-negative.")
        key = identifier()
        directory = session.root / f"upload-{key}"
        # Keep recognizable extensions, never trust filenames as paths.
        name = Path((file.filename or "upload.bin").replace("\\", "/")).name
        if name in {"", ".", ".."}:
            name = "upload.bin"
        target = directory / name
        session.uploads += 1
        try:
            await disk(directory.mkdir)
            handle = await disk(target.open, "wb")
            size = 0
            try:
                while chunk := await file.read(1024 * 1024):
                    await disk(handle.write, chunk)
                    size += len(chunk)
            finally:
                await disk(handle.close)
            media_type = (
                mimetypes.guess_type(name)[0]
                or file.content_type
                or "application/octet-stream"
            )
            media = MediaArtifact(
                target,
                media_type,
                duration_seconds,
                owned=True,
                owned_directory=directory,
            )
            item = StoredFile(
                key, media, name, size, monotonic() + RETENTION_SECONDS, kind
            )
            session.files[key] = item
            return item.info()
        except BaseException:
            await disk(shutil.rmtree, directory, True)
            raise
        finally:
            session.uploads -= 1
            await file.close()

    @app.post("/api/jobs", response_model=JobCreated)
    async def submit(
        payload: JobRequest, cookie: str | None = Cookie(None, alias=COOKIE)
    ) -> JobCreated:
        job = await store.submit(await current(cookie), payload)
        return JobCreated(id=job.id, state=job.state)

    @app.get("/api/jobs/{job_id}", response_model=JobInfo)
    async def status(
        job_id: str, cookie: str | None = Cookie(None, alias=COOKIE)
    ) -> JobInfo:
        return store.job(await current(cookie), job_id).info()

    @app.post("/api/jobs/{job_id}/cancel", response_model=JobCreated)
    async def cancel(
        job_id: str, cookie: str | None = Cookie(None, alias=COOKIE)
    ) -> JobCreated:
        job = store.job(await current(cookie), job_id)
        store.cancel(job)
        return JobCreated(id=job.id, state=job.state)

    @app.get("/api/artifacts", response_model=list[ArtifactInfo])
    async def artifacts(
        cookie: str | None = Cookie(None, alias=COOKIE),
    ) -> list[ArtifactInfo]:
        session = await current(cookie)
        return [
            item.info()
            for item in session.files.values()
            if item.kind != "cookie" and (item.pins or item.expires > monotonic())
        ]

    @app.get("/api/artifacts/{artifact_id}/download")
    async def download(
        artifact_id: str, cookie: str | None = Cookie(None, alias=COOKIE)
    ) -> FileResponse:
        return Transfer(store.file(await current(cookie), artifact_id), preview=False)

    @app.get("/api/artifacts/{artifact_id}/preview")
    async def preview(
        artifact_id: str, cookie: str | None = Cookie(None, alias=COOKIE)
    ) -> FileResponse:
        item = store.file(await current(cookie), artifact_id)
        if (
            not item.media.media_type.startswith(("audio/", "video/", "image/"))
            or item.media.media_type == "image/svg+xml"
        ):
            raise HTTPException(415, "This artifact is available as a download only.")
        response = Transfer(item, preview=True)
        response.headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
        return response

    @app.delete("/api/artifacts/{artifact_id}", status_code=204)
    async def delete(
        artifact_id: str, cookie: str | None = Cookie(None, alias=COOKIE)
    ) -> Response:
        session = await current(cookie)
        item = store.file(session, artifact_id, cookies=True)
        if item.pins:
            raise HTTPException(409, "Artifact is active.")
        session.files.pop(item.id, None)
        await disk(item.media.path.unlink, missing_ok=True)
        return Response(status_code=204)

    @app.delete("/api/session", status_code=204)
    async def clear(cookie: str | None = Cookie(None, alias=COOKIE)) -> Response:
        await store.clear(await current(cookie))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE)
        return response

    return app


app = create_app()
