"""Translate page settings and compose existing public library components."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from video_context_pipeline import (
    GeminiSettings,
    MediaArtifact,
    MediaRequest,
    MediaSettings,
    OutputFormat,
    Pipeline,
    PipelineRequest,
    SupadataSettings,
    TimestampMode,
    TimeWindow,
    TranscriptRequest,
    VisualRequest,
    validate_platform_url,
)
from video_context_pipeline.media import FFmpegMediaTools
from video_context_pipeline.providers.gemini import GeminiProvider
from video_context_pipeline.providers.supadata import SupadataProvider
from video_context_pipeline.providers.ytdlp import (
    AudioDownloadPlan,
    YtDlpMediaProvider,
    YtDlpMetadataProvider,
    plan_audio_download,
)

from .observability import Monitor, Step
from .schema import JobRequest

T = TypeVar("T")


class InputError(ValueError):
    """A safe, demo-authored request error containing no submitted values."""


def required(value: T | None, name: str) -> T:
    if value is None:
        raise InputError(f"{name} is required for this operation.")
    return value


def url_digest(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


@dataclass(frozen=True)
class ReviewedPlan:
    url_digest: str
    plan: AudioDownloadPlan


@dataclass
class Prepared:
    request: JobRequest
    directory: Path
    media: MediaSettings | None = None
    transcript: TranscriptRequest | None = None
    visual: VisualRequest | None = None
    pipeline: PipelineRequest | None = None
    source: MediaArtifact | None = None
    cover: MediaArtifact | None = None
    reviewed: ReviewedPlan | None = None
    cookie_path: Path | None = None


def prepare(
    request: JobRequest,
    directory: Path,
    executables: dict[str, list[str]],
    artifact: Callable[[str], MediaArtifact],
    reviewed: ReviewedPlan | None = None,
) -> Prepared:
    """Validate all applicable settings before any provider call or output creation."""
    action = request.action
    result = Prepared(request, directory, reviewed=reviewed)
    allowed = {"action"}

    def need(name: str) -> Any:
        allowed.add(name)
        return required(getattr(request, name), name)

    url_actions = {
        "inspect",
        "audio_plan",
        "download",
        "thumbnail",
        "transcribe",
        "pipeline",
        "audio_workflow",
    }
    if action in url_actions:
        try:
            validate_platform_url(need("url"))
        except Exception:
            raise InputError(
                "Provide a supported YouTube, Instagram, or TikTok URL."
            ) from None
    pipeline = need("pipeline") if action == "pipeline" else None
    uses_media = action in {
        "inspect",
        "audio_plan",
        "download",
        "thumbnail",
        "audio_workflow",
    } or (
        pipeline is not None
        and (pipeline.metadata or pipeline.media or pipeline.visual)
    )
    if uses_media:
        media = need("media")
        if media.runtime_path not in executables.get(media.runtime_name, []):
            raise InputError(
                "media.runtime_path must select a detected executable for runtime_name."
            )
        if media.cookie_artifact_id is not None:
            result.cookie_path = artifact(media.cookie_artifact_id).path
        elif media.cookie_text is not None:
            result.cookie_path = directory / "cookies.txt"
        result.media = MediaSettings(
            media.request_timeout_seconds, result.cookie_path, directory
        )

    if action == "transcribe" or (pipeline and pipeline.transcript):
        transcript = need("transcript")
        key = os.environ.get("SUPADATA_API_KEY", "")
        if not key.strip():
            raise InputError("SUPADATA_API_KEY is not available on the server.")
        result.transcript = TranscriptRequest(
            OutputFormat(transcript.format),
            SupadataSettings(api_key=key, **transcript.settings.model_dump()),
        )
    if action == "visual" or (pipeline and pipeline.visual):
        visual = need("visual")
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key.strip():
            raise InputError("GEMINI_API_KEY is not available on the server.")
        if pipeline and visual.transcript_context is not None:
            raise InputError(
                "Pipeline transcript context must come from its transcript output."
            )
        result.visual = VisualRequest(
            format=OutputFormat(visual.format),
            settings=GeminiSettings(api_key=key, **visual.settings.model_dump()),
            timestamp_mode=TimestampMode(visual.timestamp_mode),
            windows=tuple(TimeWindow(**item.model_dump()) for item in visual.windows),
            inspection_windows=tuple(
                TimeWindow(**item.model_dump()) for item in visual.inspection_windows
            ),
            analyzed_start_seconds=visual.analyzed_start_seconds,
            analyzed_end_seconds=visual.analyzed_end_seconds,
        )
    if action in {"visual", "probe", "extract", "convert", "enrich"}:
        result.source = artifact(need("input_artifact_id"))
        expected = {"visual": "video/", "extract": "video/", "convert": "audio/"}.get(
            action
        )
        if expected and not result.source.media_type.startswith(expected):
            raise InputError(
                f"{action} needs a compatible {expected.rstrip('/')} artifact; probe the input to measure its type."
            )
        if (
            action == "visual"
            and result.visual
            and result.visual.settings.processing_mode.value == "automatic"
            and result.source.duration_seconds is None
        ):
            raise InputError(
                "Automatic processing requires known duration; probe the input first."
            )
    if action == "audio_plan":
        need("compatible_bitrate_ratio")
    if action == "download":
        need("selected_format_id")
    if action == "audio_workflow":
        need("plan_job_id")
        if reviewed is None or reviewed.url_digest != url_digest(
            required(request.url, "url")
        ):
            raise InputError(
                "Review a completed audio plan for this URL before running the workflow."
            )
    conversion = action in {"extract", "convert"} or (
        action == "audio_workflow"
        and reviewed is not None
        and reviewed.plan.requires_mp3_conversion
    )
    if conversion:
        transform = need("transform")
        if (transform.codec, transform.container) not in {
            ("mp3", "mp3"),
            ("aac", "m4a"),
            ("aac", "mp4"),
        }:
            raise InputError(
                "Supported codec/container pairs: mp3/mp3, aac/m4a, aac/mp4."
            )
        if action == "audio_workflow" and (transform.codec, transform.container) != (
            "mp3",
            "mp3",
        ):
            raise InputError(
                "This reviewed audio plan requires explicit mp3/mp3 conversion settings."
            )
    if action == "enrich" or (
        action == "audio_workflow" and request.enrichment is not None
    ):
        enrichment = need("enrichment")
        if action == "enrich" and enrichment.source_cover:
            raise InputError(
                "source_cover applies only to the audio workflow; choose an image artifact here."
            )
        if enrichment.cover_artifact_id:
            result.cover = artifact(enrichment.cover_artifact_id)
            if not result.cover.media_type.startswith("image/"):
                raise InputError("Cover art must be an image artifact.")
        if result.source and result.source.path.suffix.lower() not in {
            ".mp3",
            ".m4a",
            ".mp4",
        }:
            raise InputError("Metadata enrichment supports mp3, m4a, and mp4 files.")
        if (
            action == "audio_workflow"
            and reviewed
            and not conversion
            and reviewed.plan.source
            and reviewed.plan.source.extension.lower() not in {"mp3", "m4a", "mp4"}
        ):
            raise InputError(
                "The reviewed source container cannot be enriched by the library. Choose another supported operation."
            )
    if action in {"probe", "extract", "convert", "enrich"} or (
        action == "audio_workflow" and (conversion or request.enrichment is not None)
    ):
        local = need("local")
        for name in ("ffmpeg", "ffprobe"):
            if getattr(local, f"{name}_path") not in executables.get(name, []):
                raise InputError(
                    f"local.{name}_path must select a detected executable."
                )
    if pipeline is not None:
        media_request = None
        visual_media = None
        if pipeline.media:
            media_request = MediaRequest(
                required(result.media, "media"),
                required(pipeline.selected_format_id, "pipeline.selected_format_id"),
            )
        elif pipeline.selected_format_id is not None:
            raise InputError("pipeline.selected_format_id requires returned media.")
        if pipeline.visual:
            visual_media = MediaRequest(
                required(result.media, "media"),
                required(pipeline.visual_format_id, "pipeline.visual_format_id"),
            )
        elif pipeline.visual_format_id is not None:
            raise InputError("pipeline.visual_format_id requires visual analysis.")
        result.pipeline = PipelineRequest(
            metadata=pipeline.metadata,
            transcript=result.transcript,
            visual=result.visual,
            media=media_request,
            visual_media=visual_media,
            include_transcript_context=pipeline.include_transcript_context,
        )
    irrelevant = {
        name
        for name in request.model_fields_set - allowed
        if getattr(request, name) is not None
    }
    if irrelevant:
        raise InputError(
            "Settings do not apply to this operation: " + ", ".join(sorted(irrelevant))
        )
    return result


def steps_for(prepared: Prepared) -> dict[str, Step]:
    action, pipeline = prepared.request.action, prepared.pipeline
    if pipeline:
        first = []
        if pipeline.metadata:
            first.append("metadata")
        if pipeline.transcript:
            first.append("transcript")
        if pipeline.media or pipeline.visual_media:
            first.append("download")
        steps = {name: Step(name, []) for name in first}
        steps["barrier"] = Step("barrier", first)
        if pipeline.visual:
            steps["visual"] = Step("visual", ["barrier"])
        return steps
    names = [action]
    if action == "audio_plan":
        names = ["inspect", "audio_plan"]
    if action == "audio_workflow":
        names = ["download"]
        if prepared.reviewed and prepared.reviewed.plan.requires_mp3_conversion:
            names.append("convert")
        if prepared.request.enrichment:
            if prepared.request.enrichment.source_cover:
                names.append("thumbnail")
            names.append("enrich")
    return {
        name: Step(name, [] if index == 0 else [names[index - 1]])
        for index, name in enumerate(names)
    }


class TrackedProvider:
    """Protocol adapter observing calls while leaving library interfaces intact."""

    def __init__(self, provider: Any, monitor: Monitor) -> None:
        self.provider, self.monitor = provider, monitor

    async def inspect(self, url: str) -> Any:
        return await self.monitor.run("metadata", lambda: self.provider.inspect(url))

    async def download(self, url: str, request: MediaRequest) -> Any:
        return await self.monitor.run(
            "download", lambda: self.provider.download(url, request)
        )

    async def transcribe(self, url: str, request: TranscriptRequest) -> Any:
        return await self.monitor.run(
            "transcript", lambda: self.provider.transcribe(url, request)
        )

    async def understand(
        self,
        media: MediaArtifact,
        request: VisualRequest,
        *,
        transcript_context: str | None,
    ) -> Any:
        return await self.monitor.run(
            "visual",
            lambda: self.provider.understand(
                media, request, transcript_context=transcript_context
            ),
        )


async def execute(prepared: Prepared, monitor: Monitor) -> Any:
    request, directory = prepared.request, prepared.directory
    action = request.action
    logger = monitor.logger()
    provider = None
    if prepared.media:
        settings = required(request.media, "media")

        def progress(value: Any) -> None:
            if "download" in monitor.steps:
                monitor.steps["download"].progress = {
                    "phase": value.phase,
                    "downloaded_bytes": value.downloaded_bytes,
                    "total_bytes": value.total_bytes,
                    "total_is_estimate": value.total_is_estimate,
                }

        provider = YtDlpMediaProvider(
            js_runtimes={settings.runtime_name: {"path": settings.runtime_path}},
            logger=logger,
            progress=progress,
        )
    tools = None
    if request.local:
        tools = FFmpegMediaTools(
            ffmpeg_path=Path(request.local.ffmpeg_path),
            ffprobe_path=Path(request.local.ffprobe_path),
            timeout_seconds=request.local.timeout_seconds,
            logger=logger,
        )
    url = request.url or ""
    if action == "pipeline":
        pipeline = required(prepared.pipeline, "pipeline")
        return await Pipeline(
            metadata_provider=TrackedProvider(
                YtDlpMetadataProvider(
                    settings=required(prepared.media, "media"),
                    media_provider=required(provider, "provider"),
                ),
                monitor,
            )
            if pipeline.metadata
            else None,
            media_provider=TrackedProvider(provider, monitor) if provider else None,
            transcript_provider=TrackedProvider(
                SupadataProvider(logger=logger), monitor
            )
            if pipeline.transcript
            else None,
            visual_provider=TrackedProvider(GeminiProvider(logger=logger), monitor)
            if pipeline.visual
            else None,
            logger=logger,
        ).run(url, pipeline)
    if action in {"inspect", "audio_plan"}:
        inspection = await monitor.run(
            "inspect",
            lambda: required(provider, "provider").inspect_media(
                url, required(prepared.media, "media")
            ),
        )
        if action == "inspect":
            return inspection

        async def plan() -> Any:
            return plan_audio_download(
                inspection,
                compatible_bitrate_ratio=required(
                    request.compatible_bitrate_ratio, "compatible_bitrate_ratio"
                ),
            )

        return {"inspection": inspection, "plan": await monitor.run("audio_plan", plan)}
    if action == "download":
        return await monitor.run(
            "download",
            lambda: required(provider, "provider").download(
                url,
                MediaRequest(
                    required(prepared.media, "media"),
                    required(request.selected_format_id, "selected_format_id"),
                ),
            ),
        )
    if action == "thumbnail":
        return await monitor.run(
            "thumbnail",
            lambda: required(provider, "provider").download_thumbnail(
                url, required(prepared.media, "media")
            ),
        )
    if action == "transcribe":
        return await monitor.run(
            "transcribe",
            lambda: SupadataProvider(logger=logger).transcribe(
                url, required(prepared.transcript, "transcript")
            ),
        )
    if action == "visual":
        return await monitor.run(
            "visual",
            lambda: GeminiProvider(logger=logger).understand(
                required(prepared.source, "input"),
                required(prepared.visual, "visual"),
                transcript_context=required(
                    request.visual, "visual"
                ).transcript_context,
            ),
        )
    if action == "probe":
        return await monitor.run(
            "probe",
            lambda: required(tools, "local").probe(
                required(prepared.source, "input").path
            ),
        )
    source = prepared.source
    if action == "audio_workflow":
        reviewed_plan = required(prepared.reviewed, "plan").plan
        downloaded = await monitor.run(
            "download",
            lambda: required(provider, "provider").download(
                url,
                MediaRequest(
                    required(prepared.media, "media"), reviewed_plan.selected_format_id
                ),
            ),
        )
        source = downloaded.data
    if request.transform:
        transform = request.transform
        actual_source = required(source, "input")
        method = (
            required(tools, "local").extract_audio
            if actual_source.media_type.startswith("video/")
            else required(tools, "local").convert_audio
        )
        source = await monitor.run(
            "extract" if action == "extract" else "convert",
            lambda: method(
                actual_source,
                destination=directory / f"audio.{transform.container}",
                codec=transform.codec,
                container=transform.container,
                bitrate_kbps=transform.bitrate_kbps,
            ),
        )
    if request.enrichment:
        cover = prepared.cover
        if request.enrichment.source_cover:
            image = await monitor.run(
                "thumbnail",
                lambda: required(provider, "provider").download_thumbnail(
                    url, required(prepared.media, "media")
                ),
            )
            cover = image.data
        actual_source = required(source, "input")
        source = await monitor.run(
            "enrich",
            lambda: required(tools, "local").enrich_metadata(
                actual_source,
                destination=directory / f"tagged{actual_source.path.suffix}",
                metadata=required(request.enrichment, "enrichment").metadata,
                thumbnail=cover.path if cover else None,
            ),
        )
    return required(source, "input")
