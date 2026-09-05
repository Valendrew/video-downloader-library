# Gemini

Gemini analyzes visible content in a local video. The adapter returns structured events
or readable prose derived from those events. It describes what is visible; optional
transcript context is separate reference material.

## Install

```bash
uv sync --locked --extra gemini
```

This command is for the library checkout. See [installation](../install.md) for using
an editable checkout in another application.

## Configure

```python
import os
from video_context_pipeline import GeminiSettings

settings = GeminiSettings(
    api_key=os.environ["GEMINI_API_KEY"],
    model="gemini-3.5-flash-lite",
    media_resolution="medium",
    thinking_level="medium",
    processing_mode="static",
    static_fps=1.0,
    agentic_threshold_seconds=None,
    request_timeout_seconds=60.0,
    max_retries=2,
    retry_backoff_seconds=1.0,
    file_upload_threshold_bytes=20_000_000,
    file_poll_deadline_seconds=300.0,
    file_poll_interval_seconds=2.0,
)
```

These are example choices, not defaults. Every constructor field is required, including
explicit `None` for mode-inapplicable values. You can also use the
[Gemini environment loader](../configuration.md#gemini-environment).

### Models and thinking

| Model accepted by the library | Thinking levels |
| --- | --- |
| `gemini-3.5-flash-lite` | `minimal`, `low`, `medium`, `high` |
| `gemini-3.8-flash` | `low`, `medium`, `high` |

Resolution accepts `low`, `medium`, or `high`. It is separate from download quality:
changing resolution does not select a different source file.

### Processing modes

| Mode | `static_fps` | `agentic_threshold_seconds` | Behavior |
| --- | --- | --- | --- |
| `static` | Positive number | `None` | Sends the requested FPS; supports a bounded interval. |
| `agentic` | `None` | `None` | Uses agentic processing for the full video. |
| `automatic` | Positive number | Positive seconds | Chooses agentic at or above the threshold, otherwise static. |

Automatic mode requires known media duration. Agentic processing cannot analyze a
partial interval. Accepted FPS does not establish an exact internal frame schedule;
[output timestamps](../schemas.md#timestamp-modes) are model estimates or caller-defined windows.

### Request and file limits

The HTTP timeout and retry fields control individual requests. The upload threshold
controls inline input versus the Files API; file polling has its own interval and
deadline. Remote uploaded files are cleaned up after use. No output-token cap,
stop sequence, or event-count cap is exposed by this library.

## Construct the provider

```python
from video_context_pipeline.providers.gemini import GeminiProvider

provider = GeminiProvider()
```

Optional `client` and `logger` keyword arguments support HTTP client injection and
application logging. Follow [visual understanding](../components/visual.md) for the
artifact and request, or use the [pipeline](../components/pipeline.md) with a URL.

## Explore the original documentation

- [Video understanding](https://ai.google.dev/gemini-api/docs/video-understanding): Google's video input and processing guide.
- [Interactions API](https://ai.google.dev/api/interactions-api): the endpoint used by this adapter.
- [Files API](https://ai.google.dev/gemini-api/docs/files): uploaded media lifecycle.
- [Interactions OpenAPI schema](https://ai.google.dev/static/api/interactions.openapi.json): wire-level field definitions.

Read [this project's validation record](../provider-validation.md#gemini) for observed
results and limits, including combinations affected by quota or demand failures.
