"""Offline request, orchestration and ownership checks for the standalone demo."""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import tempfile
import threading
import unittest
from pathlib import Path
from time import monotonic
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from demo.observability import Monitor
from demo.operations import InputError, execute, prepare, steps_for
from demo.schema import (
    DownloadSettings,
    GeminiOptions,
    JobRequest,
    SupadataOptions,
    VisualOptions,
)
from demo.server import Store, StoredFile, Transfer, create_app, disk
from video_context_pipeline import (
    ConfigurationError,
    GeminiSettings,
    MediaArtifact,
    MediaSettings,
    ProviderOutput,
    SupadataSettings,
    VisualRequest,
)
from video_context_pipeline.providers.ytdlp import MediaFormat, MediaInspection

URL = "https://www.youtube.com/watch?v=offline"
EXES = {"node": ["/bin/node"], "ffmpeg": ["/bin/ffmpeg"], "ffprobe": ["/bin/ffprobe"]}
MEDIA = {
    "request_timeout_seconds": 30,
    "runtime_name": "node",
    "runtime_path": "/bin/node",
}
LOCAL = {
    "ffmpeg_path": "/bin/ffmpeg",
    "ffprobe_path": "/bin/ffprobe",
    "timeout_seconds": 30,
}
TRANSCRIPT = {
    "format": "transcript_text",
    "settings": {
        "request_timeout_seconds": 30,
        "job_timeout_seconds": 60,
        "poll_interval_seconds": 1,
        "max_retries": 0,
        "retry_delay_seconds": 1,
    },
}
VISUAL = {
    "format": "video_text",
    "timestamp_mode": "none",
    "analyzed_start_seconds": 0,
    "settings": {
        "model": "gemini-3.8-flash",
        "media_resolution": "low",
        "thinking_level": "low",
        "processing_mode": "static",
        "static_fps": 1,
        "request_timeout_seconds": 30,
        "max_retries": 0,
        "retry_backoff_seconds": 1,
        "file_upload_threshold_bytes": 1000,
        "file_poll_deadline_seconds": 60,
        "file_poll_interval_seconds": 1,
    },
}
TRANSFORM = {"codec": "mp3", "container": "mp3", "bitrate_kbps": 128}


def output(fmt, data):
    return ProviderOutput(fmt, data, "offline-double", "content")


