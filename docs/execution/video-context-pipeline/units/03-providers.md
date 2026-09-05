# 03: Supadata and Gemini providers

## Plan mapping
Approved plan provider behavior, configuration, output validation and logging.
## Objective
Implement directly validated HTTP adapters against verified core protocols.
## Prerequisites and required inputs
[Core outcome](01-core.md#outcome) must be verified. Read docs/provider-validation.md and scripts/check_provider_apis.py for observed wire shapes before implementation. Raw local .validation responses may be inspected but never .env or secrets.
## Expected result
Independent async Supadata transcription and Gemini video understanding with focused mocked-HTTP tests.
## Owned paths and exclusions
Own src/video_context_pipeline/providers/gemini.py, supadata.py, _http.py; tests/test_providers.py; this record. Do not edit core modules, pyproject, media/downloader modules, .env, external/, docs index. Orchestrator owns providers/__init__.py.
## Interfaces and constraints
Use core configuration/models/protocols as settled. httpx optional extra, imported only by provider modules. Explicit caller-supplied retry/timeouts; retry only same-provider transient statuses and respect server Retry-After, no fallback. Errors/logs must omit raw response text and sensitive URL/key data. Supadata GET https://api.supadata.ai/v1/transcript x-api-key, params url/mode=generate/text=false; no lang. Queue poll /transcript/{jobId}. Offsets/durations milliseconds -> seconds. Strict nonnegative finite numbers, lang optional preserves supplied, missing malformed content error, [] empty success. Stop polling on error/final failure/deadline. Gemini POST https://generativelanguage.googleapis.com/v1beta/interactions header x-goog-api-key; response_format is the JSON SCHEMA DIRECTLY (not {type:json_schema,schema:...}). Video content type/video mime/data base64 or uri/resolution; processing static object {type:static,fps:number}, or string agentic (no FPS). generation_config only configured thinking fields, no output caps/stops. store=false, stateless single requests. Read text from steps type=model_output content type=text; response status must completed. Log only API reported usage fields allowlisted; distinguish actual agentic step presence vs merely requested mode. Canonical visual events schema must honor no-time/approx/window policies, validate all fields/bounds, no raw-text fallback. Pass explicit transcript context as untrusted data; prompt only visual observations, not audio transcription. Support small inline uploads and Files API for larger inputs based on explicit byte threshold INCLUDING encoded request size. Poll ACTIVE, handle FAILED/timeouts, delete remote upload in finally. Never send credentials to arbitrary upload URLs: allow only trusted Google HTTPS upload host validated from response. Validate requests/config before network. Local file I/O should avoid long blocking operations on event loop. For agentic long runs retain explicit request timeout; handle incomplete/nonfinal statuses as failure (no automatic resubmit changing mode/resolution).
## Acceptance criteria
Requests match live evidence and approved exact models/settings. Text/segments are public formatting concern and Gemini receives internal transcript text. Provider failure or bad schema never returns empty success. Upload deleted after all terminal paths where possible; caller input preserved. Mocked tests prove queued jobs, errors/retries, schema/timing, mode/FPS, output-cap absence and cancellation cleanup.
## Focused checks and expected evidence
Run owned unittest tests with httpx MockTransport; no real API calls. Build request capture assertions from observed wire format. Report public constructors and exact configuration used for docs.
## Shared change
Consumes core contracts only; request required shared edits from orchestrator.
## Outcome
Implemented Supadata and Gemini async HTTP adapters plus their private retry helper and focused MockTransport tests.

Changed paths: `src/video_context_pipeline/providers/{_http.py,supadata.py,gemini.py}`; `tests/test_providers.py`; this record.

Public adapter signatures for documentation:

```python
SupadataProvider(*, client: httpx.AsyncClient | None = None, logger: logging.Logger | None = None)
await SupadataProvider.transcribe(url: str, request: TranscriptRequest) -> ProviderOutput[str | tuple[TranscriptSegment, ...]]

GeminiProvider(*, client: httpx.AsyncClient | None = None, logger: logging.Logger | None = None)
await GeminiProvider.understand(
    media: MediaArtifact,
    request: VisualRequest,
    *,
    transcript_context: str | None,
) -> ProviderOutput[str | tuple[VideoEvent, ...]]
```

Supadata validates supported platform URLs, sends `GET https://api.supadata.ai/v1/transcript` with `x-api-key` and the exact `url`, `mode=generate`, and `text=false` parameters, then polls `/transcript/{jobId}` with the original job ID through status-only responses. Gemini sends `POST https://generativelanguage.googleapis.com/v1beta/interactions` with `x-goog-api-key`, `store=false`, `generation_config={"thinking_level": configured_value}`, and the response schema directly. Static processing sends `{type: "static", fps: configured_value, start_offset: "<seconds>s", end_offset: "<seconds>s"}` for bounded intervals; the public numeric offsets are converted to Google duration strings. Agentic processing sends `"agentic"` and rejects partial intervals. Windowed responses use `window_id` enums and map each ID to the original caller `TimeWindow`. Known media duration becomes the effective upper bound for all timed event and window validation; timed output without a known duration or explicit end is rejected before a request. Inline selection compares the complete compact JSON request byte count, including base64 data, with `file_upload_threshold_bytes`; larger requests stream the local file with an explicit `Content-Length` to the trusted Google resumable Files API and delete the remote file on terminal paths where a handle was obtained.
## Verification
`PYTHONPATH=src .validation/check-env/bin/python -m unittest tests/test_providers.py` passed: 10 tests in 0.032s.

`.validation/check-env/bin/mypy src/video_context_pipeline/providers --ignore-missing-imports` passed: no issues in 5 source files.

The mocked checks cover Supadata transient retry, queued status-only polling, terminal-failure rejection even when content is present, exact generation parameters, readable plain-text conversion, and malformed segment rejection. Gemini checks capture the direct JSON schema, `window_id` mapping, static FPS with verified string offsets, inspection-window prompting, original-timeline approximate prompts, no output cap, timestamped output beyond known media duration rejection, out-of-media windows and unknown timed bounds rejected before a request, automatic-mode unknown-duration rejection before a request, credential-free streamed resumable upload with explicit length and empty successful start/delete bodies, full upload-stream replay after a transient response, and remote-file deletion after cancellation. No live API call or environment-file read was performed.
## Blockers
None. Core verified; live findings recorded, including explicit gaps.
## Consequential decisions
Upgrade trigger: credentials, resource cleanup and provider response validation across dependent network calls.
Evidence: upload handles need cleanup on generation errors and cancellation, and remote outputs must satisfy shared strict pipeline contracts.

Decision: retain a successful Gemini file handle in the outer request and delete it in the request cleanup path; if file processing fails after the handle is received, delete it before propagating that failure.
Evidence: the Files API produces a remote resource before interaction generation, while the unit requires deletion for failures and cancellation.
Alternatives: rely on remote expiry or delete only after a completed interaction.
Impact: upload processing, failed generation, and cancelled generation all attempt deletion without exposing credentials to the resumable upload URL.
