# 01: Core API and strict pipeline

## Plan mapping
Approved plan sections 2, configuration, tests and packaging. Read docs/implementation-plan.md.
## Objective
Build usable independent public data/configuration contracts and an asynchronous pipeline that composes injected provider protocols. This unit must work and be testable using fake components before concrete adapters exist.
## Prerequisites and required inputs
No implementation prerequisites. Repository has only imported references and docs. Python 3.11+ is required; system python3 available, uv not on PATH yet. Orchestrator handles provider live checks and tooling installation.
## Expected result
Typed package foundation and complete fake-tested orchestration, standalone formatting and logging, with provider interfaces usable by the next workers.
## Owned paths and exclusions
Own pyproject.toml; src/video_context_pipeline/__init__.py, py.typed, errors.py, models.py, config.py, protocols.py, formatting.py, pipeline.py, logging.py; tests/test_core.py, tests/test_pipeline.py, tests/test_logging.py; this unit record. Do not touch external/, .env, docs index, provider modules, media.py, uv.lock, other tests/docs.
## Interfaces and constraints
Use dataclasses and stdlib where possible, Python>=3.11, uv_build, package name video-context-pipeline. Explicit config (no silent fallbacks), asynchronous methods, injected provider protocols. Expose named outputs with format/data/provider/status and optional provider language/usage. Transcript segment seconds with nullable end. Visual no-time, approximate timestamp, or caller-defined windows; validate finite times and bounds. Public text vs structured is exclusive. Artifacts must support explicit cleanup and context manager, preserve successful outputs and clean temporary dependencies. Pipeline accepts platform URL, requested metadata/transcription/visual/media selections, explicit transcript-context coupling; valid same-provider retries separate config, no fallback or partial success. URL only YouTube/Instagram/TikTok (allow their actual subdomains and short links, reject credentials/other hosts). Shared protocols must make concrete provider implementation straightforward; choose cohesive explicit configuration classes for core pipeline and provider settings, including Gemini exact approved models/levels/modes/resolution, Supadata timeouts/poll/retry and download/media parameters. Model 3.8 low/medium/high; 3.5-lite minimal/low/medium/high. Require FPS whenever static can apply; threshold only auto. Explicit environment loader no dotenv/import side effects; optional fields use explicit None. Do not set max_output_tokens, stop sequences or event caps. Use logging with allowlisted factual fields and request correlation, safe JSON helper, no payload/secret/url logging. Runtime packages optional extras: providers use httpx; yt-dlp exact latest resolved by orchestrator later. Don't pin invented current versions. Keep backend-specific imports out of base package import.
## Acceptance criteria
All components can use the same public contracts. Pipeline output is atomic even when independent concurrent tasks fail; await cancellation cleanup, preserve caller-owned files, validate before side effects. Disabled providers need no credentials. Plain text does not contain segments/JSON. Missing/invalid params fail clearly; booleans/NaN/infinity not valid numeric config. Failed schema/timestamps error. No logging of raw secrets/provider bodies or inferred metrics.
## Focused checks and expected evidence
Use python3 -m unittest discover -s tests (stdlib tests) for the owned test files. Cover fail-fast/cancellation/cleanup, three transcript/video coupling cases, empty success vs malformed failure, env rejection, formatting, temporal rules, JSON logging. Include fakes and temporary files. No real API requests, no benchmarks. Record public API signatures and use examples here for next workers.
## Shared change
Core contracts defined in owned modules; readers are all later adapters and docs; tests verify behavioral contracts. Search terms Pipeline, MediaArtifact, Transcript, Visual, Config.
## Outcome
Implemented typed package foundation, explicit provider/component settings, safe opt-in JSON logging, and atomic async orchestration using injected protocols. The pipeline validates a supported public URL and all requested dependencies before provider side effects; successful sibling-owned media is cleaned after failure or cancellation, while requested media remains caller-controlled. Internal media used only for visual analysis is cleaned after a successful visual result.

Changed paths: `pyproject.toml`; `src/video_context_pipeline/{__init__.py,py.typed,errors.py,models.py,config.py,protocols.py,formatting.py,pipeline.py,logging.py}`; `tests/{test_core.py,test_pipeline.py,test_logging.py}`; this record.

Shared API signatures for dependent workers:

```python
Pipeline(
    *, metadata_provider: MetadataProvider | None = None,
    transcript_provider: TranscriptProvider | None = None,
    media_provider: MediaProvider | None = None,
    visual_provider: VisualProvider | None = None,
    logger: logging.Logger | None = None,
)
await Pipeline.run(url: str, request: PipelineRequest) -> PipelineResult

async MetadataProvider.inspect(url: str) -> ProviderOutput[Mapping[str, Any]]
async TranscriptProvider.transcribe(url: str, request: TranscriptRequest) -> ProviderOutput[str | tuple[TranscriptSegment, ...]]
async MediaProvider.download(url: str, request: MediaRequest) -> ProviderOutput[MediaArtifact]
async VisualProvider.understand(media: MediaArtifact, request: VisualRequest, *, transcript_context: str | None) -> ProviderOutput[str | tuple[VideoEvent, ...]]
```

