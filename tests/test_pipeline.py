from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from video_context_pipeline import (  # noqa: E402
    ConfigurationError,
    GeminiModel,
    GeminiProcessingMode,
    GeminiResolution,
    GeminiSettings,
    MediaArtifact,
    MediaRequest,
    MediaSettings,
    OutputFormat,
    OutputStatus,
    Pipeline,
    PipelineError,
    PipelineRequest,
    ProviderOutput,
    SupadataSettings,
    TimestampMode,
    TranscriptRequest,
    TranscriptSegment,
    ValidationError,
    VisualRequest,
)


def media_request() -> MediaRequest:
    return MediaRequest(MediaSettings(request_timeout_seconds=5), "best")


def visual_request() -> VisualRequest:
    return VisualRequest(
        format=OutputFormat.VIDEO_TEXT,
        settings=GeminiSettings(
            "key",
            GeminiModel.FLASH_3_8,
            GeminiResolution.LOW,
            "low",
            GeminiProcessingMode.AGENTIC,
            None,
            None,
            30,
            2,
            1,
            1048576,
            120,
            2,
        ),
        timestamp_mode=TimestampMode.NONE,
    )


def transcript_request() -> TranscriptRequest:
    return TranscriptRequest(
        OutputFormat.TRANSCRIPT_SEGMENTS, SupadataSettings("key", 5, 30, 1, 0, 1)
    )


class FakeMedia:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "video.mp4"

    async def download(
        self, _url: str, _request: MediaRequest
    ) -> ProviderOutput[MediaArtifact]:
        self.path.write_text("video")
        return ProviderOutput(
            OutputFormat.MEDIA,
            MediaArtifact(self.path, "video/mp4", owned=True),
            "fake-media",
            OutputStatus.CONTENT,
        )


class FakeTranscript:
    async def transcribe(
        self, _url: str, _request: TranscriptRequest
    ) -> ProviderOutput[tuple[TranscriptSegment, ...]]:
        return ProviderOutput(
            OutputFormat.TRANSCRIPT_SEGMENTS,
            (TranscriptSegment(0, 1, "context line"),),
            "fake-transcript",
            OutputStatus.CONTENT,
            language="en",
        )


