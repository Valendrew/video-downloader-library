"""Exercise the demo's local actions with generated, offline FFmpeg media."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from demo.observability import Monitor
from demo.operations import execute, prepare, steps_for
from demo.schema import JobRequest
from video_context_pipeline import MediaArtifact


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and ffprobe are required",
)
class LocalMediaTests(unittest.IsolatedAsyncioTestCase):
    async def command(self, *args):
        process = await asyncio.create_subprocess_exec(
            *map(str, args),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
        self.assertEqual(process.returncode, 0, stderr.decode())
        return stdout

    async def test_probe_extract_enrich_cover_and_preserve_caller_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
            source = root / "caller.mp4"
            await self.command(
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=64x64:r=10",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=44100",
                "-t",
                "0.5",
                "-c:v",
                "mpeg4",
                "-c:a",
                "aac",
                source,
            )
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            cover = root / "cover.ppm"
            cover.write_bytes(b"P6\n16 16\n255\n" + bytes([255, 0, 0]) * 256)
            art = root / "cover.jpg"
            await self.command(
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                cover,
                "-frames:v",
                "1",
                art,
            )
            files = {
                "source": MediaArtifact(source, "video/mp4"),
                "cover": MediaArtifact(art, "image/jpeg"),
            }
            exes = {"ffmpeg": [ffmpeg], "ffprobe": [ffprobe]}
            local = {
                "ffmpeg_path": ffmpeg,
                "ffprobe_path": ffprobe,
                "timeout_seconds": 20,
            }

            async def run(action, **settings):
                directory = root / action
                directory.mkdir()
                prepared = prepare(
                    JobRequest(action=action, local=local, **settings),
                    directory,
                    exes,
                    files.__getitem__,
                )
                return await execute(prepared, Monitor(action, steps_for(prepared)))

            measured = await run("probe", input_artifact_id="source")
            self.assertEqual(measured.media_type, "video/mp4")
            self.assertGreater(measured.duration_seconds, 0)
            extracted = await run(
                "extract",
                input_artifact_id="source",
                transform={"codec": "mp3", "container": "mp3", "bitrate_kbps": 128},
            )
            self.assertEqual(extracted.media_type, "audio/mpeg")
            files["audio"] = extracted
            tagged = await run(
                "enrich",
                input_artifact_id="audio",
                enrichment={
                    "metadata": {"title": "Offline fixture", "artist": "Demo test"},
                    "cover_artifact_id": "cover",
                },
            )
            measured_tags = json.loads(
                await self.command(
                    ffprobe,
                    "-v",
                    "error",
                    "-show_format",
                    "-show_streams",
                    "-of",
                    "json",
                    tagged.path,
                )
            )
            self.assertEqual(
                measured_tags["format"]["tags"]["title"], "Offline fixture"
            )
            self.assertEqual(measured_tags["format"]["tags"]["artist"], "Demo test")
            self.assertTrue(
                any(
                    stream.get("disposition", {}).get("attached_pic") == 1
                    for stream in measured_tags["streams"]
                )
            )
            tagged.cleanup()
            extracted.cleanup()
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            self.assertTrue(art.exists())
