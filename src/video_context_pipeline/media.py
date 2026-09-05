"""Independent, ownership-aware ffmpeg and ffprobe media operations."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from time import monotonic
from typing import Any

from .errors import ProviderError, ValidationError
from .logging import current_request_id, request_correlation, safe_log_fields
from .models import MediaArtifact


@dataclass(frozen=True, slots=True)
class MediaMetadata:
    """Facts measured from a local media file, never inferred from its name."""

    duration_seconds: float | None
    media_type: str
    codecs: tuple[str, ...]
    bitrate_bits_per_second: int | None
    size_bytes: int
    estimated_size_bytes: int | None = None


def _audio_pair(codec: str, container: str) -> tuple[str, str]:
    pairs = {
        ("mp3", "mp3"): ("libmp3lame", "mp3"),
        ("aac", "m4a"): ("aac", "ipod"),
        ("aac", "mp4"): ("aac", "mp4"),
    }
    try:
        return pairs[(codec.lower(), container.lower())]
    except (AttributeError, KeyError) as exc:
        raise ValidationError(
            "audio codec/container must be mp3/mp3, aac/m4a, or aac/mp4"
        ) from exc


def _bitrate(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError("bitrate_kbps must be a positive integer")
    return value


def _timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("timeout_seconds must be a finite positive number")
    result = float(value)
    if result <= 0 or result == float("inf") or result != result:
        raise ValidationError("timeout_seconds must be a finite positive number")
    return result


class FFmpegMediaTools:
    """Run explicitly configured ffmpeg and ffprobe binaries without a shell."""

    def __init__(
        self,
        *,
        ffmpeg_path: Path,
        ffprobe_path: Path,
        timeout_seconds: float,
        logger: logging.Logger | None = None,
    ) -> None:
        if not isinstance(ffmpeg_path, Path) or not isinstance(ffprobe_path, Path):
            raise ValidationError(
                "ffmpeg_path and ffprobe_path must be pathlib.Path objects"
            )
        timeout_seconds = _timeout(timeout_seconds)
        self._ffmpeg_path = ffmpeg_path
        self._ffprobe_path = ffprobe_path
        self._timeout_seconds = timeout_seconds
        self._logger = logger or logging.getLogger("video_context_pipeline.media")

    async def probe(self, path: Path) -> MediaMetadata:
        """Measure streams and duration with ffprobe's JSON output."""
        with request_correlation(current_request_id()):
            started = monotonic()
            try:
                if not path.is_file():
                    raise ProviderError("media file is unavailable for probing")
                data = await self._run_probe(path)
                metadata = self._metadata_from_probe(path, data)
                self._emit(
                    "media probe completed",
                    status="completed",
                    stage="probe",
                    duration_seconds=monotonic() - started,
                )
                return metadata
            except asyncio.CancelledError:
                self._emit(
                    "media probe cancelled",
                    status="cancelled",
                    stage="probe",
                    duration_seconds=monotonic() - started,
                )
                raise
            except Exception as exc:
                self._emit(
                    "media probe failed",
                    status="failed",
                    stage="probe",
                    error_type=type(exc).__name__,
                    duration_seconds=monotonic() - started,
                )
                raise

    async def extract_audio(
        self,
        source: MediaArtifact,
        *,
        destination: Path,
        codec: str,
        container: str,
        bitrate_kbps: int,
    ) -> MediaArtifact:
        """Extract audio into a new caller-named file; the source is never changed."""
        if not source.media_type.startswith("video/"):
            raise ValidationError("extract_audio requires a video source artifact")
        return await self._transform(
            source,
            destination=destination,
            codec=codec,
            container=container,
            bitrate_kbps=bitrate_kbps,
        )

    async def convert_audio(
        self,
        source: MediaArtifact,
        *,
        destination: Path,
        codec: str,
        container: str,
        bitrate_kbps: int,
    ) -> MediaArtifact:
        """Convert an audio artifact into a new file; the source is never changed."""
        if not source.media_type.startswith("audio/"):
            raise ValidationError("convert_audio requires an audio source artifact")
        return await self._transform(
            source,
            destination=destination,
            codec=codec,
            container=container,
            bitrate_kbps=bitrate_kbps,
        )

    async def enrich_metadata(
        self,
        source: MediaArtifact,
        *,
        destination: Path,
        metadata: Mapping[str, str],
        thumbnail: Path | None = None,
    ) -> MediaArtifact:
        """Copy supported containers with optional metadata and cover art, preserving source."""
        with request_correlation(current_request_id()):
            suffix = source.path.suffix.lower()
            if suffix not in {".mp3", ".m4a", ".mp4"}:
                raise ValidationError(
                    "metadata enrichment supports mp3, m4a, and mp4 containers"
                )
            if not all(
                isinstance(key, str) and key and isinstance(value, str)
                for key, value in metadata.items()
            ):
                raise ValidationError(
                    "metadata must map non-empty string keys to string values"
                )
            if thumbnail is not None and not thumbnail.is_file():
                raise ProviderError("thumbnail file is unavailable")
            return await self._copy_with_metadata(
                source, destination, metadata, thumbnail
            )

    async def _transform(
        self,
        source: MediaArtifact,
        *,
        destination: Path,
        codec: str,
        container: str,
        bitrate_kbps: int,
    ) -> MediaArtifact:
        with request_correlation(current_request_id()):
            encoder, muxer = _audio_pair(codec, container)
            command = [
                "-map",
                "0:a:0",
                "-vn",
                "-c:a",
                encoder,
                "-b:a",
                f"{_bitrate(bitrate_kbps)}k",
                "-f",
                muxer,
            ]
            return await self._into_destination(
                source,
                destination,
                command,
                f"audio/{'mpeg' if container == 'mp3' else 'mp4'}",
                require_audio=True,
                expected_audio_codec=codec,
            )

    async def _copy_with_metadata(
        self,
        source: MediaArtifact,
        destination: Path,
        metadata: Mapping[str, str],
        thumbnail: Path | None,
    ) -> MediaArtifact:
        command = ["-map", "0", "-c", "copy"]
        for key, value in metadata.items():
            command.extend(["-metadata", f"{key}={value}"])
        if thumbnail is not None:
            if source.media_type.startswith("video/"):
                probe = await self._run_probe(source.path)
                stream_count = sum(
                    1
                    for stream in probe.get("streams", ())
                    if isinstance(stream, Mapping)
                    and stream.get("codec_type") == "video"
                )
                if stream_count != 1:
                    raise ValidationError(
                        "video thumbnail enrichment requires exactly one source video stream"
                    )
                cover_index = "1"
            else:
                cover_index = "0"
            metadata_args = command[4:]
            command = [
                "-map",
                "0",
                "-map",
                "1",
                "-c",
                "copy",
                f"-c:v:{cover_index}",
                "mjpeg",
                f"-disposition:v:{cover_index}",
                "attached_pic",
                *metadata_args,
            ]
        return await self._into_destination(
            source,
            destination,
            command,
            mimetypes.guess_type(destination.name)[0] or source.media_type,
            extra_inputs=(thumbnail,) if thumbnail else (),
        )

    async def _into_destination(
        self,
        source: MediaArtifact,
        destination: Path,
        arguments: list[str],
        media_type: str,
        *,
        extra_inputs: tuple[Path, ...] = (),
        require_audio: bool = False,
        expected_audio_codec: str | None = None,
    ) -> MediaArtifact:
        if not source.path.is_file():
            raise ProviderError("source media file is unavailable")
        if destination == source.path or destination.exists():
            raise ValidationError(
                "destination must be a new path distinct from the source"
            )
        if destination.parent and not destination.parent.is_dir():
            raise ValidationError("destination parent directory must exist")
        temporary = Path(tempfile.mkdtemp(prefix="vcp-media-", dir=destination.parent))
        staged = temporary / destination.name
        inputs: list[str] = ["-i", os.fspath(source.path)]
        for extra in extra_inputs:
            inputs.extend(["-i", os.fspath(extra)])
        command = [
            os.fspath(self._ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-n",
            *inputs,
            *arguments,
            os.fspath(staged),
        ]
        started = monotonic()
        try:
            await self._run_process(command)
            measured = await self._run_probe(staged)
            details = self._metadata_from_probe(staged, measured)
            if require_audio and not details.media_type.startswith("audio/"):
                raise ProviderError("ffmpeg output is not an audio media file")
            if (
                expected_audio_codec is not None
                and expected_audio_codec not in details.codecs
            ):
                raise ProviderError(
                    "ffmpeg output codec does not match the requested audio codec"
                )
            try:
                os.link(staged, destination)
            except FileExistsError as exc:
                raise ValidationError(
                    "destination was created before media output could be published"
                ) from exc
            staged.unlink()
            artifact = MediaArtifact(
                destination,
                media_type,
                duration_seconds=details.duration_seconds,
                owned=True,
            )
            self._emit(
                "media transform completed",
                status="completed",
                stage="transform",
                duration_seconds=monotonic() - started,
                bytes=details.size_bytes,
            )
            return artifact
        except asyncio.CancelledError:
            self._emit(
                "media transform cancelled",
                status="cancelled",
                stage="transform",
                duration_seconds=monotonic() - started,
            )
            raise
        except Exception as exc:
            self._emit(
                "media transform failed",
                status="failed",
                stage="transform",
                error_type=type(exc).__name__,
                duration_seconds=monotonic() - started,
            )
            raise
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    async def _run_process(self, command: list[str]) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise ProviderError("configured ffmpeg binary is unavailable") from exc
        try:
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout_seconds
            )
        except asyncio.CancelledError:
            await self._stop_process(process)
            raise
        except TimeoutError as exc:
            await self._stop_process(process)
            raise ProviderError("ffmpeg media operation timed out") from exc
        if process.returncode:
            del stderr
            raise ProviderError("ffmpeg media operation failed")

    async def _run_probe(self, path: Path) -> Mapping[str, Any]:
        command = [
            os.fspath(self._ffprobe_path),
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            os.fspath(path),
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        except FileNotFoundError as exc:
            raise ProviderError("configured ffprobe binary is unavailable") from exc
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout_seconds
            )
        except asyncio.CancelledError:
            await self._stop_process(process)
            raise
        except TimeoutError as exc:
            await self._stop_process(process)
            raise ProviderError("ffprobe media operation timed out") from exc
        if process.returncode:
            raise ProviderError("ffprobe could not inspect media output")
        try:
            decoded = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError("ffprobe returned invalid media metadata") from exc
        if not isinstance(decoded, Mapping):
            raise ProviderError("ffprobe returned invalid media metadata")
        return decoded

    @staticmethod
    async def _stop_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=1)
            except TimeoutError:
                process.kill()
                await process.wait()

    @staticmethod
    def _metadata_from_probe(path: Path, payload: Mapping[str, Any]) -> MediaMetadata:
        format_data = payload.get("format")
        streams = payload.get("streams")
        if not isinstance(format_data, Mapping) or not isinstance(streams, list):
            raise ProviderError("ffprobe output lacks format or streams")
        codec_types = [
            stream.get("codec_type")
            for stream in streams
            if isinstance(stream, Mapping)
        ]
        if not codec_types:
            raise ProviderError("ffprobe output has no media streams")
        media_type = (
            "audio/" + ("mpeg" if path.suffix.lower() == ".mp3" else "mp4")
            if set(codec_types) == {"audio"}
            else "video/mp4"
        )
        duration_raw = format_data.get("duration")
        try:
            duration_value = float(duration_raw) if duration_raw is not None else None
            duration = (
                duration_value
                if duration_value is None
                or (isfinite(duration_value) and duration_value >= 0)
                else None
            )
        except (TypeError, ValueError):
            duration = None
        bitrate_raw = format_data.get("bit_rate")
        try:
            candidate = int(bitrate_raw) if bitrate_raw is not None else None
            bitrate = candidate if candidate is None or candidate >= 0 else None
        except (TypeError, ValueError, OverflowError):
            bitrate = None
        codecs = tuple(
            str(stream["codec_name"])
            for stream in streams
            if isinstance(stream, Mapping) and isinstance(stream.get("codec_name"), str)
        )
        return MediaMetadata(duration, media_type, codecs, bitrate, path.stat().st_size)

    def _emit(self, message: str, **fields: Any) -> None:
        fields["request_id"] = current_request_id()
        level = (
            logging.ERROR
            if fields.get("status") == "failed"
            else logging.WARNING
            if fields.get("status") == "retrying"
            else logging.INFO
        )
        self._logger.log(
            level, message, extra={"vcp_fields": safe_log_fields(**fields)}
        )