class RequestTests(unittest.TestCase):
    def prepare(self, payload):
        return prepare(
            JobRequest.model_validate(payload),
            Path("/tmp/offline-demo-test"),
            EXES,
            lambda _: MediaArtifact(Path("/tmp/caller.mp4"), "video/mp4", 10),
        )

    def test_public_configuration_fields_are_covered(self):
        self.assertEqual(
            set(GeminiOptions.model_fields),
            {f.name for f in dataclasses.fields(GeminiSettings)} - {"api_key"},
        )
        self.assertEqual(
            set(SupadataOptions.model_fields),
            {f.name for f in dataclasses.fields(SupadataSettings)} - {"api_key"},
        )
        self.assertEqual(
            set(VisualOptions.model_fields) - {"transcript_context"},
            {f.name for f in dataclasses.fields(VisualRequest)},
        )
        self.assertEqual(
            {f.name for f in dataclasses.fields(MediaSettings)},
            {"request_timeout_seconds", "cookie_file", "output_directory"},
        )
        self.assertEqual(
            set(DownloadSettings.model_fields),
            {
                "request_timeout_seconds",
                "runtime_name",
                "runtime_path",
                "cookie_text",
                "cookie_artifact_id",
            },
        )

    def test_visual_windows_and_media_settings_translate_explicitly(self):
        visual = copy.deepcopy(VISUAL)
        visual.update(
            format="video_events",
            timestamp_mode="windows",
            analyzed_end_seconds=10,
            windows=[{"start_seconds": 0, "end_seconds": 10}],
            inspection_windows=[{"start_seconds": 1, "end_seconds": 2}],
        )
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-only"}):
            prepared = self.prepare(
                {"action": "visual", "input_artifact_id": "input", "visual": visual}
            )
        self.assertEqual(prepared.visual.windows[0].end_seconds, 10)
        self.assertEqual(prepared.visual.inspection_windows[0].start_seconds, 1)
        prepared = self.prepare(
            {
                "action": "inspect",
                "url": URL,
                "media": {**MEDIA, "cookie_text": "transient"},
            }
        )
        self.assertEqual(prepared.media.request_timeout_seconds, 30)
        self.assertEqual(prepared.media.output_directory, prepared.directory)
        self.assertEqual(prepared.media.cookie_file, prepared.directory / "cookies.txt")

    def test_blank_invalid_extra_and_irrelevant_settings(self):
        valid = {
            "action": "download",
            "url": URL,
            "media": MEDIA,
            "selected_format_id": "18",
        }
        for change in (
            {"url": " "},
            {"selected_format_id": ""},
            {"surprise": True},
            {"media": {**MEDIA, "request_timeout_seconds": "30"}},
            {"media": {**MEDIA, "request_timeout_seconds": 0}},
            {"media": {**MEDIA, "secret": "private"}},
        ):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                JobRequest.model_validate({**valid, **change})
        for change in (
            {"url": "https://example.org/private"},
            {"media": {**MEDIA, "runtime_path": "/unknown"}},
            {"local": LOCAL},
        ):
            with self.subTest(change=change), self.assertRaises(InputError):
                self.prepare({**valid, **change})

    def test_credentials_are_only_required_for_selected_providers(self):
        with patch.dict("os.environ", {}, clear=True):
            self.prepare({"action": "inspect", "url": URL, "media": MEDIA})
            with self.assertRaisesRegex(InputError, "SUPADATA_API_KEY"):
                self.prepare(
                    {"action": "transcribe", "url": URL, "transcript": TRANSCRIPT}
                )
        with patch.dict("os.environ", {"SUPADATA_API_KEY": "test-only"}, clear=True):
            prepared = self.prepare(
                {"action": "transcribe", "url": URL, "transcript": TRANSCRIPT}
            )
            self.assertIsNotNone(prepared.transcript)
            self.assertIsNone(prepared.visual)
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-only"}, clear=True):
            self.assertIsNotNone(
                self.prepare(
                    {"action": "visual", "input_artifact_id": "input", "visual": VISUAL}
                ).visual
            )

    def test_conditional_configuration_rejected(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-only"}):
            visual = copy.deepcopy(VISUAL)
            visual["settings"]["static_fps"] = None
            with self.assertRaises(ConfigurationError):
                self.prepare(
                    {"action": "visual", "input_artifact_id": "input", "visual": visual}
                )
        with self.assertRaises(InputError):
            self.prepare(
                {
                    "action": "extract",
                    "input_artifact_id": "input",
                    "local": LOCAL,
                    "transform": {**TRANSFORM, "container": "m4a"},
                }
            )


class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(root=Path(self.temp.name) / "store")
        await self.store.start()
        self.store.executables = EXES
        self.session, _ = await self.store.session(None, create=True)

    async def asyncTearDown(self):
        await self.store.close()
        self.temp.cleanup()

    def file(self, *, kind="media"):
        folder = self.session.root / (
            "cookie-input" if kind == "cookie" else "caller-input"
        )
        folder.mkdir(exist_ok=True)
        path = folder / ("cookies.txt" if kind == "cookie" else "input.mp4")
        path.write_bytes(b"caller-owned-content")
        item = StoredFile(
            kind,
            MediaArtifact(path, "video/mp4"),
            path.name,
            path.stat().st_size,
            monotonic() + 100,
            kind=kind,
        )
        self.session.files[item.id] = item
        return item

    async def test_queued_cancellation_releases_inputs(self):
        item = self.file()
        called = False

        async def runner(*_):
            nonlocal called
            called = True

        self.store.runner = runner
        job = await self.store.submit(
            self.session,
            JobRequest(action="probe", input_artifact_id=item.id, local=LOCAL),
        )
        self.store.cancel(job)
        await job.task
        self.assertFalse(called)
        self.assertEqual(job.state, "cancelled")
        self.assertEqual(item.pins, 0)
        self.assertTrue(item.media.path.exists())

    async def test_cancellation_waits_for_blocking_work_before_cleanup(self):
        started, release = threading.Event(), threading.Event()

        def blocking(directory):
            started.set()
            release.wait(5)
            (directory / "late.tmp").write_bytes(b"temporary")

        async def runner(prepared, monitor):
            await disk(blocking, prepared.directory)

        self.store.runner = runner
        job = await self.store.submit(
            self.session, JobRequest(action="inspect", url=URL, media=MEDIA)
        )
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 3))
            self.store.cancel(job)
            await asyncio.sleep(0.02)
            self.assertEqual(job.state, "cancelling")
            self.assertTrue(job.directory.exists())
            self.assertFalse(job.task.done())
        finally:
            release.set()
        await asyncio.wait_for(job.task, 3)
        self.assertEqual(job.state, "cancelled")
        self.assertFalse(job.directory.exists())

    async def test_failure_never_publishes_staged_outputs(self):
        async def runner(prepared, monitor):
            path = prepared.directory / "partial.mp3"
            path.write_bytes(b"partial")
            return [
                MediaArtifact(path, "audio/mpeg"),
                MediaArtifact(Path(self.temp.name) / "missing", "audio/mpeg"),
            ]

        self.store.runner = runner
        job = await self.store.submit(
            self.session, JobRequest(action="inspect", url=URL, media=MEDIA)
        )
        await job.task
        self.assertEqual(job.state, "failed")
        self.assertIsNone(job.info().result)
        self.assertFalse(self.session.files)
        self.assertFalse(job.directory.exists())

    async def test_expiry_preserves_active_job_input(self):
        item = self.file()
        entered, release = asyncio.Event(), asyncio.Event()

        async def runner(*_):
            entered.set()
            await release.wait()
            return {"ok": True}

        self.store.runner = runner
        job = await self.store.submit(
            self.session,
            JobRequest(action="probe", input_artifact_id=item.id, local=LOCAL),
        )
        await entered.wait()
        item.expires = 0
        await self.store.reap()
        self.assertTrue(item.media.path.exists())
        self.store.cancel(job)
        await job.task
        await self.store.reap()
        self.assertFalse(item.media.path.exists())

    async def test_transfer_pins_expired_artifact_until_send_finishes(self):
        item = self.file()
        transfer = Transfer(item, preview=False)
        item.expires = 0
        await self.store.reap()
        self.assertTrue(item.media.path.exists())
        with self.assertRaises(HTTPException) as failure:
            await self.store.clear(self.session)
        self.assertEqual(failure.exception.status_code, 409)
        sent = []

        async def send(message):
            sent.append(message)
            await self.store.reap()
            self.assertTrue(item.media.path.exists())

        async def receive():
            return {"type": "http.disconnect"}

        await transfer({"type": "http", "method": "GET", "headers": []}, receive, send)
        self.assertTrue(any(m["type"] == "http.response.body" for m in sent))
        self.assertEqual(item.pins, 0)
        await self.store.reap()
        self.assertFalse(item.media.path.exists())

    async def test_cookie_inputs_are_transient_on_success_failure_and_cancel(self):
        for mode in ("success", "failure", "cancel"):
            with self.subTest(mode=mode):
                item = self.file(kind="cookie")

                async def runner(prepared, monitor):
                    self.assertTrue(prepared.cookie_path.exists())
                    if mode == "failure":
                        raise RuntimeError("private cookie content")
                    return {"ok": True}

                self.store.runner = runner
                job = await self.store.submit(
                    self.session,
                    JobRequest(
                        action="inspect",
                        url=URL,
                        media={**MEDIA, "cookie_artifact_id": item.id},
                    ),
                )
                if mode == "cancel":
                    self.store.cancel(job)
                await job.task
                self.assertNotIn(item.id, self.session.files)
                self.assertFalse(item.media.path.exists())

        async def pasted(prepared, monitor):
            self.assertEqual(prepared.cookie_path.read_text(), "private pasted cookie")
            return {"ok": True}

        self.store.runner = pasted
        job = await self.store.submit(
            self.session,
            JobRequest(
                action="inspect",
                url=URL,
                media={**MEDIA, "cookie_text": "private pasted cookie"},
            ),
        )
        await job.task
        self.assertEqual(job.state, "completed")
        self.assertFalse(job.directory.exists())

    async def test_inspected_audio_plan_approval_conversion_and_source_art(self):
        calls = []
        inspection = MediaInspection(
            (MediaFormat("opus-source", "webm", "opus", None, 128, None, None, None),),
            10,
            "Offline",
            None,
        )

        class MediaDouble:
            def __init__(self, **kwargs):
                pass

            async def inspect_media(self, *args):
                calls.append("inspect")
                return inspection

            async def download(self, url, request):
                calls.append(("download", request.selected_format_id))
                path = request.settings.output_directory / "source.webm"
                path.write_bytes(b"source")
                return output("media", MediaArtifact(path, "audio/webm"))

            async def download_thumbnail(self, url, settings):
                calls.append("thumbnail")
                path = settings.output_directory / "cover.jpg"
                path.write_bytes(b"image")
                return output("media", MediaArtifact(path, "image/jpeg"))

        class ToolsDouble:
            def __init__(self, **kwargs):
                pass

            async def convert_audio(self, source, **kwargs):
                calls.append("convert")
                kwargs["destination"].write_bytes(b"mp3")
                return MediaArtifact(kwargs["destination"], "audio/mpeg")

            async def enrich_metadata(self, source, **kwargs):
                calls.append("enrich")
                assert kwargs["thumbnail"].exists()
                kwargs["destination"].write_bytes(b"tagged")
                return MediaArtifact(kwargs["destination"], "audio/mpeg")

        self.store.runner = execute
        with (
            patch("demo.operations.YtDlpMediaProvider", MediaDouble),
            patch("demo.operations.FFmpegMediaTools", ToolsDouble),
        ):
            plan = await self.store.submit(
                self.session,
                JobRequest(
                    action="audio_plan",
                    url=URL,
                    media=MEDIA,
                    compatible_bitrate_ratio=0.8,
                ),
            )
            await plan.task
            self.assertEqual(plan.state, "completed")
            self.assertTrue(plan.plan.plan.requires_mp3_conversion)
            payload = {
                "action": "audio_workflow",
                "url": URL,
                "media": MEDIA,
                "plan_job_id": plan.id,
            }
            with self.assertRaises(InputError):
                await self.store.submit(self.session, JobRequest(**payload))
            with self.assertRaises(InputError):
                await self.store.submit(
                    self.session,
                    JobRequest(
                        **{
                            **payload,
                            "url": URL + "other",
                            "local": LOCAL,
                            "transform": TRANSFORM,
                        }
                    ),
                )
            with self.assertRaises(InputError):
                await self.store.submit(
                    self.session,
                    JobRequest(
                        **payload,
                        transform=TRANSFORM,
                        enrichment={"metadata": {}, "source_cover": True},
                    ),
                )
            invalid_cover = self.file()
            with self.assertRaises(InputError):
                await self.store.submit(
                    self.session,
                    JobRequest(
                        **payload,
                        local=LOCAL,
                        transform=TRANSFORM,
                        enrichment={
                            "metadata": {},
                            "cover_artifact_id": invalid_cover.id,
                        },
                    ),
                )
            self.assertEqual(invalid_cover.pins, 0)
            self.session.files.pop(invalid_cover.id)
            self.assertEqual(calls, ["inspect"])
            job = await self.store.submit(
                self.session,
                JobRequest(
                    **payload,
                    local=LOCAL,
                    transform=TRANSFORM,
                    enrichment={"metadata": {"title": "Offline"}, "source_cover": True},
                ),
            )
            await job.task
            self.assertEqual(job.state, "completed", job.error)
            self.assertEqual(
                calls,
                [
                    "inspect",
                    ("download", plan.plan.plan.selected_format_id),
                    "convert",
                    "thumbnail",
                    "enrich",
                ],
            )
            self.assertEqual(len(self.session.files), 1)


