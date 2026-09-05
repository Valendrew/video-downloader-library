"""Strict demo wire contracts. Secrets are deliberately absent from these models."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DownloadSettings(WireModel):
    request_timeout_seconds: Positive = Field(
        description="Source request timeout in seconds. Example: 60."
    )
    runtime_name: Literal["node", "deno"] = Field(
        description="Installed JavaScript runtime for source access. Select explicitly."
    )
    runtime_path: Text = Field(
        description="Select a detected path for the chosen runtime on the server."
    )
    cookie_text: str | None = Field(
        default=None,
        description="Optional Netscape cookie file contents; temporary and never logged.",
    )
    cookie_artifact_id: str | None = Field(
        default=None,
        description="Optional uploaded cookie file. Choose upload OR pasted contents.",
    )

    @model_validator(mode="after")
    def one_cookie(self) -> DownloadSettings:
        if self.cookie_text is not None and self.cookie_artifact_id is not None:
            raise ValueError("Choose only one cookie input")
        return self


class SupadataOptions(WireModel):
    request_timeout_seconds: Positive = Field(
        description="Timeout for each HTTP request, in seconds. Example: 30."
    )
    job_timeout_seconds: Positive = Field(
        description="Deadline for a queued transcript job, in seconds. Example: 180."
    )
    poll_interval_seconds: Positive = Field(
        description="Seconds between job-status requests. Example: 2."
    )
    max_retries: Annotated[int, Field(ge=0)] = Field(
        description="Retry count; explicitly choose 0 to disable retries."
    )
    retry_delay_seconds: Positive = Field(
        description="Delay between retries, in seconds. Example: 1."
    )


class GeminiOptions(WireModel):
    model: Literal["gemini-3.8-flash", "gemini-3.5-flash-lite"] = Field(
        description="Gemini model. Flash Lite also supports minimal thinking."
    )
    media_resolution: Literal["low", "medium", "high"] = Field(
        description="Provider video media resolution."
    )
    thinking_level: Literal["minimal", "low", "medium", "high"] = Field(
        description="Minimal is only supported by Flash Lite; other models accept low, medium, high."
    )
    processing_mode: Literal["static", "agentic", "automatic"] = Field(
        description="Static samples at explicit FPS. Agentic inspects on demand. Automatic uses the duration threshold."
    )
    static_fps: Positive | None = Field(
        default=None,
        description="Required for static and automatic modes; omit for agentic. Example: 1.",
    )
    agentic_threshold_seconds: Positive | None = Field(
        default=None,
        description="Required only for automatic mode. Example: 60 seconds. Media duration must be known.",
    )
    request_timeout_seconds: Positive = Field(
        description="Timeout per request, in seconds. Example: 60."
    )
    max_retries: Annotated[int, Field(ge=0)] = Field(
        description="Explicit retry count, including 0."
    )
    retry_backoff_seconds: Positive = Field(
        description="Retry backoff in seconds. Example: 1."
    )
    file_upload_threshold_bytes: Annotated[int, Field(gt=0)] = Field(
        description="Use file upload above this byte threshold. Example: 20000000."
    )
    file_poll_deadline_seconds: Positive = Field(
        description="Deadline for uploaded-file processing, in seconds. Example: 120."
    )
    file_poll_interval_seconds: Positive = Field(
        description="Seconds between uploaded-file readiness checks. Example: 2."
    )


class Window(WireModel):
    start_seconds: NonNegative
    end_seconds: Positive


class TranscriptOptions(WireModel):
    format: Literal["transcript_text", "transcript_segments"] = Field(
        description="Readable text or timed transcript segments; Supadata only."
    )
    settings: SupadataOptions


class VisualOptions(WireModel):
    format: Literal["video_text", "video_events"] = Field(
        description="Readable visual description or structured events."
    )
    timestamp_mode: Literal["none", "approximate", "windows"] = Field(
        description="Untimed events, approximate timestamps, or labels from supplied windows."
    )
    analyzed_start_seconds: NonNegative = Field(
        description="Explicit start of analyzed interval, in seconds. Example: 0."
    )
    analyzed_end_seconds: NonNegative | None = Field(
        default=None,
        description="Optional end of analyzed interval; blank means the available end.",
    )
    windows: list[Window] = Field(
        default_factory=list,
        description='For windowed events only. JSON example: [{"start_seconds":0,"end_seconds":10}].',
    )
    inspection_windows: list[Window] = Field(
        default_factory=list,
        description='Optional inspection intervals. JSON example: [{"start_seconds":0,"end_seconds":5}].',
    )
    transcript_context: str | None = Field(
        default=None,
        description="Optional context for independent video understanding. Pipeline context comes from its transcript.",
    )
    settings: GeminiOptions


class LocalOptions(WireModel):
    ffmpeg_path: Text = Field(
        description="Explicit detected FFmpeg executable on the server."
    )
    ffprobe_path: Text = Field(
        description="Explicit detected ffprobe executable on the server."
    )
    timeout_seconds: Positive = Field(
        description="Local processing timeout, in seconds. Example: 60."
    )


class TransformOptions(WireModel):
    codec: Literal["mp3", "aac"] = Field(
        description="Supported pairs: mp3/mp3, aac/m4a, aac/mp4. Audio workflow conversion requires mp3/mp3."
    )
    container: Literal["mp3", "m4a", "mp4"] = Field(
        description="Output container; must match the selected codec."
    )
    bitrate_kbps: Annotated[int, Field(gt=0)] = Field(
        description="Explicit output audio bitrate in kilobits/second. Example: 192."
    )


class EnrichmentOptions(WireModel):
    metadata: dict[Text, str] = Field(
        description='String tags, as JSON. Example: {"title":"Example", "artist":"Creator"}. Use {} for cover art only.'
    )
    cover_artifact_id: str | None = Field(
        default=None, description="Optional uploaded or produced image artifact."
    )
    source_cover: bool = Field(
        default=False,
        description="Audio workflow only: download source artwork using the library thumbnail service.",
    )

    @model_validator(mode="after")
    def one_cover(self) -> EnrichmentOptions:
        if self.source_cover and self.cover_artifact_id:
            raise ValueError("Choose one cover source")
        return self


class PipelineOptions(WireModel):
    metadata: bool = False
    transcript: bool = False
    visual: bool = False
    media: bool = False
    include_transcript_context: bool = Field(
        default=False,
        description="Requires both transcript and visual outputs. Passes readable transcript text to visual analysis.",
    )
    selected_format_id: Text | None = Field(
        default=None,
        description="Required to return downloaded media. Use an inspected format ID or explicit yt-dlp selector.",
    )
    visual_format_id: Text | None = Field(
        default=None,
        description="Required for visual analysis. Must match returned media selection if both are selected.",
    )


Action = Literal[
    "inspect",
    "audio_plan",
    "download",
    "thumbnail",
    "transcribe",
    "visual",
    "probe",
    "extract",
    "convert",
    "enrich",
    "pipeline",
    "audio_workflow",
]


class JobRequest(WireModel):
    action: Action
    url: Text | None = None
    media: DownloadSettings | None = None
    transcript: TranscriptOptions | None = None
    visual: VisualOptions | None = None
    local: LocalOptions | None = None
    transform: TransformOptions | None = None
    enrichment: EnrichmentOptions | None = None
    pipeline: PipelineOptions | None = None
    input_artifact_id: Text | None = None
    selected_format_id: Text | None = Field(
        default=None, description="Explicit inspected format ID or yt-dlp selector."
    )
    compatible_bitrate_ratio: Positive | None = Field(
        default=None,
        description="Audio plan quality ratio. Example: 0.80 matches the reference quality policy.",
    )
    plan_job_id: Text | None = Field(
        default=None,
        description="Completed audio-plan job reviewed before downloading.",
    )


State = Literal["pending", "running", "completed", "failed", "cancelling", "cancelled"]


class ArtifactInfo(WireModel):
    id: str
    filename: str
    media_type: str
    size_bytes: int
    duration_seconds: float | None
    download_url: str
    preview_url: str


class StepInfo(WireModel):
    id: str
    dependencies: list[str]
    state: State
    elapsed_seconds: float
    progress: dict[str, Any] | None = None


class JobInfo(WireModel):
    id: str
    action: Action
    state: State
    elapsed_seconds: float
    steps: list[StepInfo]
    logs: list[dict[str, Any]]
    result: Any = None
    error: str | None = None


class JobCreated(WireModel):
    id: str
    state: State
