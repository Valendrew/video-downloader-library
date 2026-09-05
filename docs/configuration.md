# Configuration

Configure only the services you use. Settings control credentials and operational
choices; requests control which output to produce. Invalid or missing applicable
settings raise `ConfigurationError` instead of selecting replacement values.

## Choose how to supply settings

You can build `GeminiSettings`, `SupadataSettings`, and `MediaSettings` directly in
Python, or load the HTTP provider settings from environment variables.

```python
from video_context_pipeline import load_environment

settings = load_environment(include_supadata=True)
assert settings.supadata is not None
# settings.gemini is None: Gemini variables are not required or read.
```

### Environment loader interface

```text title="Function reference"
load_environment(
    *,
    include_gemini: bool = False,
    include_supadata: bool = False,
    environ: Mapping[str, str] | None = None,
) -> EnvironmentSettings
```

| Argument | Behavior |
| --- | --- |
| `include_gemini` | Load and validate Gemini fields when `True`. |
| `include_supadata` | Load and validate Supadata fields when `True`. |
| `environ` | Read this mapping, or `os.environ` when omitted or `None`. |

Both flags default to `False`. The returned object's `gemini` and `supadata` fields
are settings objects for selected services and `None` for the others. Set both flags
to load both services.

The loader does not open `.env` files or contact providers. Your application decides
how to populate the environment. The repository's `.env.example` lists the variables;
keep real keys outside source control.

## Gemini environment

Use `load_environment(include_gemini=True)` and read `settings.gemini`.
All fields below are required unless their description limits them to a processing mode.

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

For a Python constructor, mode examples, and upstream documentation, see
[Gemini](providers/gemini.md).

## Supadata environment

Use `load_environment(include_supadata=True)` and read `settings.supadata`.
All six fields below are required. Numeric environment values are strings which the
loader converts and validates.

| Variable | Meaning |
| --- | --- |
| `SUPADATA_API_KEY` | Supadata API key. |
| `VCP_SUPADATA_REQUEST_TIMEOUT_SECONDS` | Positive timeout for a Supadata HTTP request. |
| `VCP_SUPADATA_JOB_TIMEOUT_SECONDS` | Positive total wait for a queued transcript job. |
| `VCP_SUPADATA_POLL_INTERVAL_SECONDS` | Positive interval between queued-job polls. |
| `VCP_SUPADATA_MAX_RETRIES` | Non-negative retry count. |
| `VCP_SUPADATA_RETRY_DELAY_SECONDS` | Positive retry delay. |

For a complete settings example and transcript behavior, see [Supadata](providers/supadata.md).

## Download settings

The environment loader does not configure yt-dlp. Construct `MediaSettings` in Python:

```python
from video_context_pipeline import MediaSettings

media_settings = MediaSettings(
    request_timeout_seconds=60.0,
    cookie_file=None,
    output_directory=None,
)
```

| Field | Meaning |
| --- | --- |
| `request_timeout_seconds` | Required positive download/inspection timeout. |
| `cookie_file` | Optional `Path` to a cookie file; defaults to `None`. |
| `output_directory` | Optional `Path` for download storage; defaults to `None` for temporary storage. |

A storage directory does not change artifact ownership: downloader-created files are
still library-owned and removed by their cleanup method. Configure the JavaScript
runtime separately on [the yt-dlp provider](providers/ytdlp.md).

## Local media tools

FFmpeg tools take explicit executable paths and an operation timeout in their
constructor. They use no provider credentials or environment-loader fields.
See [local media tools](components/media-tools.md) for a complete example.
