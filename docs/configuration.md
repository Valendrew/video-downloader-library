# Configuration

Every request supplies a settings object. `load_environment()` is an optional helper
that converts an explicit environment mapping into Gemini and Supadata settings. It
does not read `.env` files or perform network I/O. Your application decides whether
to pass `os.environ`, another mapping, or settings built directly in Python.

## Environment loader

`load_environment(include_gemini=True, include_supadata=True, environ=...)` returns
only the requested provider settings. All listed values are required when that
provider is included, except the mode-dependent Gemini values described below.

| Variable | Meaning |
| --- | --- |
| `GEMINI_API_KEY` | Gemini API key. |
| `VCP_GEMINI_MODEL` | `gemini-3.8-flash` or `gemini-3.5-flash-lite`. |
| `VCP_GEMINI_MEDIA_RESOLUTION` | `low`, `medium`, or `high`. |
| `VCP_GEMINI_THINKING_LEVEL` | For 3.8: `low`, `medium`, or `high`; for Flash Lite: `minimal`, `low`, `medium`, or `high`. |
| `VCP_GEMINI_PROCESSING_MODE` | `static`, `agentic`, or `automatic`. |
| `VCP_GEMINI_STATIC_FPS` | Positive FPS. Required by `static` and `automatic`; not used by `agentic`. |
| `VCP_GEMINI_AGENTIC_THRESHOLD_SECONDS` | Positive duration threshold. Required only by `automatic`; it chooses agentic processing at or above this duration. |
| `VCP_GEMINI_REQUEST_TIMEOUT_SECONDS` | Positive timeout for each Gemini HTTP request. |
| `VCP_GEMINI_MAX_RETRIES` | Non-negative retry count. |
| `VCP_GEMINI_RETRY_BACKOFF_SECONDS` | Positive retry delay. |
| `VCP_GEMINI_FILE_UPLOAD_THRESHOLD_BYTES` | Positive request-size threshold for inline versus Files API upload. |
| `VCP_GEMINI_FILE_POLL_DEADLINE_SECONDS` | Positive deadline while waiting for an uploaded file. |
| `VCP_GEMINI_FILE_POLL_INTERVAL_SECONDS` | Positive interval between uploaded-file polls. |
| `SUPADATA_API_KEY` | Supadata API key. |
| `VCP_SUPADATA_REQUEST_TIMEOUT_SECONDS` | Positive timeout for a Supadata HTTP request. |
| `VCP_SUPADATA_JOB_TIMEOUT_SECONDS` | Positive total wait for a queued transcript job. |
| `VCP_SUPADATA_POLL_INTERVAL_SECONDS` | Positive interval between queued-job polls. |
| `VCP_SUPADATA_MAX_RETRIES` | Non-negative retry count. |
| `VCP_SUPADATA_RETRY_DELAY_SECONDS` | Positive retry delay. |

`MediaSettings` is Python configuration, not an environment-loader setting:
`MediaSettings(request_timeout_seconds=..., cookie_file=Path(...) | None,
output_directory=Path(...) | None)`. The timeout is required and positive; cookie and
output locations are explicit caller choices.

## Direct Python settings

The following construction makes every operational choice visible. It does not call
a provider:

```python
from video_context_pipeline import GeminiSettings, MediaSettings, SupadataSettings

gemini = GeminiSettings(
    api_key="kept outside source control", model="gemini-3.5-flash-lite",
    media_resolution="medium", thinking_level="medium", processing_mode="automatic",
    static_fps=1.0, agentic_threshold_seconds=120.0, request_timeout_seconds=60.0,
    max_retries=2, retry_backoff_seconds=1.0, file_upload_threshold_bytes=20_000_000,
    file_poll_deadline_seconds=300.0, file_poll_interval_seconds=2.0,
)
supadata = SupadataSettings(
    api_key="kept outside source control", request_timeout_seconds=30.0,
    job_timeout_seconds=120.0, poll_interval_seconds=2.0, max_retries=2,
    retry_delay_seconds=1.0,
)
media = MediaSettings(request_timeout_seconds=60.0, cookie_file=None, output_directory=None)
```

`GeminiSettings` has one valid shape per mode: `static` needs `static_fps` and an
explicit `None` threshold; `agentic` needs explicit `None` for both FPS and threshold;
`automatic` needs both. Provider timeouts and retries can still fail an operation;
there is no output size, stop-sequence, or event-count setting in this library.

The repository-root `.env.example` contains the same loader fields with placeholders.
Keep real keys outside the repository.
