"""Atomic orchestration over independently injectable provider components."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from contextlib import suppress
from time import monotonic
from typing import Any
from urllib.parse import urlparse

from .config import PipelineRequest, TranscriptRequest, VisualRequest
from .errors import PipelineError, ValidationError
from .formatting import transcript_plain_text
from .logging import current_request_id, request_correlation, safe_log_fields
from .models import (
    MediaArtifact,
    OutputFormat,
    OutputStatus,
    PipelineResult,
    ProviderOutput,
    TranscriptSegment,
    validate_video_events,
)
from .protocols import (
    MediaProvider,
    MetadataProvider,
    TranscriptProvider,
    VisualProvider,
)

_SUPPORTED_HOSTS = (
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "instagr.am",
    "tiktok.com",
)


def validate_platform_url(url: str) -> str:
    """Accept only public YouTube, Instagram, or TikTok URLs and their subdomains."""
    if not isinstance(url, str) or not url.strip():
        raise ValidationError("platform URL must be a non-empty string")
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username
        or parsed.password
        or not parsed.hostname
    ):
        raise ValidationError(
            "platform URL must be a public http(s) URL without credentials"
        )
    host = parsed.hostname.lower().rstrip(".")
    if not any(
        host == allowed or host.endswith(f".{allowed}") for allowed in _SUPPORTED_HOSTS
    ):
        raise ValidationError(
            "platform URL must belong to YouTube, Instagram, or TikTok"
        )
    return url


class Pipeline:
    """Run requested components atomically; adapters are supplied by the application."""

    def __init__(
        self,
        *,
        metadata_provider: MetadataProvider | None = None,
        transcript_provider: TranscriptProvider | None = None,
        media_provider: MediaProvider | None = None,
        visual_provider: VisualProvider | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._metadata_provider = metadata_provider
        self._transcript_provider = transcript_provider
        self._media_provider = media_provider
        self._visual_provider = visual_provider
        self._logger = logger or logging.getLogger("video_context_pipeline.pipeline")

    async def run(self, url: str, request: PipelineRequest) -> PipelineResult:
        """Validate before side effects, then return every requested output or raise."""
        with request_correlation(current_request_id()):
            started = monotonic()
            self._emit("pipeline started", status="started", stage="pipeline")
            produced: list[ProviderOutput[Any]] = []
            internal_media: ProviderOutput[MediaArtifact] | None = None
            stage_tasks: dict[str, asyncio.Task[ProviderOutput[Any]]] = {}
            try:
                validate_platform_url(url)
                self._validate_providers(request)
                async with asyncio.TaskGroup() as group:
                    if request.metadata:
                        assert self._metadata_provider is not None
                        stage_tasks["metadata"] = group.create_task(
                            self._metadata_provider.inspect(url)
                        )  # type: ignore[union-attr]
                    if request.transcript is not None:
                        assert self._transcript_provider is not None
                        stage_tasks["transcript"] = group.create_task(
                            self._transcript_provider.transcribe(
                                url, request.transcript
                            )
                        )  # type: ignore[union-attr]
                    media_request = request.media or request.visual_media
                    if media_request is not None:
                        assert self._media_provider is not None
                        stage_tasks["media"] = group.create_task(
                            self._media_provider.download(url, media_request)
                        )  # type: ignore[union-attr]
                completed = {name: task.result() for name, task in stage_tasks.items()}
                produced.extend(completed.values())
                self._validate_stage_outputs(completed, request)
                if "media" in completed:
                    internal_media = completed["media"]  # type: ignore[assignment]

                visual_output: ProviderOutput[Any] | None = None
                if request.visual is not None:
                    assert internal_media is not None
                    if (
                        request.visual.settings.processing_mode.value == "automatic"
                        and internal_media.data.duration_seconds is None
                    ):
                        raise ValidationError(
                            "automatic visual processing requires known media duration_seconds"
                        )
                    context = None
                    if request.include_transcript_context:
                        transcript = completed["transcript"]
                        context = transcript_plain_text(transcript.data)  # type: ignore[arg-type]
                    visual_output = await self._visual_provider.understand(  # type: ignore[union-attr]
                        internal_media.data,
                        request.visual,
                        transcript_context=context,
                    )
                    produced.append(visual_output)
                    self._validate_visual_output(visual_output, request.visual)

                outputs = {
                    name: output
                    for name, output in completed.items()
                    if name != "media" or request.media is not None
                }
                if visual_output is not None:
                    outputs["visual"] = visual_output
                if internal_media is not None and request.media is None:
                    internal_media.data.cleanup()
                    self._emit(
                        "pipeline cleanup",
                        status="completed",
                        stage="cleanup",
                        cleanup="internal_media",
                    )
                self._emit(
                    "pipeline completed",
                    status="completed",
                    stage="pipeline",
                    duration_seconds=monotonic() - started,
                    output_count=len(outputs),
                )
                return PipelineResult(outputs=outputs)
            except asyncio.CancelledError:
                self._emit("pipeline cancelled", status="cancelled", stage="pipeline")
                self._cleanup_outputs(produced)
                self._cleanup_completed_tasks(stage_tasks)
                raise
            except Exception as exc:
                self._emit(
                    "pipeline failed",
                    status="failed",
                    stage="pipeline",
                    error_type=type(exc).__name__,
                    duration_seconds=monotonic() - started,
                )
                self._cleanup_outputs(produced)
                self._cleanup_completed_tasks(stage_tasks)
                if isinstance(exc, (ValidationError, PipelineError)):
                    raise
                raise PipelineError(
                    "pipeline request failed; no partial outputs were returned"
                ) from exc

    def _validate_providers(self, request: PipelineRequest) -> None:
        if request.metadata and self._metadata_provider is None:
            raise ValidationError("metadata provider is required")
        if request.transcript is not None and self._transcript_provider is None:
            raise ValidationError("transcript provider is required")
        if (
            request.media is not None or request.visual is not None
        ) and self._media_provider is None:
            raise ValidationError("media provider is required")
        if request.visual is not None and self._visual_provider is None:
            raise ValidationError("visual provider is required")

    def _validate_stage_outputs(
        self, outputs: Mapping[str, ProviderOutput[Any]], request: PipelineRequest
    ) -> None:
        if "metadata" in outputs:
            output = outputs["metadata"]
            if output.format is not OutputFormat.METADATA or not isinstance(
                output.data, Mapping
            ):
                raise ValidationError("metadata provider returned an invalid schema")
        if "transcript" in outputs:
            assert request.transcript is not None
            self._validate_transcript_output(outputs["transcript"], request.transcript)
        if "media" in outputs:
            output = outputs["media"]
            if output.format is not OutputFormat.MEDIA or not isinstance(
                output.data, MediaArtifact
            ):
                raise ValidationError("media provider returned an invalid schema")

    @staticmethod
    def _validate_transcript_output(
        output: ProviderOutput[Any], request: TranscriptRequest
    ) -> None:
        if output.format is not request.format:
            raise ValidationError(
                "transcript provider did not return the requested format"
            )
        if request.format is OutputFormat.TRANSCRIPT_TEXT:
            if not isinstance(output.data, str):
                raise ValidationError("plain-text transcript must be a string")
        else:
            if not isinstance(output.data, Sequence) or isinstance(
                output.data, (str, bytes)
            ):
                raise ValidationError("segment transcript must be a sequence")
            if not all(
                isinstance(segment, TranscriptSegment) for segment in output.data
            ):
                raise ValidationError("segment transcript contains malformed segments")
        if output.status is OutputStatus.EMPTY and output.data not in ("", (), []):
            raise ValidationError("empty transcript success must have empty data")

    @staticmethod
    def _validate_visual_output(
        output: ProviderOutput[Any], request: VisualRequest
    ) -> None:
        if output.format is not request.format:
            raise ValidationError("visual provider did not return the requested format")
        if request.format is OutputFormat.VIDEO_TEXT:
            if not isinstance(output.data, str):
                raise ValidationError("video text must be a string")
        else:
            if not isinstance(output.data, Sequence) or isinstance(
                output.data, (str, bytes)
            ):
                raise ValidationError("video events must be a sequence")
            validate_video_events(
                output.data,  # type: ignore[arg-type]
                request.timestamp_mode,
                analyzed_start_seconds=request.analyzed_start_seconds,
                analyzed_end_seconds=request.analyzed_end_seconds,
                windows=request.windows,
            )
        if output.status is OutputStatus.EMPTY and output.data not in ("", (), []):
            raise ValidationError("empty visual success must have empty data")

    def _cleanup_outputs(self, outputs: Sequence[ProviderOutput[Any]]) -> None:
        for output in outputs:
            if output.format is OutputFormat.MEDIA and isinstance(
                output.data, MediaArtifact
            ):
                try:
                    output.data.cleanup()
                    self._emit(
                        "pipeline cleanup",
                        status="completed",
                        stage="cleanup",
                        cleanup="owned_media",
                    )
                except OSError as exc:
                    self._emit(
                        "pipeline cleanup",
                        status="failed",
                        stage="cleanup",
                        cleanup="owned_media",
                        error_type=type(exc).__name__,
                    )

    def _cleanup_completed_tasks(
        self, tasks: Mapping[str, asyncio.Task[ProviderOutput[Any]]]
    ) -> None:
        """Recover successful sibling media results when a TaskGroup exits early."""
        for task in tasks.values():
            if task.cancelled() or not task.done():
                continue
            with suppress(BaseException):
                self._cleanup_outputs((task.result(),))

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
