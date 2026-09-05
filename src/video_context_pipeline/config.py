"""Explicit typed settings and a side-effect-free environment loader."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from pathlib import Path

from .errors import ConfigurationError
from .models import OutputFormat, TimestampMode, TimeWindow


class GeminiModel(StrEnum):
    FLASH_3_8 = "gemini-3.8-flash"
    FLASH_LITE_3_5 = "gemini-3.5-flash-lite"


class GeminiResolution(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GeminiProcessingMode(StrEnum):
    STATIC = "static"
    AGENTIC = "agentic"
    AUTOMATIC = "automatic"


_THINKING_LEVELS = {
    GeminiModel.FLASH_3_8: frozenset({"low", "medium", "high"}),
    GeminiModel.FLASH_LITE_3_5: frozenset({"minimal", "low", "medium", "high"}),
}


def _number(value: object, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{name} must be a finite number")
    number = float(value)
    if not isfinite(number) or (positive and number <= 0):
        raise ConfigurationError(
            f"{name} must be a finite positive number"
            if positive
            else f"{name} must be finite"
        )
    return number


def _integer(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigurationError(f"{name} must be an integer at least {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class GeminiSettings:
    api_key: str = field(repr=False)
    model: GeminiModel
    media_resolution: GeminiResolution
    thinking_level: str
    processing_mode: GeminiProcessingMode
    static_fps: float | None
    agentic_threshold_seconds: float | None
    request_timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    file_upload_threshold_bytes: int
    file_poll_deadline_seconds: float
    file_poll_interval_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ConfigurationError("Gemini api_key is required")
        try:
            object.__setattr__(self, "model", GeminiModel(self.model))
            object.__setattr__(
                self, "media_resolution", GeminiResolution(self.media_resolution)
            )
            object.__setattr__(
                self, "processing_mode", GeminiProcessingMode(self.processing_mode)
            )
        except ValueError as exc:
            raise ConfigurationError(
                "Gemini model, media_resolution, or processing_mode is unsupported"
            ) from exc
        if self.thinking_level not in _THINKING_LEVELS[self.model]:
            allowed = ", ".join(sorted(_THINKING_LEVELS[self.model]))
            raise ConfigurationError(
                f"thinking_level is invalid for {self.model}; expected one of {allowed}"
            )
        if self.static_fps is not None:
            object.__setattr__(
                self,
                "static_fps",
                _number(self.static_fps, "static_fps", positive=True),
            )
        if self.agentic_threshold_seconds is not None:
            object.__setattr__(
                self,
                "agentic_threshold_seconds",
                _number(
                    self.agentic_threshold_seconds,
                    "agentic_threshold_seconds",
                    positive=True,
                ),
            )
        if (
            self.processing_mode is GeminiProcessingMode.STATIC
            and self.static_fps is None
        ):
            raise ConfigurationError("static_fps is required for static processing")
        if self.processing_mode is GeminiProcessingMode.AUTOMATIC:
            if self.static_fps is None or self.agentic_threshold_seconds is None:
                raise ConfigurationError(
                    "automatic processing requires static_fps and agentic_threshold_seconds"
                )
        if (
            self.processing_mode is GeminiProcessingMode.STATIC
            and self.agentic_threshold_seconds is not None
        ):
            raise ConfigurationError(
                "agentic_threshold_seconds must be explicitly None for static processing"
            )
        if self.processing_mode is GeminiProcessingMode.AGENTIC and (
            self.static_fps is not None or self.agentic_threshold_seconds is not None
        ):
            raise ConfigurationError(
                "static_fps and agentic_threshold_seconds must be explicitly None for agentic processing"
            )
        object.__setattr__(
            self,
            "request_timeout_seconds",
            _number(
                self.request_timeout_seconds, "request_timeout_seconds", positive=True
            ),
        )
        _integer(self.max_retries, "max_retries")
        object.__setattr__(
            self,
            "retry_backoff_seconds",
            _number(self.retry_backoff_seconds, "retry_backoff_seconds", positive=True),
        )
        _integer(
            self.file_upload_threshold_bytes, "file_upload_threshold_bytes", minimum=1
        )
        object.__setattr__(
            self,
            "file_poll_deadline_seconds",
            _number(
                self.file_poll_deadline_seconds,
                "file_poll_deadline_seconds",
                positive=True,
            ),
        )
        object.__setattr__(
            self,
            "file_poll_interval_seconds",
            _number(
                self.file_poll_interval_seconds,
                "file_poll_interval_seconds",
                positive=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class SupadataSettings:
    api_key: str = field(repr=False)
    request_timeout_seconds: float
    job_timeout_seconds: float
    poll_interval_seconds: float
    max_retries: int
    retry_delay_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ConfigurationError("Supadata api_key is required")
        object.__setattr__(
            self,
            "request_timeout_seconds",
            _number(
                self.request_timeout_seconds, "request_timeout_seconds", positive=True
            ),
        )
        object.__setattr__(
            self,
            "job_timeout_seconds",
            _number(self.job_timeout_seconds, "job_timeout_seconds", positive=True),
        )
        object.__setattr__(
            self,
            "poll_interval_seconds",
            _number(self.poll_interval_seconds, "poll_interval_seconds", positive=True),
        )
        _integer(self.max_retries, "max_retries")
        object.__setattr__(
            self,
            "retry_delay_seconds",
            _number(self.retry_delay_seconds, "retry_delay_seconds", positive=True),
        )


@dataclass(frozen=True, slots=True)
class MediaSettings:
    request_timeout_seconds: float
    cookie_file: Path | None = None
    output_directory: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_timeout_seconds",
            _number(
                self.request_timeout_seconds, "request_timeout_seconds", positive=True
            ),
        )
        if self.cookie_file is not None and not isinstance(self.cookie_file, Path):
            raise ConfigurationError("cookie_file must be a pathlib.Path or None")
        if self.output_directory is not None and not isinstance(
            self.output_directory, Path
        ):
            raise ConfigurationError("output_directory must be a pathlib.Path or None")


@dataclass(frozen=True, slots=True)
class TranscriptRequest:
    format: OutputFormat
    settings: SupadataSettings

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "format", OutputFormat(self.format))
        except ValueError as exc:
            raise ConfigurationError("transcript format is unsupported") from exc
        if self.format not in {
            OutputFormat.TRANSCRIPT_TEXT,
            OutputFormat.TRANSCRIPT_SEGMENTS,
        }:
            raise ConfigurationError(
                "transcript format must be transcript_text or transcript_segments"
            )


@dataclass(frozen=True, slots=True)
class MediaRequest:
    settings: MediaSettings
    selected_format_id: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.selected_format_id, str)
            or not self.selected_format_id.strip()
        ):
            raise ConfigurationError(
                "selected_format_id must be an explicit non-empty string"
            )


@dataclass(frozen=True, slots=True)
class VisualRequest:
    format: OutputFormat
    settings: GeminiSettings
    timestamp_mode: TimestampMode
    windows: tuple[TimeWindow, ...] = ()
    inspection_windows: tuple[TimeWindow, ...] = ()
    analyzed_start_seconds: float = 0
    analyzed_end_seconds: float | None = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "format", OutputFormat(self.format))
            object.__setattr__(
                self, "timestamp_mode", TimestampMode(self.timestamp_mode)
            )
        except ValueError as exc:
            raise ConfigurationError(
                "visual format or timestamp_mode is unsupported"
            ) from exc
        if self.format not in {OutputFormat.VIDEO_TEXT, OutputFormat.VIDEO_EVENTS}:
            raise ConfigurationError("visual format must be video_text or video_events")
        if self.timestamp_mode is TimestampMode.WINDOWS and not self.windows:
            raise ConfigurationError(
                "windowed visual output requires caller-defined windows"
            )
        if self.timestamp_mode is not TimestampMode.WINDOWS and self.windows:
            raise ConfigurationError("windows are valid only for windowed video events")
        start = _number(self.analyzed_start_seconds, "analyzed_start_seconds")
        if start < 0:
            raise ConfigurationError("analyzed_start_seconds must be at least 0")
        end = (
            None
            if self.analyzed_end_seconds is None
            else _number(self.analyzed_end_seconds, "analyzed_end_seconds")
        )
        if end is not None and end < start:
            raise ConfigurationError(
                "analyzed_end_seconds cannot precede analyzed_start_seconds"
            )
        if not all(isinstance(window, TimeWindow) for window in self.windows):
            raise ConfigurationError("windows must contain TimeWindow objects")
        if any(
            window.start_seconds < start
            or (end is not None and window.end_seconds > end)
            for window in self.windows
        ):
            raise ConfigurationError("windows must lie inside the analyzed interval")
        if not all(
            isinstance(window, TimeWindow) for window in self.inspection_windows
        ):
            raise ConfigurationError(
                "inspection_windows must contain TimeWindow objects"
            )
        if any(
            window.start_seconds < start
            or (end is not None and window.end_seconds > end)
            for window in self.inspection_windows
        ):
            raise ConfigurationError(
                "inspection_windows must lie inside the analyzed interval"
            )
        object.__setattr__(self, "analyzed_start_seconds", start)
        object.__setattr__(self, "analyzed_end_seconds", end)


@dataclass(frozen=True, slots=True)
class PipelineRequest:
    metadata: bool = False
    transcript: TranscriptRequest | None = None
    visual: VisualRequest | None = None
    media: MediaRequest | None = None
    visual_media: MediaRequest | None = None
    include_transcript_context: bool = False

    def __post_init__(self) -> None:
        if not any(
            (
                self.metadata,
                self.transcript is not None,
                self.visual is not None,
                self.media is not None,
            )
        ):
            raise ConfigurationError("pipeline requests at least one output")
        if self.include_transcript_context and (
            self.transcript is None or self.visual is None
        ):
            raise ConfigurationError(
                "transcript context requires both transcript and visual requests"
            )
        if self.visual is not None and self.visual_media is None and self.media is None:
            raise ConfigurationError(
                "pipeline visual requests require explicit visual_media or media settings"
            )
        if self.visual_media is not None and self.visual is None:
            raise ConfigurationError("visual_media is valid only with a visual request")
        if (
            self.visual is not None
            and self.visual_media is not None
            and self.media is not None
            and self.visual_media != self.media
        ):
            raise ConfigurationError(
                "visual_media and media requests must use the same media configuration"
            )


@dataclass(frozen=True, slots=True)
class EnvironmentSettings:
    gemini: GeminiSettings | None
    supadata: SupadataSettings | None


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if value is None or not value.strip():
        raise ConfigurationError(f"missing required environment variable {name}")
    return value


def _enum(values: Mapping[str, str], name: str, enum_type: type[StrEnum]) -> StrEnum:
    try:
        return enum_type(_required(values, name))
    except ValueError as exc:
        choices = ", ".join(member.value for member in enum_type)
        raise ConfigurationError(f"{name} must be one of {choices}") from exc


def _env_number(values: Mapping[str, str], name: str) -> float:
    raw = _required(values, name)
    try:
        return _number(float(raw), name, positive=True)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a finite positive number") from exc


def _env_int(values: Mapping[str, str], name: str) -> int:
    raw = _required(values, name)
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer at least 0") from exc
    return _integer(parsed, name)


def load_environment(
    *,
    include_gemini: bool = False,
    include_supadata: bool = False,
    environ: Mapping[str, str] | None = None,
) -> EnvironmentSettings:
    """Build provider settings from explicit environment variables without dotenv I/O."""
    values = os.environ if environ is None else environ
    gemini: GeminiSettings | None = None
    supadata: SupadataSettings | None = None
    if include_gemini:
        api_key = _required(values, "GEMINI_API_KEY")
        model = _enum(values, "VCP_GEMINI_MODEL", GeminiModel)
        processing = _enum(values, "VCP_GEMINI_PROCESSING_MODE", GeminiProcessingMode)
        static_fps = (
            None
            if processing is GeminiProcessingMode.AGENTIC
            else _env_number(values, "VCP_GEMINI_STATIC_FPS")
        )
        threshold = (
            _env_number(values, "VCP_GEMINI_AGENTIC_THRESHOLD_SECONDS")
            if processing is GeminiProcessingMode.AUTOMATIC
            else None
        )
        gemini = GeminiSettings(
            api_key=api_key,
            model=model,  # type: ignore[arg-type]
            media_resolution=_enum(
                values, "VCP_GEMINI_MEDIA_RESOLUTION", GeminiResolution
            ),  # type: ignore[arg-type]
            thinking_level=_required(values, "VCP_GEMINI_THINKING_LEVEL"),
            processing_mode=processing,  # type: ignore[arg-type]
            static_fps=static_fps,
            agentic_threshold_seconds=threshold,
            request_timeout_seconds=_env_number(
                values, "VCP_GEMINI_REQUEST_TIMEOUT_SECONDS"
            ),
            max_retries=_env_int(values, "VCP_GEMINI_MAX_RETRIES"),
            retry_backoff_seconds=_env_number(
                values, "VCP_GEMINI_RETRY_BACKOFF_SECONDS"
            ),
            file_upload_threshold_bytes=_env_int(
                values, "VCP_GEMINI_FILE_UPLOAD_THRESHOLD_BYTES"
            ),
            file_poll_deadline_seconds=_env_number(
                values, "VCP_GEMINI_FILE_POLL_DEADLINE_SECONDS"
            ),
            file_poll_interval_seconds=_env_number(
                values, "VCP_GEMINI_FILE_POLL_INTERVAL_SECONDS"
            ),
        )
    if include_supadata:
        api_key = _required(values, "SUPADATA_API_KEY")
        supadata = SupadataSettings(
            api_key=api_key,
            request_timeout_seconds=_env_number(
                values, "VCP_SUPADATA_REQUEST_TIMEOUT_SECONDS"
            ),
            job_timeout_seconds=_env_number(values, "VCP_SUPADATA_JOB_TIMEOUT_SECONDS"),
            poll_interval_seconds=_env_number(
                values, "VCP_SUPADATA_POLL_INTERVAL_SECONDS"
            ),
            max_retries=_env_int(values, "VCP_SUPADATA_MAX_RETRIES"),
            retry_delay_seconds=_env_number(values, "VCP_SUPADATA_RETRY_DELAY_SECONDS"),
        )
    return EnvironmentSettings(gemini=gemini, supadata=supadata)
