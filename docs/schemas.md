# Schemas and requests

Requests describe the output you want. Settings describe how to run the service.
Results wrap the returned data with its format, provider, and success status.
The types on this page are exported from `video_context_pipeline` unless stated otherwise.

## Output formats at a glance

| Request | `format` | Type of `ProviderOutput.data` |
| --- | --- | --- |
| Metadata inspection | `metadata` | Mapping with title, description, duration, and formats |
| `TranscriptRequest` | `transcript_text` | `str` |
| `TranscriptRequest` | `transcript_segments` | `tuple[TranscriptSegment, ...]` |
| `VisualRequest` | `video_text` | `str` |
| `VisualRequest` | `video_events` | `tuple[VideoEvent, ...]` |
| `MediaRequest` | `media` (set by the provider) | `MediaArtifact` |

Formats and modes accept the documented string values or their corresponding
`OutputFormat` and `TimestampMode` enum members. Public text is formatted for readers;
model input formatting is handled separately by the adapter.

## ProviderOutput

Every provider returns this wrapper. Applications normally read it rather than construct it.

```text title="Constructor reference"
ProviderOutput(
    format: OutputFormat,
    data: T,
    provider: str,
    status: OutputStatus,
    language: str | None = None,
    usage: Mapping[str, Any] | None = None,
)
```

| Field | Meaning |
| --- | --- |
| `format` | The representation of `data`, from the table above. |
| `data` | Text, typed records, a metadata mapping, or a media artifact. |
| `provider` | Non-empty provider identifier. |
| `status` | `content` for content, or `empty` for an empty string or collection. |
| `language` | Provider-reported language when available. |
| `usage` | Provider-reported usage mapping when available; no inferred cost. |

An empty response is a successful result. Failed operations raise exceptions and do
not return an error status in this wrapper.

## TranscriptRequest

Select readable text or structured segments. See [Supadata setup](providers/supadata.md)
for the settings object and [transcription](components/transcription.md) for the call.

```text title="Constructor reference"
TranscriptRequest(
    format: OutputFormat,
    settings: SupadataSettings,
)
```

Both fields are required. `format` must be `transcript_text` or `transcript_segments`.

### TranscriptSegment

```text title="Constructor reference"
TranscriptSegment(
    start_seconds: float,
    end_seconds: float | None,
    text: str,
)
```

| Field | Rules |
| --- | --- |
| `start_seconds` | Finite and non-negative. |
| `end_seconds` | `None` when unavailable; otherwise finite and at least the start. |
| `text` | Non-empty speech text. |

The adapter converts provider timing into seconds. Text output is formatted from
these same segments. For example, a segment can represent speech from 2.5 to 4 seconds:

```python
from video_context_pipeline import TranscriptSegment

segment = TranscriptSegment(start_seconds=2.5, end_seconds=4.0, text="Welcome back.")
```

## VisualRequest

Select the representation, timing policy, and interval for a local video analysis.

```text title="Constructor reference"
VisualRequest(
    format: OutputFormat,
    settings: GeminiSettings,
    timestamp_mode: TimestampMode,
    windows: tuple[TimeWindow, ...] = (),
    inspection_windows: tuple[TimeWindow, ...] = (),
    analyzed_start_seconds: float = 0,
    analyzed_end_seconds: float | None = None,
)
```

| Field | Purpose |
| --- | --- |
| `format` | Required: `video_text` or `video_events`. Both come from the same event response. |
| `settings` | Required Gemini settings, including processing mode. |
| `timestamp_mode` | Required: `none`, `approximate`, or `windows`. |
| `windows` | Caller-defined labels for `windows` mode; leave empty for other modes. |
| `inspection_windows` | Intervals to focus on, independent of how events are timestamped. |
| `analyzed_start_seconds` | Non-negative start on the original video timeline. |
| `analyzed_end_seconds` | End on the original timeline; `None` uses known media duration when available. |

### Timestamp modes

| Mode | Event fields | What the time means |
| --- | --- | --- |
| `none` | Description only | No time claim. |
| `approximate` | Description and `timestamp_seconds` | Model-produced estimate on the original video timeline. |
| `windows` | Description and a supplied `window` | Caller-defined interval, assigned to the event by the model. |

Timed output requires a finite analysis end, supplied explicitly or resolved from
known media duration. Windows must lie inside the analysis interval.
An approximate timestamp is not a measured frame time. A window's boundaries are
fixed by you, but assigning an observation to a window is still model work.

### TimeWindow and VideoEvent

