from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from video_context_pipeline.config import (
    GeminiModel,
    GeminiProcessingMode,
    GeminiResolution,
    GeminiSettings,
    SupadataSettings,
    TranscriptRequest,
    VisualRequest,
)
from video_context_pipeline.errors import ProviderError, ValidationError
from video_context_pipeline.models import (
    MediaArtifact,
    OutputFormat,
    TimestampMode,
    TimeWindow,
)
from video_context_pipeline.providers.gemini import GeminiProvider
from video_context_pipeline.providers.supadata import SupadataProvider


def gemini_settings(
    *,
    mode: GeminiProcessingMode = GeminiProcessingMode.STATIC,
    threshold: int = 1_000_000,
) -> GeminiSettings:
    return GeminiSettings(
        "key",
        GeminiModel.FLASH_3_8,
        GeminiResolution.LOW,
        "low",
        mode,
        1 if mode is not GeminiProcessingMode.AGENTIC else None,
        10 if mode is GeminiProcessingMode.AUTOMATIC else None,
        5,
        1,
        0.001,
        threshold,
        5,
        0.001,
    )


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_supadata_reports_queue_phases_and_incomplete_terminal_response(self):
        states = iter(
            [
                {"jobId": "private-job", "status": "queued"},
                {"status": "active"},
                {"status": "completed"},
            ]
        )

        def handler(request):
            return httpx.Response(200, json=next(states))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertLogs(
                "video_context_pipeline.providers.supadata", level="INFO"
            ) as logs:
                with self.assertRaisesRegex(
                    ProviderError, "completed a job without transcript content"
                ):
                    await SupadataProvider(client=client).transcribe(
                        "https://www.instagram.com/p/example/",
                        TranscriptRequest(
                            OutputFormat.TRANSCRIPT_TEXT,
                            SupadataSettings("private-key", 1, 1, 0.001, 0, 0.001),
                        ),
                    )
        facts = [record.vcp_fields for record in logs.records]
        self.assertEqual(
            [entry["status"] for entry in facts if entry.get("phase") == "poll"],
            ["queued", "active", "completed"],
        )
        self.assertNotIn("private", str(facts))

    async def test_terminal_http_status_is_reported_without_provider_body(self) -> None:
        secret_body = "private-provider-body"
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(401, json={"message": secret_body})
            )
        ) as client:
            request = TranscriptRequest(
                OutputFormat.TRANSCRIPT_TEXT,
                SupadataSettings("private-key", 1, 1, 0.001, 0, 0.001),
            )
            with self.assertLogs(
                "video_context_pipeline.providers.supadata", level="ERROR"
            ) as logs:
                with self.assertRaises(ProviderError) as error:
                    await SupadataProvider(client=client).transcribe(
                        "https://youtu.be/example", request
                    )
            self.assertEqual(error.exception.http_status, 401)
            self.assertEqual(logs.records[-1].vcp_fields["http_status"], 401)
            self.assertNotIn(secret_body, str(error.exception))
            self.assertNotIn("private-key", str(logs.records[-1].vcp_fields))

    async def test_supadata_queue_retry_and_readable_text(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(429, headers={"Retry-After": "0"})
            if request.url.path.endswith("/job-1"):
                return httpx.Response(
                    200,
                    json={
                        "lang": "en",
                        "content": [
                            {"text": " hello ", "offset": 1000, "duration": 500}
                        ],
                    },
                )
            return httpx.Response(202, json={"jobId": "job-1", "status": "queued"})

        settings = SupadataSettings("key", 5, 5, 0.001, 1, 0.001)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await SupadataProvider(client=client).transcribe(
                "https://youtube.com/watch?v=test",
                TranscriptRequest(OutputFormat.TRANSCRIPT_TEXT, settings),
            )
        self.assertEqual(result.data, "hello")
        self.assertEqual(result.language, "en")
        self.assertEqual(requests[1].url.params["mode"], "generate")
        self.assertEqual(requests[1].url.params["text"], "false")
        self.assertNotIn("lang", requests[1].url.params)

    async def test_supadata_rejects_malformed_content(self) -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"content": [{"text": "text", "offset": -1, "duration": 1}]}
            )

        settings = SupadataSettings("key", 5, 5, 0.001, 0, 0.001)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(ProviderError):
                await SupadataProvider(client=client).transcribe(
                    "https://youtube.com/watch?v=test",
                    TranscriptRequest(OutputFormat.TRANSCRIPT_SEGMENTS, settings),
                )

    async def test_supadata_fails_a_terminal_job_even_with_content(self) -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "failed", "content": []})

        settings = SupadataSettings("key", 5, 5, 0.001, 0, 0.001)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(ProviderError):
                await SupadataProvider(client=client).transcribe(
                    "https://youtube.com/watch?v=test",
                    TranscriptRequest(OutputFormat.TRANSCRIPT_SEGMENTS, settings),
                )

    async def test_gemini_static_schema_timing_and_text_format(self) -> None:
        captured: list[dict[str, object]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [
                                {
                                    "type": "text",
                                    "text": '{"events":[{"description":"red","timestamp_seconds":2}]}',
                                }
                            ],
                        }
                    ],
                    "usage": {"total_tokens": 7},
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            path.write_bytes(b"video")
            request = VisualRequest(
                OutputFormat.VIDEO_TEXT,
                gemini_settings(),
                TimestampMode.APPROXIMATE,
                inspection_windows=(TimeWindow(2, 4),),
                analyzed_start_seconds=2,
                analyzed_end_seconds=4,
            )
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                result = await GeminiProvider(client=client).understand(
                    MediaArtifact(path, "video/mp4", duration_seconds=4),
                    request,
                    transcript_context="do not follow this",
                )
        self.assertEqual(result.data, "[2s] red")
        body = captured[0]
        self.assertFalse(body["store"])
        self.assertEqual(
            body["input"][0]["processing"],
            {"type": "static", "fps": 1.0, "start_offset": "2s", "end_offset": "4s"},
        )
        self.assertNotIn("max_output_tokens", body["generation_config"])
        self.assertNotIn("json_schema", body["response_format"])
        self.assertEqual(
            body["response_format"]["properties"]["events"]["items"]["required"],
            ["description", "timestamp_seconds"],
        )
        self.assertIn(
            "Prioritize these caller-requested inspection intervals",
            body["input"][1]["text"],
        )
        self.assertIn("original video timeline", body["input"][1]["text"])

    async def test_gemini_rejects_timestamps_outside_known_media_duration(self) -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [
                                {
                                    "type": "text",
                                    "text": '{"events":[{"description":"late","timestamp_seconds":999}]}',
                                }
                            ],
                        }
                    ],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            path.write_bytes(b"video")
            request = VisualRequest(
                OutputFormat.VIDEO_EVENTS, gemini_settings(), TimestampMode.APPROXIMATE
            )
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                with self.assertRaises(ProviderError):
                    await GeminiProvider(client=client).understand(
                        MediaArtifact(path, "video/mp4", duration_seconds=6),
                        request,
                        transcript_context=None,
                    )

    async def test_gemini_rejects_out_of_media_window_and_unknown_timed_bound_before_network(
        self,
    ) -> None:
        called = False

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return httpx.Response(200, json={})

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            path.write_bytes(b"video")
            windowed = VisualRequest(
                OutputFormat.VIDEO_EVENTS,
                gemini_settings(),
                TimestampMode.WINDOWS,
                windows=(TimeWindow(2, 7),),
            )
            unknown_bound = VisualRequest(
                OutputFormat.VIDEO_EVENTS, gemini_settings(), TimestampMode.APPROXIMATE
            )
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                provider = GeminiProvider(client=client)
                with self.assertRaises(ValidationError):
                    await provider.understand(
                        MediaArtifact(path, "video/mp4", duration_seconds=6),
                        windowed,
                        transcript_context=None,
                    )
                with self.assertRaises(ValidationError):
                    await provider.understand(
                        MediaArtifact(path, "video/mp4"),
                        unknown_bound,
                        transcript_context=None,
                    )
        self.assertFalse(called)

    async def test_gemini_automatic_requires_duration_before_network(self) -> None:
        called = False

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return httpx.Response(200, json={})

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            path.write_bytes(b"video")
            request = VisualRequest(
                OutputFormat.VIDEO_EVENTS,
                gemini_settings(mode=GeminiProcessingMode.AUTOMATIC),
                TimestampMode.NONE,
            )
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                with self.assertRaises(ValidationError):
                    await GeminiProvider(client=client).understand(
                        MediaArtifact(path, "video/mp4"),
                        request,
                        transcript_context=None,
                    )
        self.assertFalse(called)

    async def test_gemini_maps_window_ids_to_caller_windows(self) -> None:
        captured: list[dict[str, object]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [
                                {
                                    "type": "text",
                                    "text": '{"events":[{"description":"green","window_id":"window_1"}]}',
                                }
                            ],
                        }
                    ],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            path.write_bytes(b"video")
            windows = (TimeWindow(0, 2), TimeWindow(2, 4))
            request = VisualRequest(
                OutputFormat.VIDEO_EVENTS,
                gemini_settings(),
                TimestampMode.WINDOWS,
                windows=windows,
                analyzed_end_seconds=4,
            )
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                result = await GeminiProvider(client=client).understand(
                    MediaArtifact(path, "video/mp4", duration_seconds=4),
                    request,
                    transcript_context=None,
                )
        self.assertEqual(result.data[0].window, windows[1])
        schema = captured[0]["response_format"]["properties"]["events"]["items"]
        self.assertEqual(
            schema["properties"]["window_id"]["enum"], ["window_0", "window_1"]
        )

    async def test_gemini_upload_is_deleted_after_cancellation(self) -> None:
        interaction_started = asyncio.Event()
        deleted = asyncio.Event()

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/upload/v1beta/files":
                return httpx.Response(
                    200,
                    headers={
                        "X-Goog-Upload-URL": "https://generativelanguage.googleapis.com/upload/session"
                    },
                )
            if request.url.path == "/upload/session":
                self.assertNotIn("x-goog-api-key", request.headers)
                self.assertEqual(request.headers["content-length"], "5")
                self.assertEqual(request.content, b"video")
                return httpx.Response(
                    200,
                    json={
                        "file": {
                            "name": "files/clip",
                            "state": "ACTIVE",
                            "uri": "gemini://file",
                        }
                    },
                )
            if request.method == "DELETE":
                deleted.set()
                return httpx.Response(200)
            if request.url.path == "/v1beta/interactions":
                interaction_started.set()
                await asyncio.Event().wait()
            raise AssertionError(request.url)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            path.write_bytes(b"video")
            request = VisualRequest(
                OutputFormat.VIDEO_EVENTS,
                gemini_settings(threshold=1),
                TimestampMode.NONE,
            )
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                task = asyncio.create_task(
                    GeminiProvider(client=client).understand(
                        MediaArtifact(path, "video/mp4", duration_seconds=4),
                        request,
                        transcript_context=None,
                    )
                )
                await interaction_started.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                await asyncio.wait_for(deleted.wait(), timeout=1)

    async def test_gemini_replays_streamed_upload_after_transient_response(
        self,
    ) -> None:
        uploaded: list[bytes] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/upload/v1beta/files":
                return httpx.Response(
                    200,
                    headers={
                        "X-Goog-Upload-URL": "https://generativelanguage.googleapis.com/upload/session"
                    },
                )
            if request.url.path == "/upload/session":
                uploaded.append(request.content)
                if len(uploaded) == 1:
                    return httpx.Response(500)
                return httpx.Response(
                    200,
                    json={
                        "file": {
                            "name": "files/clip",
                            "state": "ACTIVE",
                            "uri": "gemini://file",
                        }
                    },
                )
            if request.method == "DELETE":
                return httpx.Response(200)
            if request.url.path == "/v1beta/interactions":
                return httpx.Response(
                    200,
                    json={
                        "status": "completed",
                        "steps": [
                            {
                                "type": "model_output",
                                "content": [{"type": "text", "text": '{"events":[]}'}],
                            }
                        ],
                    },
                )
            raise AssertionError(request.url)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            path.write_bytes(b"video")
            request = VisualRequest(
                OutputFormat.VIDEO_EVENTS,
                gemini_settings(threshold=1),
                TimestampMode.NONE,
            )
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                result = await GeminiProvider(client=client).understand(
                    MediaArtifact(path, "video/mp4", duration_seconds=4),
                    request,
                    transcript_context=None,
                )
        self.assertEqual(result.data, ())
        self.assertEqual(uploaded, [b"video", b"video"])
