from __future__ import annotations

import asyncio
import math
import os
import shutil
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from video_context_pipeline import (  # noqa: E402
    MediaArtifact,
    ProviderError,
    ValidationError,
)
from video_context_pipeline.media import FFmpegMediaTools  # noqa: E402


def write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(
            b"".join(
                struct.pack(
                    "<h", int(12_000 * math.sin(index * 2 * math.pi * 440 / 8_000))
                )
                for index in range(8_000)
            )
        )


class MediaToolsTests(unittest.IsolatedAsyncioTestCase):
    def _tools(self, timeout: float = 5) -> FFmpegMediaTools:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg and ffprobe are unavailable")
        return FFmpegMediaTools(
            ffmpeg_path=Path(ffmpeg),
            ffprobe_path=Path(ffprobe),
            timeout_seconds=timeout,
        )

    async def _make_video(self, wav: Path, video: Path) -> None:
        ffmpeg = shutil.which("ffmpeg")
        assert ffmpeg is not None
        process = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=16x16",
            "-i",
            str(wav),
            "-shortest",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            str(video),
        )
        self.assertEqual(await process.wait(), 0)

    async def test_extracts_video_audio_and_converts_audio_without_touching_sources(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wav = root / "tone.wav"
            video = root / "tone.mp4"
            write_wav(wav)
            await self._make_video(wav, video)
            extracted = await self._tools().extract_audio(
                MediaArtifact(video, "video/mp4"),
                destination=root / "extracted.mp3",
                codec="mp3",
                container="mp3",
                bitrate_kbps=128,
            )
            converted = await self._tools().convert_audio(
                MediaArtifact(wav, "audio/wav"),
                destination=root / "converted.mp3",
                codec="mp3",
                container="mp3",
                bitrate_kbps=96,
            )
            self.assertTrue(video.exists())
            self.assertTrue(wav.exists())
            self.assertEqual(
                (await self._tools().probe(extracted.path)).codecs, ("mp3",)
            )
            self.assertEqual(
                (await self._tools().probe(converted.path)).media_type, "audio/mpeg"
            )

    async def test_enriches_generated_audio_with_local_thumbnail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wav = root / "tone.wav"
            thumbnail = root / "cover.ppm"
            write_wav(wav)
            thumbnail.write_bytes(b"P6\n1 1\n255\n\xff\x00\x00")
            source = await self._tools().convert_audio(
                MediaArtifact(wav, "audio/wav"),
                destination=root / "source.mp3",
                codec="mp3",
                container="mp3",
                bitrate_kbps=96,
            )
            enriched = await self._tools().enrich_metadata(
                source,
                destination=root / "enriched.mp3",
                metadata={"title": "Tone"},
                thumbnail=thumbnail,
            )
            self.assertTrue(source.path.exists())
            self.assertTrue(enriched.path.exists())
            self.assertIn("mp3", (await self._tools().probe(enriched.path)).codecs)

    async def test_rejects_bad_destination_source_kind_and_reports_missing_binary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wav = root / "tone.wav"
            write_wav(wav)
            path = root / "exists.mp3"
            path.write_text("existing")
            with self.assertRaises(ValidationError):
                await self._tools().convert_audio(
                    MediaArtifact(wav, "audio/wav"),
                    destination=path,
                    codec="mp3",
                    container="mp3",
                    bitrate_kbps=128,
                )
            with self.assertRaisesRegex(ValidationError, "video source"):
                await self._tools().extract_audio(
                    MediaArtifact(wav, "audio/wav"),
                    destination=root / "wrong.mp3",
                    codec="mp3",
                    container="mp3",
                    bitrate_kbps=128,
                )
            missing = FFmpegMediaTools(
                ffmpeg_path=Path("/not/ffmpeg"),
                ffprobe_path=Path("/not/ffprobe"),
                timeout_seconds=1,
            )
            with self.assertRaisesRegex(ProviderError, "ffmpeg binary"):
                await missing.convert_audio(
                    MediaArtifact(wav, "audio/wav"),
                    destination=root / "new.mp3",
                    codec="mp3",
                    container="mp3",
                    bitrate_kbps=128,
                )

    async def test_atomic_publish_preserves_competing_destination_and_cancelled_process_stops(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wav = root / "tone.wav"
            destination = root / "winner.mp3"
            write_wav(wav)
            original_link = os.link

            def competing_link(
                source: str | Path, target: str | Path, *args: object, **kwargs: object
            ) -> None:
                destination.write_text("winner")
                original_link(source, target, *args, **kwargs)

            with patch(
                "video_context_pipeline.media.os.link", side_effect=competing_link
            ):
                with self.assertRaisesRegex(ValidationError, "created"):
                    await self._tools().convert_audio(
                        MediaArtifact(wav, "audio/wav"),
                        destination=destination,
                        codec="mp3",
                        container="mp3",
                        bitrate_kbps=96,
                    )
            self.assertEqual(destination.read_text(), "winner")
            running = asyncio.create_task(
                self._tools()._run_process(
                    [sys.executable, "-c", "import time; time.sleep(30)"]
                )
            )
            await asyncio.sleep(0.05)
            running.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await running


if __name__ == "__main__":
    unittest.main()