class FakeVisual:
    def __init__(self) -> None:
        self.contexts: list[str | None] = []

    async def understand(
        self,
        _media: MediaArtifact,
        _request: VisualRequest,
        *,
        transcript_context: str | None,
    ) -> ProviderOutput[str]:
        self.contexts.append(transcript_context)
        return ProviderOutput(
            OutputFormat.VIDEO_TEXT,
            "A visible action.",
            "fake-visual",
            OutputStatus.CONTENT,
        )


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_transcript_visual_coupling_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            visual_only = FakeVisual()
            only_pipeline = Pipeline(
                media_provider=FakeMedia(Path(temporary)), visual_provider=visual_only
            )
            result = await only_pipeline.run(
                "https://youtube.com/watch?v=x",
                PipelineRequest(visual=visual_request(), visual_media=media_request()),
            )
            self.assertEqual(result.output("visual").data, "A visible action.")
            self.assertEqual(visual_only.contexts, [None])

        with tempfile.TemporaryDirectory() as temporary:
            independent_visual = FakeVisual()
            independent = Pipeline(
                media_provider=FakeMedia(Path(temporary)),
                transcript_provider=FakeTranscript(),
                visual_provider=independent_visual,
            )
            await independent.run(
                "https://youtube.com/watch?v=x",
                PipelineRequest(
                    transcript=transcript_request(),
                    visual=visual_request(),
                    visual_media=media_request(),
                ),
            )
            self.assertEqual(independent_visual.contexts, [None])

        with tempfile.TemporaryDirectory() as temporary:
            coupled_visual = FakeVisual()
            coupled = Pipeline(
                media_provider=FakeMedia(Path(temporary)),
                transcript_provider=FakeTranscript(),
                visual_provider=coupled_visual,
            )
            await coupled.run(
                "https://youtube.com/watch?v=x",
                PipelineRequest(
                    transcript=transcript_request(),
                    visual=visual_request(),
                    visual_media=media_request(),
                    include_transcript_context=True,
                ),
            )
            self.assertEqual(coupled_visual.contexts, ["context line"])

    async def test_failure_is_atomic_and_cleans_successful_owned_media(self) -> None:
        class FailingTranscript:
            async def transcribe(
                self, _url: str, _request: TranscriptRequest
            ) -> ProviderOutput[str]:
                await asyncio.sleep(0)
                raise RuntimeError("provider rejected request")

        with tempfile.TemporaryDirectory() as temporary:
            media = FakeMedia(Path(temporary))
            pipeline = Pipeline(
                media_provider=media, transcript_provider=FailingTranscript()
            )
            with self.assertRaises(PipelineError):
                await pipeline.run(
                    "https://youtube.com/watch?v=x",
                    PipelineRequest(
                        transcript=transcript_request(), media=media_request()
                    ),
                )
            self.assertFalse(media.path.exists())

    async def test_cancellation_cleans_media_and_success_retains_requested_media(
        self,
    ) -> None:
        class WaitingTranscript:
            async def transcribe(
                self, _url: str, _request: TranscriptRequest
            ) -> ProviderOutput[str]:
                await asyncio.Event().wait()
                raise AssertionError("unreachable")

        with tempfile.TemporaryDirectory() as temporary:
            media = FakeMedia(Path(temporary))
            pipeline = Pipeline(
                media_provider=media, transcript_provider=WaitingTranscript()
            )
            running = asyncio.create_task(
                pipeline.run(
                    "https://youtube.com/watch?v=x",
                    PipelineRequest(
                        transcript=transcript_request(), media=media_request()
                    ),
                )
            )
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            running.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await running
            self.assertFalse(media.path.exists())

        with tempfile.TemporaryDirectory() as temporary:
            media = FakeMedia(Path(temporary))
            records: list[logging.LogRecord] = []

            class Capture(logging.Handler):
                def emit(self, record: logging.LogRecord) -> None:
                    records.append(record)

            logger = logging.getLogger("test.video_context_pipeline.lifecycle")
            logger.handlers[:] = [Capture()]
            logger.setLevel(logging.INFO)
            logger.propagate = False
            result = await Pipeline(media_provider=media, logger=logger).run(
                "https://youtube.com/watch?v=x", PipelineRequest(media=media_request())
            )
            artifact = result.output("media").data
            self.assertTrue(artifact.path.exists())
            result.cleanup()
            self.assertFalse(artifact.path.exists())
            messages = [record.getMessage() for record in records]
            self.assertEqual(messages, ["pipeline started", "pipeline completed"])
            self.assertEqual(
                len({record.vcp_fields["request_id"] for record in records}), 1
            )

    async def test_empty_success_is_valid_but_malformed_schema_fails(self) -> None:
        class EmptyTranscript:
            async def transcribe(
                self, _url: str, _request: TranscriptRequest
            ) -> ProviderOutput[tuple[()]]:
                return ProviderOutput(
                    OutputFormat.TRANSCRIPT_SEGMENTS, (), "fake", OutputStatus.EMPTY
                )

        result = await Pipeline(transcript_provider=EmptyTranscript()).run(
            "https://instagram.com/reel/x",
            PipelineRequest(transcript=transcript_request()),
        )
        self.assertEqual(result.output("transcript").status, OutputStatus.EMPTY)

        class MalformedTranscript:
            async def transcribe(
                self, _url: str, _request: TranscriptRequest
            ) -> ProviderOutput[tuple[str]]:
                return ProviderOutput(
                    OutputFormat.TRANSCRIPT_SEGMENTS,
                    ("not a segment",),
                    "fake",
                    OutputStatus.CONTENT,
                )

        with self.assertRaises(ValidationError):
            await Pipeline(transcript_provider=MalformedTranscript()).run(
                "https://instagram.com/reel/x",
                PipelineRequest(transcript=transcript_request()),
            )

    async def test_automatic_visual_mode_requires_artifact_duration(self) -> None:
        automatic = VisualRequest(
            format=OutputFormat.VIDEO_TEXT,
            settings=GeminiSettings(
                "key",
                GeminiModel.FLASH_3_8,
                GeminiResolution.LOW,
                "low",
                GeminiProcessingMode.AUTOMATIC,
                1,
                10,
                30,
                2,
                1,
                1048576,
                120,
                2,
            ),
            timestamp_mode=TimestampMode.NONE,
        )
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValidationError, "duration_seconds"):
                await Pipeline(
                    media_provider=FakeMedia(Path(temporary)),
                    visual_provider=FakeVisual(),
                ).run(
                    "https://youtube.com/watch?v=x",
                    PipelineRequest(visual=automatic, visual_media=media_request()),
                )
        with self.assertRaises(ConfigurationError):
            VisualRequest(
                format=OutputFormat.VIDEO_TEXT,
                settings=automatic.settings,
                timestamp_mode=TimestampMode.NONE,
                analyzed_start_seconds=-1,
            )

    async def test_timestamped_text_remains_plain_text(self) -> None:
        timestamped_text = VisualRequest(
            format=OutputFormat.VIDEO_TEXT,
            settings=visual_request().settings,
            timestamp_mode=TimestampMode.APPROXIMATE,
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = await Pipeline(
                media_provider=FakeMedia(Path(temporary)), visual_provider=FakeVisual()
            ).run(
                "https://youtube.com/watch?v=x",
                PipelineRequest(visual=timestamped_text, visual_media=media_request()),
            )
        self.assertIsInstance(result.output("visual").data, str)


if __name__ == "__main__":
    unittest.main()
