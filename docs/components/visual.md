# Visual understanding

`GeminiProvider(client=None, logger=None)` analyzes a local `MediaArtifact` with a
`VisualRequest`; it never downloads a URL itself. Use [Pipeline](pipeline.md) for a
public URL plus an explicit internal or returned download request.

```python
result = await provider.understand(
    artifact,
    VisualRequest(
        format="video_events",
        settings=gemini_settings,
        timestamp_mode="approximate",
        analyzed_start_seconds=0,
        analyzed_end_seconds=60,
    ),
    transcript_context=None,
)
```

`video_events` returns canonical `VideoEvent` values. `video_text` returns readable
event text formatted from the same visual-event response. Choose timing and optional
windows explicitly as described in [schemas](../schemas.md). Approximate timestamps
are model observations, while caller-supplied windows are deterministic labels.

Static Gemini processing sends the explicit FPS and can analyze a bounded interval.
Agentic processing cannot analyze a partial interval. Automatic processing needs known
media duration and chooses agentic at the configured threshold; otherwise it uses
static FPS. The full model, resolution, thinking, upload, timeout, retry, and polling
settings are required by `GeminiSettings` and listed in [configuration](../configuration.md).

Choose resolution for the visual task: low suits general actions, medium uses the same
documented video allocation, and high is for small text. Download quality is an
independent caller choice; resolution does not alter it, and the library does not
escalate either setting automatically. An accepted FPS value is an API acceptance
observation, not a measured sampling schedule. Never derive an event time from frame
position or FPS; use only the model's approximate timestamp or a caller-defined window.

An optional transcript context is independent reference data. Gemini is instructed to
describe only visible observations and not describe audio or transcription. The request
contains no output-token cap, stop sequence, or event-count cap.
