# Schemas and requests

All provider results are `ProviderOutput(format, data, provider, status, language=None,
usage=None)`. `status` is `content` for non-empty data and `empty` for empty data.
`usage`, when present, is factual provider-reported data.

## Transcript

`TranscriptRequest(format, settings)` accepts `transcript_text` or
`transcript_segments`. Text is readable, formatted transcript prose. Segments are
`TranscriptSegment(start_seconds, end_seconds, text)`: start is non-negative, end may
be `None` or be at least the start, and text is non-empty. Segment time values come
from the provider's transcript timing; formatting text is derived from those segments.

## Visual output

`VisualRequest(format, settings, timestamp_mode, windows=(), inspection_windows=(),
analyzed_start_seconds=0, analyzed_end_seconds=None)` accepts `video_text` or
`video_events`.

`video_text` is readable prose formatted from returned visual events. Event output
uses `VideoEvent(description, timestamp_seconds=None, window=None)`. An event has a
non-empty description and either one timestamp, one window, or neither.

`timestamp_mode` controls the event schema:

| Mode | Result | Time provenance |
| --- | --- | --- |
| `none` | Events have no time fields. | No time claim. |
| `approximate` | Each event has `timestamp_seconds`. | A model-produced approximation on the original video timeline; it is not deterministic frame timing. |
| `windows` | Each event has one supplied `TimeWindow`. | A deterministic caller-defined interval, assigned by the model. |

`windows` is required only for `windows` mode and defines output labels.
`inspection_windows` only directs which intervals to inspect; it does not alter event
schema. Both must lie within the finite requested analysis interval. Timed output also
needs a known media duration or explicit `analyzed_end_seconds`.

## Media and pipeline

`MediaRequest(settings, selected_format_id)` always needs an explicit yt-dlp format
identifier. `MediaArtifact(path, media_type, duration_seconds=None, owned=False, ... )`
represents a local artifact and records ownership for cleanup.

`PipelineRequest(metadata=False, transcript=None, visual=None, media=None,
visual_media=None, include_transcript_context=False)` requests outputs by name.
`visual_media` supplies the explicit internal download setting for a visual request
when `media` is not requested. `include_transcript_context=True` requires both a
transcript and visual request. `PipelineResult.outputs` contains only `metadata`,
`transcript`, `visual`, and/or explicitly requested `media` output names.

