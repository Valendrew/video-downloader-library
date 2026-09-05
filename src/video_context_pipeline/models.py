"""Provider-neutral public values returned by the library."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from pathlib import Path
from typing import Any, Generic, TypeVar

from .errors import ValidationError


class OutputFormat(StrEnum):
    METADATA = "metadata"
    TRANSCRIPT_TEXT = "transcript_text"
    TRANSCRIPT_SEGMENTS = "transcript_segments"
    VIDEO_TEXT = "video_text"
    VIDEO_EVENTS = "video_events"
    MEDIA = "media"


class OutputStatus(StrEnum):
    CONTENT = "content"
    EMPTY = "empty"


class TimestampMode(StrEnum):
    NONE = "none"
    APPROXIMATE = "approximate"
    WINDOWS = "windows"


def _finite_number(value: object, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} must be a finite number")
    number = float(value)
    if not isfinite(number) or (minimum is not None and number < minimum):
        raise ValidationError(
            f"{name} must be a finite number"
            + (f" at least {minimum}" if minimum is not None else "")
        )
    return number


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    start_seconds: float
    end_seconds: float | None
    text: str

    def __post_init__(self) -> None:
        start = _finite_number(self.start_seconds, "start_seconds", minimum=0)
        object.__setattr__(self, "start_seconds", start)
        if self.end_seconds is not None:
            end = _finite_number(self.end_seconds, "end_seconds", minimum=0)
            if end < start:
                raise ValidationError("end_seconds cannot precede start_seconds")
            object.__setattr__(self, "end_seconds", end)
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValidationError("transcript segment text must be non-empty")


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start_seconds: float
    end_seconds: float

    def __post_init__(self) -> None:
        start = _finite_number(self.start_seconds, "window start_seconds", minimum=0)
        end = _finite_number(self.end_seconds, "window end_seconds", minimum=0)
        if end <= start:
            raise ValidationError("time-window end_seconds must follow start_seconds")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)


@dataclass(frozen=True, slots=True)
class VideoEvent:
    description: str
    timestamp_seconds: float | None = None
    window: TimeWindow | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValidationError("video event description must be non-empty")
        if self.timestamp_seconds is not None and self.window is not None:
            raise ValidationError(
                "a video event cannot have both a timestamp and a window"
            )
        if self.timestamp_seconds is not None:
            object.__setattr__(
                self,
                "timestamp_seconds",
                _finite_number(self.timestamp_seconds, "timestamp_seconds", minimum=0),
            )


@dataclass(frozen=True, slots=True)
class MediaArtifact:
    """A local file with explicit, ownership-aware cleanup."""

    path: Path
    media_type: str
    duration_seconds: float | None = None
    owned: bool = False
    dependencies: tuple["MediaArtifact", ...] = ()
    owned_directory: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ValidationError("media path must be a pathlib.Path")
        if not isinstance(self.media_type, str) or not self.media_type.strip():
            raise ValidationError("media_type must be a non-empty string")
        if self.duration_seconds is not None:
            object.__setattr__(
                self,
                "duration_seconds",
                _finite_number(self.duration_seconds, "duration_seconds", minimum=0),
            )
        if self.owned_directory is not None:
            if not self.owned or not isinstance(self.owned_directory, Path):
                raise ValidationError(
                    "owned_directory requires an owned pathlib.Path artifact"
                )
            try:
                self.path.resolve().relative_to(self.owned_directory.resolve())
            except ValueError as exc:
                raise ValidationError(
                    "owned_directory must contain the owned media path"
                ) from exc
            if self.path.resolve() == self.owned_directory.resolve():
                raise ValidationError(
                    "owned_directory must name a directory containing, not equal to, the media path"
                )

    def cleanup(self) -> None:
        """Remove owned files and empty owned temporary directories, preserving caller paths."""
        for dependency in self.dependencies:
            dependency.cleanup()
        if self.owned:
            self.path.unlink(missing_ok=True)
        if self.owned_directory is not None:
            try:
                self.owned_directory.rmdir()
            except FileNotFoundError:
                pass

    def __enter__(self) -> "MediaArtifact":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.cleanup()


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ProviderOutput(Generic[T]):
    """A named result with a caller-selected public representation."""

    format: OutputFormat
    data: T
    provider: str
    status: OutputStatus
    language: str | None = None
    usage: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "format", OutputFormat(self.format))
            object.__setattr__(self, "status", OutputStatus(self.status))
        except (TypeError, ValueError) as exc:
            raise ValidationError("output format or success status is invalid") from exc
        empty = isinstance(self.data, (str, tuple, list, dict)) and len(self.data) == 0
        if (self.status is OutputStatus.EMPTY) != empty:
            raise ValidationError("output status must match whether its data is empty")
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValidationError("provider must be a non-empty string")
        if self.language is not None and (
            not isinstance(self.language, str) or not self.language.strip()
        ):
            raise ValidationError("language must be a non-empty string or None")
        if self.usage is not None and not isinstance(self.usage, Mapping):
            raise ValidationError(
                "usage must be provider-reported mapping data or None"
            )


@dataclass(frozen=True, slots=True)
class PipelineResult:
    outputs: Mapping[str, ProviderOutput[Any]] = field(default_factory=dict)

    def output(self, name: str) -> ProviderOutput[Any]:
        try:
            return self.outputs[name]
        except KeyError as exc:
            raise ValidationError(f"pipeline did not request output {name!r}") from exc

    def cleanup(self) -> None:
        """Release owned media returned to the caller; caller-owned files remain intact."""
        for output in self.outputs.values():
            if output.format is OutputFormat.MEDIA and isinstance(
                output.data, MediaArtifact
            ):
                output.data.cleanup()

    def __enter__(self) -> "PipelineResult":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.cleanup()


def validate_video_events(
    events: Sequence[VideoEvent],
    mode: TimestampMode,
    *,
    analyzed_start_seconds: float = 0,
    analyzed_end_seconds: float | None = None,
    windows: Sequence[TimeWindow] = (),
) -> tuple[VideoEvent, ...]:
    """Reject events whose timestamp representation violates the requested policy."""
    start = _finite_number(analyzed_start_seconds, "analyzed_start_seconds", minimum=0)
    end = (
        None
        if analyzed_end_seconds is None
        else _finite_number(analyzed_end_seconds, "analyzed_end_seconds", minimum=start)
    )
    expected_windows = set(windows)
    checked: list[VideoEvent] = []
    for event in events:
        if not isinstance(event, VideoEvent):
            raise ValidationError("video events must be VideoEvent objects")
        if mode is TimestampMode.NONE and (
            event.timestamp_seconds is not None or event.window is not None
        ):
            raise ValidationError("untimed events cannot include timestamps")
        if mode is TimestampMode.APPROXIMATE and (
            event.timestamp_seconds is None or event.window is not None
        ):
            raise ValidationError("approximate events require exactly one timestamp")
        if mode is TimestampMode.WINDOWS and (
            event.window is None or event.timestamp_seconds is not None
        ):
            raise ValidationError(
                "windowed events require exactly one caller-defined window"
            )
        if event.timestamp_seconds is not None and (
            event.timestamp_seconds < start
            or (end is not None and event.timestamp_seconds > end)
        ):
            raise ValidationError("event timestamp lies outside the analyzed interval")
        if event.window is not None:
            if event.window.start_seconds < start or (
                end is not None and event.window.end_seconds > end
            ):
                raise ValidationError("event window lies outside the analyzed interval")
            if expected_windows and event.window not in expected_windows:
                raise ValidationError("event window was not supplied by the caller")
        checked.append(event)
    return tuple(checked)
