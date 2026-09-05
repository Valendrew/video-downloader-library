# Video Context Pipeline: implementation plan

## 1. Goal and prerequisites

Build `video-context-pipeline`, a Python library whose components can be used separately or combined to inspect, download, transcribe and understand videos.

Support YouTube, Instagram and TikTok URLs. Downloaded files can pass between components; accepting arbitrary local files as the initial pipeline input is deferred.

The library must support later integration into the two projects in `external/`. Do not modify those projects during this work. Their interfaces, output formats and operating requirements are compatibility references.

Before implementation:

1. Check that `GEMINI_API_KEY` and `SUPADATA_API_KEY` are available. If either is missing, **stop before changing files** and report its name. Never print secret values.
2. Save this plan as `docs/implementation-plan.md`.
3. Check the intended provider requests directly against their APIs before implementing the adapters. Record unsupported settings and resolve any changes to approved behavior before proceeding.

## 2. Components and returned data

Each component has its own settings and can be called independently.

| Component | Accepts | Returns |
|---|---|---|
| Inspect | Platform URL | Metadata and available formats |
| Select format | Available formats and selection rules | Selected download format |
| Download | URL and selected format | Video or audio file |
| Extract audio | Downloaded video | Audio file |
| Convert audio | Audio file and requested format | Converted audio file |
| Add metadata | Supported media file and supplied metadata/thumbnail | Updated media file |
| Transcribe | Public platform URL | Plain text or timed segments |
| Understand video | Video file and optional transcript context | Plain text or visual events |

File results expose their path, media information and an explicit cleanup method or context manager. Keep successful files available until the caller releases them. Clean up temporary files after failure or cancellation.

Return named outputs for everything the caller requested. Each output identifies its format, data, provider and whether it completed with content or a valid empty result. Do not expose extra outputs merely because they were needed internally.

Output formatting must match the caller’s choice:

- **Transcript text:** plain text.
- **Transcript segments:** objects containing `start_seconds`, nullable `end_seconds`, and `text`. Preserve provider-reported language separately when available.
- **Video text:** readable prose.
- **Video events:** descriptions with the selected timestamp or time-window fields.
- **Metadata:** structured fields.
- **Media:** a file result with ownership and cleanup information.

Keep public formatting separate from the text supplied to Gemini. A caller can request transcript segments while Gemini receives a concise text version of those same segments.

Support transcription alone, video understanding alone, both independently, or both with the transcript passed to Gemini.

The optional pipeline validates settings before starting. Every requested component must succeed. On terminal failure, stop dependent work, cancel pending work where possible, clean up and raise an actionable error. Never return partial success. Remote jobs already submitted may continue running.

## 3. Providers and settings

### yt-dlp

Use the latest stable version available when implementation begins and lock the tested version. Do not update it automatically at runtime.

Keep format selection, downloading, conversion and metadata writing separate. Preserve the downloader project’s selection behavior through explicit settings, including its compatible-format quality ratio.

MP3 conversion happens only when the selected policy requires it. It is not a recovery mechanism for failed downloads. Conversion failure fails the requested workflow.

Accept cookie files for real operations. Remove the standalone authentication test, which does not reliably establish whether authentication works.

### Supadata

Use Supadata as the only transcription provider, always with `mode="generate"`.

Do not use existing captions, automatic-caption extraction, language defaults, Supadata auto/native modes or Gemini transcription fallback.

Handle immediate results and queued jobs. Require explicit retry, polling and timeout settings. Normalize segment times to seconds. Treat malformed responses as errors; accept documented no-speech results as empty success.

### Gemini

Support `gemini-3.8-flash` and `gemini-3.5-flash-lite`, with settings confirmed through direct API checks.

Support these processing choices:

- **Static:** use an explicitly configured sampling rate.
- **Agentic:** let the model select video content to inspect.
- **Automatic selection:** use Static below a required duration threshold and Agentic at or above it. Fail if duration is unknown.

Do not send Static FPS settings to Agentic requests. Distinguish API acceptance of an FPS value from evidence that the requested sampling actually occurred.

Require explicit resolution and thinking settings. Validate thinking levels for the chosen model.

Explain resolution simply:

- `low`: general actions and descriptions.
- `medium`: currently the same documented video allocation as `low`.
- `high`: small details and on-screen text.