class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_isolation_validation_and_operational_log_redaction(self):
        async def runner(prepared, monitor):
            monitor.logger().info(
                "private-message",
                extra={
                    "vcp_fields": {
                        "stage": "private-stage",
                        "status": "private-status",
                        "bytes": 12,
                        "url": "private-url",
                        "api_key": "private-key",
                        "usage": 100,
                        "cost": 2,
                        "fps": "private-fps",
                    }
                },
            )
            await asyncio.sleep(0)
            raise RuntimeError("private-exception")

        store = Store(runner=runner)
        app = create_app(store)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as first,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as second,
        ):
            await first.get("/api/capabilities")
            await second.get("/api/capabilities")
            store.executables = EXES
            upload = await first.post(
                "/api/uploads", files={"file": ("input.mp4", b"caller", "video/mp4")}
            )
            artifact_id = upload.json()["id"]
            self.assertEqual(
                (
                    await second.get(f"/api/artifacts/{artifact_id}/download")
                ).status_code,
                404,
            )
            self.assertEqual(
                (await second.delete(f"/api/artifacts/{artifact_id}")).status_code, 404
            )
            invalid = await first.post(
                "/api/jobs", json={"action": "private-action", "url": "private-url"}
            )
            self.assertEqual(invalid.status_code, 422)
            self.assertNotIn("private-", invalid.text)
            submitted = await first.post(
                "/api/jobs", json={"action": "inspect", "url": URL, "media": MEDIA}
            )
            self.assertEqual(submitted.status_code, 200, submitted.text)
            job_id = submitted.json()["id"]
            await store.sessions[first.cookies["vcp_session"]].jobs[job_id].task
            status = await first.get(f"/api/jobs/{job_id}")
            self.assertEqual(status.json()["state"], "failed")
            self.assertNotIn("private-", status.text)
            self.assertTrue(
                any(log.get("bytes") == 12 for log in status.json()["logs"])
            )
            self.assertEqual((await second.get(f"/api/jobs/{job_id}")).status_code, 404)
            self.assertEqual(
                (await second.post(f"/api/jobs/{job_id}/cancel")).status_code, 404
            )


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_first_stage_and_real_barrier_before_visual(self):
        started = {
            name: asyncio.Event() for name in ("metadata", "transcript", "download")
        }
        release = {name: asyncio.Event() for name in started}
        visual_started = asyncio.Event()

        async def stage(name, value):
            started[name].set()
            await release[name].wait()
            return value

        class Metadata:
            def __init__(self, **kwargs):
                pass

            async def inspect(self, url):
                return await stage("metadata", output("metadata", {"title": "Offline"}))

        class Transcript:
            def __init__(self, **kwargs):
                pass

            async def transcribe(self, *args):
                return await stage(
                    "transcript", output("transcript_text", "readable context")
                )

        class Media:
            def __init__(self, **kwargs):
                pass

            async def download(self, url, request):
                path = request.settings.output_directory / "video.mp4"
                path.write_bytes(b"video")
                return await stage(
                    "download", output("media", MediaArtifact(path, "video/mp4", 10))
                )

        class Visual:
            def __init__(self, **kwargs):
                pass

            async def understand(self, media, request, *, transcript_context):
                assert all(event.is_set() for event in release.values())
                assert transcript_context == "readable context"
                visual_started.set()
                return output("video_text", "description")

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(
                "os.environ", {"GEMINI_API_KEY": "test", "SUPADATA_API_KEY": "test"}
            ),
            patch("demo.operations.YtDlpMediaProvider", Media),
            patch("demo.operations.YtDlpMetadataProvider", Metadata),
            patch("demo.operations.SupadataProvider", Transcript),
            patch("demo.operations.GeminiProvider", Visual),
        ):
            prepared = prepare(
                JobRequest(
                    action="pipeline",
                    url=URL,
                    media=MEDIA,
                    transcript=TRANSCRIPT,
                    visual=VISUAL,
                    pipeline={
                        "metadata": True,
                        "transcript": True,
                        "visual": True,
                        "media": True,
                        "include_transcript_context": True,
                        "selected_format_id": "18",
                        "visual_format_id": "18",
                    },
                ),
                Path(folder),
                EXES,
                lambda _: None,
            )
            monitor = Monitor("offline", steps_for(prepared))
            task = asyncio.create_task(execute(prepared, monitor))
            try:
                await asyncio.wait_for(
                    asyncio.gather(*(e.wait() for e in started.values())), 3
                )
                release["transcript"].set()
                release["download"].set()
                await asyncio.sleep(0.02)
                self.assertFalse(visual_started.is_set())
                self.assertEqual(monitor.steps["barrier"].state, "pending")
                release["metadata"].set()
                result = await asyncio.wait_for(task, 3)
                self.assertEqual(
                    set(result.outputs), {"metadata", "transcript", "media", "visual"}
                )
                self.assertEqual(monitor.steps["barrier"].state, "completed")
            finally:
                for event in release.values():
                    event.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