```text title="Constructor reference"
TimeWindow(
    start_seconds: float,
    end_seconds: float,
)

VideoEvent(
    description: str,
    timestamp_seconds: float | None = None,
    window: TimeWindow | None = None,
)
```

A window has a finite non-negative start and a strictly later finite end.
An event has a non-empty description and either a timestamp, a window, or neither;
it cannot have both a timestamp and a window.

### Label events with your own intervals

Given `gemini_settings` configured for static processing and a video at least ten
seconds long:

```python
from video_context_pipeline import TimeWindow, VisualRequest

request = VisualRequest(
    format="video_events",
    settings=gemini_settings,
    timestamp_mode="windows",
    windows=(TimeWindow(0, 5), TimeWindow(5, 10)),
    analyzed_start_seconds=0,
    analyzed_end_seconds=10,
)
```

Here `windows` determines the allowed output labels. To direct attention to an interval
without using window labels, use `inspection_windows` with another timestamp mode.
For processing-mode restrictions and a complete call, see
[visual understanding](components/visual.md).

## MediaRequest

Select a download format using an ID from the source's inspection result.

```text title="Constructor reference"
MediaRequest(
    settings: MediaSettings,
    selected_format_id: str,
)
```

Both fields are required. The format ID must be non-empty; it is not a universal
quality preset. Inspect the source and choose a suitable format as shown in
[downloads](components/downloads.md).

## MediaArtifact

An artifact describes a local file and who is responsible for removing it.

```text title="Constructor reference"
MediaArtifact(
    path: Path,
    media_type: str,
    duration_seconds: float | None = None,
    owned: bool = False,
    dependencies: tuple[MediaArtifact, ...] = (),
    owned_directory: Path | None = None,
)
```

| Field | Meaning |
| --- | --- |
| `path` | Required `pathlib.Path` to the file. |
| `media_type` | Required non-empty media type, such as `video/mp4` or `audio/mpeg`. |
| `duration_seconds` | Finite non-negative duration when known. |
| `owned` | Whether cleanup may remove this file. Defaults to `False`. |
| `dependencies` | Artifacts whose cleanup is also called. Each retains its own ownership rules. |
| `owned_directory` | Optional owned directory containing the artifact; cleanup removes it when empty. |

For a file supplied by your application:

```python
from pathlib import Path
from video_context_pipeline import MediaArtifact

artifact = MediaArtifact(path=Path("clip.mp4"), media_type="video/mp4", owned=False)
```

`cleanup()` preserves this caller-owned file. Downloader outputs are owned by the
library. Use their artifact as a synchronous context manager to release them after use:

```python
# download is the ProviderOutput returned by await provider.download(...).
with download.data as artifact:
    print(artifact.path)
```

## PipelineRequest

Select at least one output. Unselected stages do not need provider configuration.

```text title="Constructor reference"
PipelineRequest(
    metadata: bool = False,
    transcript: TranscriptRequest | None = None,
    visual: VisualRequest | None = None,
    media: MediaRequest | None = None,
    visual_media: MediaRequest | None = None,
    include_transcript_context: bool = False,
)
```

| Field | What it requests |
| --- | --- |
| `metadata` | A metadata output from the metadata provider. |
| `transcript` | A transcript output in the requested format. |
| `visual` | A visual output from downloaded video. |
| `media` | A downloaded artifact returned to the caller. |
| `visual_media` | A download for visual processing, cleaned up internally when `media` is absent. |
| `include_transcript_context` | Supplies the requested transcript as independent context to the visual provider. |

A visual request needs either `media` or `visual_media` to define its download. If both
are supplied, they must be equal. `visual_media` requires `visual`, and transcript
context requires both `transcript` and `visual`.

## PipelineResult

```text title="Constructor reference"
PipelineResult(outputs: Mapping[str, ProviderOutput[Any]] = <empty mapping>)
```

`outputs` contains only requested names: `metadata`, `transcript`, `visual`, and/or
`media`. The name is the stage; the output's `format` is its representation. For example,
`result.output("transcript").format` may be `transcript_segments`.

`result.output(name)` returns that stage's output and raises `ValidationError` for an
unrequested name. `result.cleanup()` releases returned owned media. The result also
supports a synchronous context manager:

```python
with await pipeline.run(url, request) as result:
    transcript = result.output("transcript")
    print(transcript.data)
```

See [the pipeline guide](components/pipeline.md) for provider wiring and
[errors and logging](errors-and-logging.md) for failure and cancellation behavior.
