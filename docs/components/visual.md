# Understand visible content

Use Gemini to describe visible actions, objects, and text in a local video. Choose
readable prose or structured events, with no timing, approximate timestamps, or your
own time-window labels.

## Before you start

Install the `gemini` extra and create settings from
[the Gemini guide](../providers/gemini.md#configure). The following function accepts
those settings and an existing local video. Use static mode for this bounded example,
and supply a clip at least 60 seconds long.

## Analyze an interval

```python
from pathlib import Path
from video_context_pipeline import GeminiSettings, MediaArtifact, VisualRequest
from video_context_pipeline.providers.gemini import GeminiProvider

async def describe(path: Path, settings: GeminiSettings) -> None:
    artifact = MediaArtifact(path=path, media_type="video/mp4", owned=False)
    request = VisualRequest(
        format="video_events",
        settings=settings,
        timestamp_mode="approximate",
        analyzed_start_seconds=0,
        analyzed_end_seconds=60,
    )
    result = await GeminiProvider().understand(
        artifact,
        request,
        transcript_context=None,
    )
    for event in result.data:
        print(event.timestamp_seconds, event.description)
```

The file stays caller-owned. The method makes real provider requests when awaited.
For an arbitrary video length, provide its measured duration or choose a valid explicit
analysis end. [Local media tools](media-tools.md) can measure the file.

## Choose the output

| Need | Request choice |
| --- | --- |
| Readable description | `format="video_text"` |
| Events for application processing | `format="video_events"` |
| Observations without time claims | `timestamp_mode="none"` |
| Approximate positions in the source | `timestamp_mode="approximate"` |
| Events grouped into your intervals | `timestamp_mode="windows"` and explicit `windows` |

Both output formats come from the same event response. See
[timestamp modes and window examples](../schemas.md#timestamp-modes) for their exact meaning.
`inspection_windows` directs attention to intervals without changing the event schema.

## Choose processing separately

Static processing sends your FPS and supports partial intervals. Agentic processing
requires the full video. Automatic processing needs a known duration and chooses the
mode at your configured threshold. See [processing modes](../providers/gemini.md#processing-modes).

Resolution and download quality are separate settings. The library does not increase
either automatically. Accepted FPS is not evidence of an exact frame schedule, so do
not calculate event timestamps from frame positions.

## Add transcript context or start from a URL

The optional `transcript_context` argument accepts text as independent reference data.
The adapter instructs Gemini to describe visible observations only. For a public URL,
use [the pipeline](pipeline.md) with explicit download settings; Gemini itself does
not download source URLs.

[Gemini provider details and upstream docs →](../providers/gemini.md)