`PipelineRequest(metadata=False, transcript=None, visual=None, media=None, visual_media=None, include_transcript_context=False)` exposes only `metadata`, `transcript`, `visual`, and explicitly requested `media` outputs. `visual_media` is the explicit internal download selection required for a pipeline visual request when `media` is not requested. `include_transcript_context=True` requires both transcript and visual requests. `PipelineResult.outputs` carries those named outputs and supports `cleanup()` plus a synchronous context manager for returned owned artifacts.

`GeminiSettings(api_key, model, media_resolution, thinking_level, processing_mode, static_fps, agentic_threshold_seconds, request_timeout_seconds, max_retries, retry_backoff_seconds, file_upload_threshold_bytes, file_poll_deadline_seconds, file_poll_interval_seconds)` and `SupadataSettings(api_key, request_timeout_seconds, job_timeout_seconds, poll_interval_seconds, max_retries, retry_delay_seconds)` require every applicable value; keys are excluded from representations. `MediaRequest(settings, selected_format_id)` requires an explicit format identifier. Adapter results use `ProviderOutput(format, data, provider, status, language=None, usage=None)` with `OutputFormat` and `OutputStatus` enums.

`VisualRequest(format, settings, timestamp_mode, windows=(), inspection_windows=(), analyzed_start_seconds=0, analyzed_end_seconds=None)` validates all supplied windows against the finite, nonnegative analyzed interval before pipeline side effects. `windows` assigns caller-defined event windows when `timestamp_mode="windows"`; `inspection_windows` is the only explicit targeted-inspection policy. `VIDEO_TEXT` permits all timestamp modes so an adapter can return readable timestamped prose while event formats remain canonical `VideoEvent` schema.

`MediaArtifact(path, media_type, duration_seconds=None, owned=False, dependencies=(), owned_directory=None)` carries compatible media type and known duration. `owned_directory` is valid only for an owned artifact whose path it contains; cleanup unlinks owned files and removes that directory only when it is empty, so caller directories are never removed. Pipeline automatic Gemini selection rejects an artifact with `duration_seconds is None` before visual-provider work.

`Pipeline.run` emits standard logging events `pipeline started`, `pipeline completed`, `pipeline failed`, `pipeline cancelled`, and `pipeline cleanup`; each carries the same ContextVar-backed `request_id` plus allowlisted factual fields only. `configure_json_logging()` is opt-in and package import does not configure logging.
## Verification
`python3 -m unittest discover -s tests` — 14 worker tests passed; 15 passed after main-task logging integration correction (INFO console setup, preserved correlation, duration and cleanup failure logs).

- Atomic failure/cancellation and ownership-aware cleanup: `test_pipeline` verifies no partial result, cleans a completed sibling artifact when another concurrent provider fails, cleans on cancellation, and preserves requested media until explicit cleanup.
- Transcript/video coupling: `test_pipeline` verifies visual-only, independent transcript+visual, and explicitly coupled transcript-context calls.
- Output and schema contracts: `test_core` and `test_pipeline` verify plain-text formatting, supported URL validation, valid empty transcript success, malformed segment rejection, finite numeric validation, timestamp/window bounds, readable timestamped text, owned temporary-directory cleanup, and rejection of automatic visual selection with unknown duration.
- Configuration and logging: `test_core` verifies disabled providers need no credentials and explicit Gemini validation; `test_logging` verifies JSON output only admits allowlisted factual fields and rejects secrets, URLs, provider bodies, and inferred cost fields; `test_pipeline` verifies lifecycle event correlation for a successful request.
## Blockers
None.
## Consequential decisions
Upgrade trigger: shared public API and atomic concurrent pipeline with cleanup.
Evidence: independent provider outcomes must never escape as partial success and file lifetime crosses component boundaries.

Decision: represent pipeline-only visual downloads with `PipelineRequest.visual_media` rather than adding downloader settings to `VisualRequest`.
Evidence: standalone `VisualProvider.understand` accepts an existing `MediaArtifact`; a required download configuration on `VisualRequest` would make local-file analysis carry irrelevant downloader parameters.
Alternatives: embed `MediaRequest` in every visual request; let pipeline choose an implicit download format.
Impact: visual adapters remain reusable for local artifacts, and pipeline download behavior stays explicit without silently selecting a downloader format.
