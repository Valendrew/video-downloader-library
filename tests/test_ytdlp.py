from __future__ import annotations

import asyncio
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from video_context_pipeline import (
    MediaRequest,
    MediaSettings,
    Pipeline,
    PipelineRequest,
    ValidationError,
)  # noqa: E402
from video_context_pipeline.providers.ytdlp import (
    MediaFormat,
    MediaInspection,
    YtDlpMediaProvider,
    YtDlpMetadataProvider,
    plan_audio_download,
)  # noqa: E402


class FakeDownloader:
    def __init__(
        self, options: dict[str, object], *, wait: asyncio.Event | None = None
    ) -> None:
        self.options = options
        self.wait = wait

    def __enter__(self) -> "FakeDownloader":
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def extract_info(self, _url: str, *, download: bool) -> dict[str, object]:
        if self.wait is not None:
            import time

            while not self.wait.is_set():
                time.sleep(0.01)
                for hook in self.options["progress_hooks"]:  # type: ignore[index]
                    hook(
                        {
                            "status": "downloading",
                            "downloaded_bytes": 1,
                            "total_bytes": 10,
                        }
                    )
        if download:
            directory = Path(str(self.options["outtmpl"])).parent  # type: ignore[index]
            path = directory / "source.m4a"
            for hook in self.options["progress_hooks"]:  # type: ignore[index]
                hook(
                    {"status": "downloading", "downloaded_bytes": 4, "total_bytes": 10}
                )
            path.write_bytes(b"media")
        else:
            return {
                "title": "Example title",
                "description": "Example description",
                "duration": 3,
                "formats": [
                    {
                        "format_id": "a",
                        "ext": "m4a",
                        "acodec": "mp4a.40.2",
                        "vcodec": "none",
                        "abr": 128,
                        "filesize": 4,
                    }
                ],
            }
        return {
            "format_id": "a",
            "ext": "m4a",
            "acodec": "mp4a.40.2",
            "vcodec": "none",
            "duration": 3,
            "requested_downloads": [{"filepath": str(path)}],
        }


class YtDlpTests(unittest.IsolatedAsyncioTestCase):
    def test_selects_compatible_only_when_explicit_ratio_is_met(self) -> None:
        compatible = MediaFormat("m4a", "m4a", "mp4a.40.2", "none", 128, None, 10, None)
        best = MediaFormat("webm", "webm", "opus", "none", 192, None, 20, None)
        inspection = MediaInspection((compatible, best), 3, None, None)
        direct = plan_audio_download(inspection, compatible_bitrate_ratio=0.5)
        self.assertEqual(
            (direct.selected_format_id, direct.requires_mp3_conversion), ("m4a", False)
        )
        converted = plan_audio_download(inspection, compatible_bitrate_ratio=0.8)
        self.assertEqual(
            (converted.selected_format_id, converted.source), ("bestaudio/best", None)
        )
        m4p = MediaFormat("m4p", "m4p", "alac", "none", 128, None, None, None)
        muxed = MediaFormat("muxed", "mp4", "mp4a.40.2", "avc1", 999, None, None, None)
        self.assertEqual(
            plan_audio_download(
                MediaInspection((m4p, muxed), 3, None, None), compatible_bitrate_ratio=1
            ).selected_format_id,
            "m4p",
        )
        fallback = plan_audio_download(
            MediaInspection((muxed,), 3, None, None), compatible_bitrate_ratio=1
        )
        self.assertEqual(
            (fallback.selected_format_id, fallback.source), ("bestaudio/best", None)
        )
        with self.assertRaises(ValidationError):
            plan_audio_download(inspection, compatible_bitrate_ratio=math.nan)

    async def test_download_maps_progress_and_owned_directory(self) -> None:
        seen = []
        captured: dict[str, object] = {}

        def factory(options: dict[str, object]) -> FakeDownloader:
            captured.update(options)
            return FakeDownloader(options)

        with tempfile.TemporaryDirectory() as temporary:
            cookie = Path(temporary) / "cookies.txt"
            cookie.write_text("# Netscape HTTP Cookie File\n")
            constructor_events = []
            provider = YtDlpMediaProvider(
                js_runtimes={"node": {}},
                downloader_factory=factory,
                progress=constructor_events.append,
            )
            output = await provider.download(
                "https://youtube.com/watch?v=x",
                MediaRequest(
                    MediaSettings(
                        5, cookie_file=cookie, output_directory=Path(temporary)
                    ),
                    "a",
                ),
                progress=seen.append,
            )
            self.assertTrue(output.data.path.exists())
            self.assertEqual(
                [(item.downloaded_bytes, item.total_bytes) for item in seen], [(4, 10)]
            )
            self.assertEqual(constructor_events, [])
            self.assertEqual(captured["format"], "a")
            self.assertEqual(captured["socket_timeout"], 5.0)
            self.assertEqual(captured["js_runtimes"], {"node": {}})
            self.assertEqual(captured["cookiefile"], str(cookie))
            output.data.cleanup()
            self.assertFalse(output.data.owned_directory.exists())  # type: ignore[union-attr]

    def test_media_type_numbers_and_owned_result_paths_are_strict(self) -> None:
        audio_mp4 = MediaFormat("a", "mp4", "mp4a.40.2", "none", None, None, None, None)
        self.assertEqual(YtDlpMediaProvider._media_type(audio_mp4), "audio/mp4")
        self.assertIsNone(YtDlpMediaProvider._number(math.inf))
        self.assertIsNone(YtDlpMediaProvider._integer(-1))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root.parent / "outside.mp3"
            outside.write_bytes(b"x")
            try:
                with self.assertRaises(Exception):
                    YtDlpMediaProvider._result_path({"filepath": str(outside)}, root)
            finally:
                outside.unlink(missing_ok=True)

    async def test_cancellation_waits_for_blocking_worker_before_cleanup(self) -> None:
        waiting = asyncio.Event()
        provider = YtDlpMediaProvider(
            js_runtimes={},
            downloader_factory=lambda options: FakeDownloader(
                dict(options), wait=waiting
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = MediaRequest(MediaSettings(5, output_directory=root), "a")
            task = asyncio.create_task(
                provider.download("https://youtube.com/watch?v=x", request)
            )
            await asyncio.sleep(0.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(tuple(root.iterdir()), ())

    async def test_metadata_adapter_composes_with_pipeline_and_hides_provider_diagnostics(
        self,
    ) -> None:
        captured: dict[str, object] = {}

        def factory(options: dict[str, object]) -> FakeDownloader:
            captured.update(options)
            return FakeDownloader(options)

        media = YtDlpMediaProvider(js_runtimes={}, downloader_factory=factory)
        result = await Pipeline(
            metadata_provider=YtDlpMetadataProvider(
                settings=MediaSettings(5), media_provider=media
            )
        ).run("https://youtube.com/watch?v=x", PipelineRequest(metadata=True))
        metadata = result.output("metadata").data
        self.assertEqual(metadata["description"], "Example description")
        self.assertEqual(metadata["formats"][0]["exact_size_bytes"], 4)
        self.assertEqual(captured["retries"], 0)
        self.assertIn("logger", captured)


if __name__ == "__main__":
    unittest.main()