Download quality and Gemini resolution are separate settings. Higher Gemini resolution cannot restore detail missing from the downloaded file. Do not automatically increase resolution or submit a second analysis request.

Do not set output-token caps, stop sequences or hard event-count limits. Request concise, relevant observations. Detect incomplete or malformed responses and fail instead of returning them as successful results.

### Timestamps

Offer three explicit choices:

1. Ordered events without times.
2. Events with approximate model-reported times.
3. Events assigned to caller-defined time windows.

The library creates window boundaries; Gemini assigns events to windows. Never calculate event times from their position in the response or from FPS.

Validate returned times against the analyzed interval. Do not silently repair invalid values.

The recipe project’s existing three-/six-second schedule is not mandatory. Retain targeted inspection only as an explicitly selected policy.

### Configuration

Use typed Python configuration objects. Provide an explicit environment loader that creates those same objects. Do not read dotenv files or configure logging automatically when importing the package.

Missing or invalid applicable settings must cause clear errors, not silent substitutions.

Document these environment variables:

| Variable | Meaning |
|---|---|
| `GEMINI_API_KEY` | Gemini credentials |
| `SUPADATA_API_KEY` | Supadata credentials |
| `VCP_GEMINI_MODEL` | Selected supported model |
| `VCP_GEMINI_MEDIA_RESOLUTION` | Video detail setting |
| `VCP_GEMINI_THINKING_LEVEL` | Model-compatible thinking level |
| `VCP_GEMINI_PROCESSING_MODE` | Static, Agentic or automatic selection |
| `VCP_GEMINI_STATIC_FPS` | Sampling rate when Static can be selected |
| `VCP_GEMINI_AGENTIC_THRESHOLD_SECONDS` | Duration threshold for automatic selection |

Keep requested outputs, format rules, timestamps, cookies, retries and timeouts in their corresponding component settings. Examples must explicitly supply all applicable settings.

Normal library use requires credentials only for enabled providers. Implementation requires both keys because both providers must be checked.

## 4. Checks and project compatibility

Do not add performance benchmarks.

Before implementing provider adapters, make direct, limited API checks:

- Check each Gemini model’s intended modes, resolution, thinking, FPS and structured output.
- Use a short video with known transitions and visible text to inspect observations and approximate timestamps.
- Check Supadata generation, segments, language reporting and queued-job handling where exercised.
- Check representative platform downloads and required conversion tools.

Record whether each finding is documented, observed, rejected or not exercised. Do not claim untested behavior is verified.

Add focused automated tests for configuration errors, output formatting, response parsing, timestamps, pipeline failure, cancellation and file cleanup. Use simulated provider responses in routine CI; do not make paid API calls there.

Document how the library maps to each imported project:

- **Recipe project:** description, transcript and visual observations remain available for its combined recipe input. Recipe generation, database operations and HTTP/SSE endpoints remain application responsibilities.
- **Downloader project:** preserve format summaries, conversion rules, progress stages and file ownership. Jobs, expiry, UI and file serving remain application responsibilities.

Provide asynchronous calls and progress events suitable for GUI, TUI, CLI and web applications. Keep blocking downloader work off the application’s event loop.

## 5. Packaging, documentation and logs

Use Python ≥3.11, a `src/video_context_pipeline` layout, `uv_build`, typed public interfaces, `py.typed`, optional provider dependencies and a development lockfile.

Use the package name `video-context-pipeline`, MIT licensing and initial version `0.1.0`. Check code provenance and dependency licenses before publication; do not copy unlicensed code from the imported projects.

Prepare GitHub release automation for wheels, source archives and checksums. Document installation pinned to a release artifact. PyPI publication is deferred.

Create a small MkDocs site suitable for GitHub Pages. Cover installation, settings, components, output schemas, errors, cleanup, conversion tools, examples, provider checks and project compatibility.

Make components discoverable by video, audio and text input/output. Give each component one main documentation page, linked from relevant categories. Clearly distinguish public URLs from downloaded files.

Use standard Python logging and an optional JSON console setup for hosting platforms such as Render. Record request identifiers, stages, durations, retries, provider status, bytes, cleanup and provider-reported usage.

Never log secrets, dollar estimates or inferred usage. Distinguish model-generated observations from verified facts.
