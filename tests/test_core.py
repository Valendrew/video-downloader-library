from __future__ import annotations

import math
import sys
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
    OutputFormat,
    OutputStatus,
    ProviderOutput,
    SupadataSettings,
    TimestampMode,
    TimeWindow,
    TranscriptSegment,
    ValidationError,
    VideoEvent,
    load_environment,
)
from video_context_pipeline.formatting import transcript_plain_text  # noqa: E402
from video_context_pipeline.models import validate_video_events  # noqa: E402
from video_context_pipeline.pipeline import validate_platform_url  # noqa: E402


class CoreContractTests(unittest.TestCase):
    def test_provider_output_cannot_disguise_failure_or_empty_data(self) -> None:
        for status, data in (
            ("failed", "error"),
            (OutputStatus.CONTENT, ""),
            (OutputStatus.EMPTY, "error"),
        ):
            with self.subTest(status=status), self.assertRaises(ValidationError):
                ProviderOutput(OutputFormat.TRANSCRIPT_TEXT, data, "test", status)

    def test_environment_is_explicit_and_disabled_providers_need_no_credentials(
        self,
    ) -> None:
        self.assertEqual(load_environment(environ={}).gemini, None)
        with self.assertRaisesRegex(ConfigurationError, "GEMINI_API_KEY"):
            load_environment(include_gemini=True, environ={})
        settings = load_environment(
            include_gemini=True,
            environ={
                "GEMINI_API_KEY": "key",
                "VCP_GEMINI_MODEL": "gemini-3.8-flash",
                "VCP_GEMINI_MEDIA_RESOLUTION": "high",
                "VCP_GEMINI_THINKING_LEVEL": "high",
                "VCP_GEMINI_PROCESSING_MODE": "automatic",
                "VCP_GEMINI_STATIC_FPS": "2",
                "VCP_GEMINI_AGENTIC_THRESHOLD_SECONDS": "120",
                "VCP_GEMINI_REQUEST_TIMEOUT_SECONDS": "30",
                "VCP_GEMINI_MAX_RETRIES": "2",
                "VCP_GEMINI_RETRY_BACKOFF_SECONDS": "1",
                "VCP_GEMINI_FILE_UPLOAD_THRESHOLD_BYTES": "1048576",
                "VCP_GEMINI_FILE_POLL_DEADLINE_SECONDS": "120",
                "VCP_GEMINI_FILE_POLL_INTERVAL_SECONDS": "2",
            },
        )
        self.assertEqual(settings.gemini.model, GeminiModel.FLASH_3_8)
        with self.assertRaises(ConfigurationError):
            GeminiSettings(
                "key",
                GeminiModel.FLASH_3_8,
                GeminiResolution.LOW,
                "minimal",
                GeminiProcessingMode.AGENTIC,
                None,
                None,
                30,
                2,
                1,
                1048576,
                120,
                2,
            )
        with self.assertRaises(ConfigurationError):
            GeminiSettings(
                "key",
                "unknown",
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
            )

    def test_numeric_and_temporal_contracts_reject_booleans_nan_and_invalid_bounds(
        self,
    ) -> None:
        with self.assertRaises(ValidationError):
            TranscriptSegment(True, None, "text")
        with self.assertRaises(ValidationError):
            TimeWindow(0, math.inf)
        with self.assertRaises(ConfigurationError):
            SupadataSettings("key", True, 30, 1, 0, 1)
        window = TimeWindow(1, 3)
        event = VideoEvent("cut", window=window)
        self.assertEqual(
            validate_video_events(
                (event,),
                TimestampMode.WINDOWS,
                analyzed_end_seconds=5,
                windows=(window,),
            ),
            (event,),
        )
        with self.assertRaises(ValidationError):
            validate_video_events(
                (VideoEvent("bad", timestamp_seconds=6),),
                TimestampMode.APPROXIMATE,
                analyzed_end_seconds=5,
            )

    def test_plain_text_formatting_never_returns_segments_or_json(self) -> None:
        text = transcript_plain_text(
            (TranscriptSegment(0, 1, "one"), TranscriptSegment(1, None, "two"))
        )
        self.assertEqual(text, "one\ntwo")
        self.assertNotIn("start_seconds", text)
        output = ProviderOutput(
            OutputFormat.TRANSCRIPT_TEXT, text, "fake", OutputStatus.CONTENT
        )
        self.assertEqual(output.data, "one\ntwo")

    def test_owned_artifacts_clean_dependencies_but_preserve_caller_file(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            caller = root / "caller.mp4"
            temporary_file = root / "temporary.mp3"
            caller.write_text("caller")
            temporary_file.write_text("temporary")
            with MediaArtifact(
                caller,
                "video/mp4",
                owned=False,
                dependencies=(MediaArtifact(temporary_file, "audio/mpeg", owned=True),),
            ):
                pass
            self.assertTrue(caller.exists())
            self.assertFalse(temporary_file.exists())

    def test_owned_artifact_can_release_its_dedicated_empty_directory_and_duration_is_finite(
        self,
    ) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "owned"
            directory.mkdir()
            path = directory / "video.mp4"
            path.write_text("video")
            artifact = MediaArtifact(
                path,
                "video/mp4",
                duration_seconds=3.5,
                owned=True,
                owned_directory=directory,
            )
            artifact.cleanup()
            self.assertFalse(directory.exists())
        with self.assertRaises(ValidationError):
            MediaArtifact(Path("bad.mp4"), "video/mp4", duration_seconds=math.nan)

    def test_platform_url_policy(self) -> None:
        self.assertEqual(
            validate_platform_url("https://youtu.be/example"),
            "https://youtu.be/example",
        )
        self.assertEqual(
            validate_platform_url("https://vm.tiktok.com/example"),
            "https://vm.tiktok.com/example",
        )
        with self.assertRaises(ValidationError):
            validate_platform_url("https://user:pass@youtube.com/watch?v=x")
        with self.assertRaises(ValidationError):
            validate_platform_url("https://youtube.com.evil.example/watch")


if __name__ == "__main__":
    unittest.main()
