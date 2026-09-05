"""yt-dlp inspection and download adapter with explicit selection and lifetime rules."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Any, Protocol
from urllib.parse import urlsplit

from ..config import MediaRequest, MediaSettings
from ..errors import ProviderError, ValidationError
from ..logging import current_request_id, request_correlation, safe_log_fields
from ..models import MediaArtifact, OutputFormat, OutputStatus, ProviderOutput
from ..pipeline import validate_platform_url


@dataclass(frozen=True, slots=True)
class MediaFormat:
    format_id: str
    extension: str
    audio_codec: str | None
    video_codec: str | None
    audio_bitrate_kbps: float | None
    total_bitrate_kbps: float | None
    exact_size_bytes: int | None
    estimated_size_bytes: int | None

    @property
    def bitrate_kbps(self) -> float | None:
        return (
            self.audio_bitrate_kbps
            if self.audio_bitrate_kbps is not None
            else self.total_bitrate_kbps
        )

    @property
    def directly_compatible_audio(self) -> bool:
        if self.video_codec not in {None, "none", "null"}:
            return False
        return self.extension.lower() in {"mp3", "m4p"} or (
            self.extension.lower() in {"mp4", "m4a"}
            and bool(self.audio_codec and self.audio_codec.lower().startswith("mp4a"))
        )


@dataclass(frozen=True, slots=True)
class MediaThumbnail:
    """Source artwork in provider preference order; dimensions may be unknown."""

    url: str
    thumbnail_id: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True, slots=True)
class MediaInspection:
    formats: tuple[MediaFormat, ...]
    duration_seconds: float | None
    title: str | None
    description: str | None
    thumbnails: tuple[MediaThumbnail, ...] = ()


@dataclass(frozen=True, slots=True)
class AudioDownloadPlan:
    selected_format_id: str
    requires_mp3_conversion: bool
    source: MediaFormat | None


@dataclass(frozen=True, slots=True)
class DownloadProgress:
    phase: str
    downloaded_bytes: int | None
    total_bytes: int | None
    total_is_estimate: bool


class _Downloader(Protocol):
    def __enter__(self) -> "_Downloader": ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...
    def extract_info(self, url: str, *, download: bool) -> Mapping[str, Any]: ...


DownloaderFactory = Callable[[Mapping[str, Any]], _Downloader]


class _QuietYtDlpLogger:
    """Prevent yt-dlp from sending URL-bearing diagnostics to application logs."""

    def debug(self, _message: str) -> None:
        pass

    def warning(self, _message: str) -> None:
        pass

    def error(self, _message: str) -> None:
        pass


def plan_audio_download(
    inspection: MediaInspection, *, compatible_bitrate_ratio: float
) -> AudioDownloadPlan:
    """Choose direct audio only when its measured bitrate meets the explicit ratio."""
    if (
        isinstance(compatible_bitrate_ratio, bool)
        or not isinstance(compatible_bitrate_ratio, (int, float))
        or not isfinite(compatible_bitrate_ratio)
        or compatible_bitrate_ratio <= 0
    ):
        raise ValidationError(
            "compatible_bitrate_ratio must be a finite positive number"
        )
    audio_formats = tuple(
        item
        for item in inspection.formats
        if item.video_codec in {None, "none", "null"}
        and item.audio_codec not in {None, "none", ""}
    )
    if not audio_formats:
        return AudioDownloadPlan("bestaudio/best", True, None)
    best = max(audio_formats, key=lambda item: item.bitrate_kbps or 0)
    compatible = tuple(item for item in audio_formats if item.directly_compatible_audio)
    if compatible:
        direct = max(compatible, key=lambda item: item.bitrate_kbps or 0)
        if (direct.bitrate_kbps or 0) >= compatible_bitrate_ratio * (
            best.bitrate_kbps or 0
        ):
            return AudioDownloadPlan(direct.format_id, False, direct)
    return AudioDownloadPlan("bestaudio/best", True, None)


class YtDlpMediaProvider:
    """Blocking yt-dlp adapter whose worker completes before owned files are removed."""

    def __init__(
        self,
        *,
        js_runtimes: Mapping[str, Mapping[str, Any]],
        downloader_factory: DownloaderFactory | None = None,
        logger: logging.Logger | None = None,
        progress: Callable[[DownloadProgress], None] | None = None,
    ) -> None:
        self._js_runtimes = dict(js_runtimes)
        self._downloader_factory = downloader_factory
        self._logger = logger or logging.getLogger("video_context_pipeline.ytdlp")
        self._progress = progress

    async def inspect_media(self, url: str, settings: MediaSettings) -> MediaInspection:
        """Inspect once and return normalized formats for an explicit coordinator choice."""
        with request_correlation(current_request_id()):
            started = monotonic()
            try:
                validate_platform_url(url)
                result = await self._run_ytdlp(
                    url, settings, download=False, format_selector=None, progress=None
                )
                formats_raw = result.get("formats")
                if not isinstance(formats_raw, Sequence):
                    raise ProviderError("yt-dlp inspection returned no formats")
                formats = tuple(
                    self._format(item)
                    for item in formats_raw
                    if isinstance(item, Mapping)
                )
                inspection = MediaInspection(
                    formats,
                    self._number(result.get("duration")),
                    result.get("title")
                    if isinstance(result.get("title"), str)
                    else None,
                    result.get("description")
                    if isinstance(result.get("description"), str)
                    else None,
                    self._thumbnails(result),
                )
                self._emit(
                    "media inspection completed",
                    status="completed",
                    stage="inspect",
                    duration_seconds=monotonic() - started,
                    output_count=len(formats),
                )
                return inspection
            except asyncio.CancelledError:
                self._emit(
                    "media inspection cancelled",
                    status="cancelled",
                    stage="inspect",
                    duration_seconds=monotonic() - started,
                )
                raise
            except Exception as exc:
                self._emit(
                    "media inspection failed",
                    status="failed",
                    stage="inspect",
                    error_type=type(exc).__name__,
                    duration_seconds=monotonic() - started,
                )
                raise

    async def download(
        self,
        url: str,
        request: MediaRequest,
        *,
        progress: Callable[[DownloadProgress], None] | None = None,
    ) -> ProviderOutput[MediaArtifact]:
        """Download the caller-selected source format without hidden conversion."""
        with request_correlation(current_request_id()):
            started = monotonic()
            selected_progress = progress if progress is not None else self._progress
            owned_directory = (
                Path(
                    tempfile.mkdtemp(
                        prefix="vcp-ytdlp-", dir=request.settings.output_directory
                    )
                )
                if request.settings.output_directory
                else Path(tempfile.mkdtemp(prefix="vcp-ytdlp-"))
            )
            try:
                validate_platform_url(url)
                result = await self._run_ytdlp(
                    url,
                    request.settings,
                    download=True,
                    format_selector=request.selected_format_id,
                    progress=selected_progress,
                    output_directory=owned_directory,
                )
                filepath = self._result_path(result, owned_directory)
                if not filepath.is_file():
                    raise ProviderError("yt-dlp did not produce a media file")
                format_data = self._format(result)
                media_type = self._media_type(format_data)
                artifact = MediaArtifact(
                    filepath,
                    media_type,
                    duration_seconds=self._number(result.get("duration")),
                    owned=True,
                    owned_directory=owned_directory,
                )
                self._emit(
                    "media download completed",
                    status="completed",
                    stage="download",
                    duration_seconds=monotonic() - started,
                    bytes=filepath.stat().st_size,
                )
                return ProviderOutput(
                    OutputFormat.MEDIA, artifact, "yt-dlp", OutputStatus.CONTENT
                )
            except asyncio.CancelledError:
                self._emit(
                    "media download cancelled",
                    status="cancelled",
                    stage="download",
                    duration_seconds=monotonic() - started,
                )
                shutil.rmtree(owned_directory, ignore_errors=True)
                raise
            except Exception as exc:
                self._emit(
                    "media download failed",
                    status="failed",
                    stage="download",
                    error_type=type(exc).__name__,
                    duration_seconds=monotonic() - started,
                )
                shutil.rmtree(owned_directory, ignore_errors=True)
                raise

    async def download_thumbnail(
        self, url: str, settings: MediaSettings
    ) -> ProviderOutput[MediaArtifact]:
        """Fetch source cover art using yt-dlp's preferred available thumbnail.

        No audio/video is downloaded. The caller owns the returned image's lifetime.
        Missing artwork is an error, including when yt-dlp only issues a warning.
        """
        with request_correlation(current_request_id()):
            validate_platform_url(url)
            directory = Path(
                tempfile.mkdtemp(prefix="vcp-thumbnail-", dir=settings.output_directory)
            )
            started = monotonic()
            try:
                result = await self._run_ytdlp(
                    url,
                    settings,
                    download=True,
                    format_selector=None,
                    progress=None,
                    output_directory=directory,
                    thumbnail_only=True,
                )
                path = self._thumbnail_path(result, directory)
                media_type = mimetypes.guess_type(path.name)[0]
                if media_type is None or not media_type.startswith("image/"):
                    raise ProviderError(
                        "yt-dlp thumbnail has an unsupported image type"
                    )
                artifact = MediaArtifact(
                    path, media_type, owned=True, owned_directory=directory
                )
                self._emit(
                    "thumbnail download completed",
                    status="completed",
                    stage="thumbnail",
                    duration_seconds=monotonic() - started,
                    bytes=path.stat().st_size,
                )
                return ProviderOutput(
                    OutputFormat.MEDIA, artifact, "yt-dlp", OutputStatus.CONTENT
                )
            except BaseException as exc:
                shutil.rmtree(directory, ignore_errors=True)
                self._emit(
                    "thumbnail download did not complete",
                    status="cancelled"
                    if isinstance(exc, asyncio.CancelledError)
                    else "failed",
                    stage="thumbnail",
                    error_type=type(exc).__name__,
                    duration_seconds=monotonic() - started,
                )
                raise

    @staticmethod
    def _thumbnail_path(result: Mapping[str, Any], directory: Path) -> Path:
        thumbnails = result.get("thumbnails")
        paths: set[Path] = set()
        if isinstance(thumbnails, (list, tuple)):
            for item in thumbnails:
                if not isinstance(item, Mapping) or not isinstance(
                    item.get("filepath"), str
                ):
                    continue
                path = Path(item["filepath"]).resolve()
                if (
                    path.parent == directory.resolve()
                    and path.is_file()
                    and path.stat().st_size > 0
                ):
                    paths.add(path)
        if len(paths) != 1:
            raise ProviderError("yt-dlp did not produce one source thumbnail")
        chosen = paths.pop()
        # Failed upstream candidates may leave partial files with another extension.
        for extra in directory.iterdir():
            if extra.resolve() != chosen:
                if extra.is_dir() and not extra.is_symlink():
                    shutil.rmtree(extra)
                else:
                    extra.unlink()
        return chosen

    @staticmethod
    def _thumbnails(result: Mapping[str, Any]) -> tuple[MediaThumbnail, ...]:
        raw = result.get("thumbnails")
        items = list(raw) if isinstance(raw, (list, tuple)) else []
        fallback = result.get("thumbnail")
        if isinstance(fallback, str) and not any(
            isinstance(item, Mapping) and item.get("url") == fallback for item in items
        ):
            items.append({"url": fallback})
        normalized = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            url = item.get("url")
            if not isinstance(url, str):
                continue
            try:
                parsed = urlsplit(url)
                if parsed.scheme not in {"https", "http"} or not parsed.hostname:
                    continue
            except ValueError:
                continue
            normalized.append(
                MediaThumbnail(
                    url,
                    item.get("id") if isinstance(item.get("id"), str) else None,
                    YtDlpMediaProvider._integer(item.get("width")),
                    YtDlpMediaProvider._integer(item.get("height")),
                )
            )
        return tuple(normalized)

    async def _run_ytdlp(
        self,
        url: str,
        settings: MediaSettings,
        *,
        download: bool,
        format_selector: str | None,
        progress: Callable[[DownloadProgress], None] | None,
        output_directory: Path | None = None,
        thumbnail_only: bool = False,
    ) -> Mapping[str, Any]:
        if settings.cookie_file is not None and not settings.cookie_file.is_file():
            raise ProviderError("configured cookie file is unavailable")
        cancelled = Event()
        loop = asyncio.get_running_loop()

        def hook(data: Mapping[str, Any]) -> None:
            if cancelled.is_set():
                raise _DownloadCancelled()
            status = data.get("status")
            if status not in {"downloading", "finished"}:
                return
            downloaded = self._integer(data.get("downloaded_bytes"))
            total = self._integer(data.get("total_bytes"))
            total_is_estimate = False
            if total is None:
                total = self._integer(data.get("total_bytes_estimate"))
                total_is_estimate = total is not None
            event = DownloadProgress(str(status), downloaded, total, total_is_estimate)
            self._emit(
                "media download progress",
                status="in_progress",
                stage="download",
                phase=event.phase,
                downloaded_bytes=downloaded,
                total_bytes=total,
                total_is_estimate=total_is_estimate,
            )
            if progress is not None:
                loop.call_soon_threadsafe(self._deliver_progress, progress, event)

        options: dict[str, Any] = {
            "noplaylist": True,
            "no_warnings": True,
            "socket_timeout": settings.request_timeout_seconds,
            "progress_hooks": [hook],
            "js_runtimes": self._js_runtimes,
            "logger": _QuietYtDlpLogger(),
            "retries": 0,
            "fragment_retries": 0,
            "extractor_retries": 0,
        }
        if thumbnail_only:
            options.update(
                skip_download=True, writethumbnail=True, write_all_thumbnails=False
            )
        if settings.cookie_file is not None:
            options["cookiefile"] = str(settings.cookie_file)
        if format_selector is not None:
            options["format"] = format_selector
        if output_directory is not None:
            options["outtmpl"] = str(
                output_directory
                / ("source.%(ext)s" if thumbnail_only else "%(id)s.%(ext)s")
            )

        def blocking() -> Mapping[str, Any]:
            factory = self._downloader_factory or self._installed_factory()
            try:
                with factory(options) as downloader:
                    return downloader.extract_info(url, download=download)
            except _DownloadCancelled as exc:
                raise asyncio.CancelledError() from exc
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise ProviderError(
                    "yt-dlp could not complete the media operation"
                ) from exc

        worker = asyncio.create_task(asyncio.to_thread(blocking))
        try:
            return await asyncio.wait_for(
                asyncio.shield(worker), timeout=settings.request_timeout_seconds
            )
        except (asyncio.CancelledError, TimeoutError) as exc:
            cancelled.set()
            with suppress(BaseException):
                await worker
            if isinstance(exc, TimeoutError):
                raise ProviderError("yt-dlp operation timed out")
            raise

    @staticmethod
    def _installed_factory() -> DownloaderFactory:
        try:
            from yt_dlp import YoutubeDL  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ProviderError(
                "yt-dlp is unavailable; install the download dependency"
            ) from exc
        return YoutubeDL

    @staticmethod
    def _format(data: Mapping[str, Any]) -> MediaFormat:
        format_id = data.get("format_id")
        extension = data.get("ext")
        if (
            not isinstance(format_id, str)
            or not format_id
            or not isinstance(extension, str)
            or not extension
        ):
            raise ProviderError(
                "yt-dlp returned a format without an identifier or extension"
            )
        return MediaFormat(
            format_id,
            extension,
            data.get("acodec") if isinstance(data.get("acodec"), str) else None,
            data.get("vcodec") if isinstance(data.get("vcodec"), str) else None,
            YtDlpMediaProvider._number(data.get("abr")),
            YtDlpMediaProvider._number(data.get("tbr")),
            YtDlpMediaProvider._integer(data.get("filesize")),
            YtDlpMediaProvider._integer(data.get("filesize_approx")),
        )

    @staticmethod
    def _result_path(result: Mapping[str, Any], directory: Path) -> Path:
        root = directory.resolve()

        def valid(candidate: object) -> Path | None:
            if not isinstance(candidate, str):
                return None
            path = Path(candidate).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                return None
            if path.is_file() and path.suffix.lower() not in {
                ".part",
                ".ytdl",
                ".json",
            }:
                return path
            return None

        for key in ("filepath", "_filename"):
            chosen = valid(result.get(key))
            if chosen is not None:
                return chosen
        requested = result.get("requested_downloads")
        if isinstance(requested, Sequence):
            requested_paths = tuple(
                valid(item.get("filepath"))
                for item in requested
                if isinstance(item, Mapping)
            )
            existing = tuple(path for path in requested_paths if path is not None)
            if len(existing) == 1:
                return existing[0]
        candidates = tuple(
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() not in {".part", ".ytdl", ".json"}
        )
        if len(candidates) == 1:
            return candidates[0]
        raise ProviderError("yt-dlp result did not identify one downloaded file")

    @staticmethod
    def _media_type(format_data: MediaFormat) -> str:
        if format_data.video_codec not in {None, "none"}:
            return mimetypes.guess_type(f"x.{format_data.extension}")[0] or "video/mp4"
        if format_data.extension.lower() in {"mp4", "m4a", "m4p"}:
            return "audio/mp4"
        return mimetypes.guess_type(f"x.{format_data.extension}")[0] or "audio/mpeg"

    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        number = float(value)
        return number if isfinite(number) and number >= 0 else None

    @staticmethod
    def _integer(value: object) -> int | None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value < 0
            or int(value) != value
        ):
            return None
        return int(value)

    def _deliver_progress(
        self, callback: Callable[[DownloadProgress], None], event: DownloadProgress
    ) -> None:
        try:
            callback(event)
        except Exception as exc:
            self._emit(
                "media progress callback failed",
                status="failed",
                stage="download",
                error_type=type(exc).__name__,
            )

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


class _DownloadCancelled(Exception):
    pass


class YtDlpMetadataProvider:
    """Protocol-compatible metadata adapter using one explicit media inspection."""

    def __init__(
        self, *, settings: MediaSettings, media_provider: YtDlpMediaProvider
    ) -> None:
        self._settings = settings
        self._media_provider = media_provider

    async def inspect(self, url: str) -> ProviderOutput[Mapping[str, Any]]:
        inspection = await self._media_provider.inspect_media(url, self._settings)
        formats = tuple(
            {
                "format_id": item.format_id,
                "extension": item.extension,
                "audio_codec": item.audio_codec,
                "video_codec": item.video_codec,
                "audio_bitrate_kbps": item.audio_bitrate_kbps,
                "total_bitrate_kbps": item.total_bitrate_kbps,
                "exact_size_bytes": item.exact_size_bytes,
                "estimated_size_bytes": item.estimated_size_bytes,
            }
            for item in inspection.formats
        )
        return ProviderOutput(
            OutputFormat.METADATA,
            {
                "title": inspection.title,
                "description": inspection.description,
                "duration_seconds": inspection.duration_seconds,
                "formats": formats,
                "thumbnails": tuple(asdict(item) for item in inspection.thumbnails),
            },
            "yt-dlp",
            OutputStatus.CONTENT,
        )
