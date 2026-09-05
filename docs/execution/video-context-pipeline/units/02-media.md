# 02: Download and media tools

## Plan mapping
Approved plan components, yt-dlp, compatibility and tests.
## Objective
Implement inspect, select, download and independent ffmpeg audio extraction/conversion/metadata components against verified core contracts.
## Prerequisites and required inputs
[Core outcome](01-core.md#outcome) must be verified. Direct tool evidence is recorded in docs/provider-validation.md. Read the approved plan and core public signatures.
## Expected result
Usable async components with file ownership, actual progress, safe errors and focused tests. Preserve runtime behavior of the downloader reference without copying unlicensed code.
## Owned paths and exclusions
Own src/video_context_pipeline/providers/ytdlp.py, src/video_context_pipeline/media.py, tests/test_media.py, tests/test_ytdlp.py and this record. Do not touch core files, pyproject, .env, external/, other provider modules, docs index. Provider package __init__.py is orchestrator-owned.
## Interfaces and constraints
Implement existing core protocols/configs. yt-dlp pinned2026.8.19 by core. Explicit cookie path and JS runtime configuration; don't run auth probe. Inspect once and reuse formats in coordinator; no captions/subtitles. Maintain downloader audio-only compatibility: mp3; AAC(mp4a) mp4/m4a; m4p. Select best compatible if its abr (otherwise tbr) >= explicitly supplied ratio times best overall, otherwise bestaudio/best then explicit MP3 conversion. Metadata outputs include exact/estimated sizes and codec/bitrate. No ffmpeg conversion hidden inside unrelated settings; transform independent artifact. Blocking yt-dlp must be isolated and await cleanup on cancellation; don't leave a to_thread download writing into deleted tempdir. Async subprocess strategy acceptable with safe result/progress collection; do not print URLs/cookie paths/provider stderr into public logs or exceptions. Components need configurable explicit timeouts and actual step/byte events; no fake postprocess %. FFmpeg binary paths explicit, no shell=True, validate codec/container pairs, refuse overwrite caller input, use dedicated temp output dir, terminate/kill and await process on cancellation/timeouts. ffprobe actual output validates resulting file media type, duration, streams. Metadata/thumbnail enrichment must operate only on supported containers and preserve source. Cookie/JS options should produce actionable missing-tool errors without leaking paths. Video downloads must permit clear source quality policies, not hard-coded worst selection. Do not invent silent numeric defaults in public config.
## Acceptance criteria
Direct compatible audio selection avoids conversion; explicit conversion path creates expected media; failures/cancel remove owned temp artifacts and preserve originals. No captions/network tests in routine tests. External projects untouched.
## Focused checks and expected evidence
Owned unittest suites for selection, subprocess failures and cancellation, argument mapping, resource ownership, errors/progress. Real local ffmpeg smoke on synthetic fixture where available; no additional paid requests or arbitrary platform URLs. Orchestrator has direct YouTube check; Instagram/TikTok remain unexercised until valid examples supplied/found.
## Shared change
Consumes core contracts without altering them. Request any required shared edit from orchestrator.
## Outcome
Implemented independent yt-dlp inspection, explicit audio selection/download, and ffmpeg media tooling.

Changed paths: `src/video_context_pipeline/providers/ytdlp.py`; `src/video_context_pipeline/media.py`; `tests/test_ytdlp.py`; `tests/test_media.py`; this record.

Public module signatures:

```python
YtDlpMediaProvider(*, js_runtimes: Mapping[str, Mapping[str, Any]], downloader_factory: DownloaderFactory | None = None, logger: logging.Logger | None = None, progress: Callable[[DownloadProgress], None] | None = None)
await YtDlpMediaProvider.inspect_media(url: str, settings: MediaSettings) -> MediaInspection
await YtDlpMediaProvider.download(url: str, request: MediaRequest, *, progress: Callable[[DownloadProgress], None] | None = None) -> ProviderOutput[MediaArtifact]
YtDlpMetadataProvider(*, settings: MediaSettings, media_provider: YtDlpMediaProvider)
await YtDlpMetadataProvider.inspect(url: str) -> ProviderOutput[Mapping[str, Any]]
plan_audio_download(inspection: MediaInspection, *, compatible_bitrate_ratio: float) -> AudioDownloadPlan

FFmpegMediaTools(*, ffmpeg_path: Path, ffprobe_path: Path, timeout_seconds: float, logger: logging.Logger | None = None)
await FFmpegMediaTools.probe(path: Path) -> MediaMetadata
await FFmpegMediaTools.extract_audio(source: MediaArtifact, *, destination: Path, codec: str, container: str, bitrate_kbps: int) -> MediaArtifact
await FFmpegMediaTools.convert_audio(source: MediaArtifact, *, destination: Path, codec: str, container: str, bitrate_kbps: int) -> MediaArtifact
await FFmpegMediaTools.enrich_metadata(source: MediaArtifact, *, destination: Path, metadata: Mapping[str, str], thumbnail: Path | None = None) -> MediaArtifact
```

`MediaFormat` exposes exact and estimated sizes, audio/total bitrate and codecs from yt-dlp inspection. `YtDlpMetadataProvider` adapts the same one inspection to the core `MetadataProvider` contract with title, description, duration and formats. `MediaMetadata` carries actual ffprobe duration, type, codecs, bitrate, and size. A direct compatible source is audio-only MP3 or M4P, or audio-only AAC (`mp4a`) in MP4/M4A. `plan_audio_download` uses caller-supplied finite ratio and returns the explicit `bestaudio/best` source with required separate MP3 conversion whenever no compatible source meets it. Downloads disable implicit yt-dlp retries and postprocessors, use an explicit JS runtime mapping, suppress provider diagnostics, and deliver actual total-byte provenance through `DownloadProgress.total_is_estimate`. FFmpeg uses a dedicated temporary directory, validates requested codecs with ffprobe, and atomically publishes only when the caller destination remains absent. Source artifacts are never overwritten; audio codec and bitrate are explicit.
## Verification
`.validation/check-env/bin/python -m unittest tests.test_media tests.test_ytdlp` — 9 tests passed. Main-task review confirmed clean-checkout fixtures and protocol composition; mypy passed for both owned source modules. A local variable rename fixed a typing conflict; missing bitrate comparison uses zero solely to preserve the reference selection policy (never logged as measured bitrate).

- Real local ffmpeg/ffprobe smoke: tests generate WAV, MP4, and PPM thumbnail inputs with standard-library code in temporary directories. They verify video extraction, audio conversion, MP3 enrichment with cover art, requested codec validation, and preservation of sources.
- FFmpeg errors and resource ownership: existing destinations and wrong source kinds are refused, a missing configured ffmpeg binary produces a safe `ProviderError`, a competing destination is preserved during atomic publication, and a cancelled subprocess is terminated and awaited.
- yt-dlp selection and mapping: audio-only AAC/M4P compatibility, muxed-video rejection, `bestaudio/best` fallback, finite-ratio validation, media type mapping, strict result-path containment, and malformed numerical metadata are covered. The fake adapter verifies explicit source format, timeout, cookie path, JS runtime options, disabled retries, suppressed provider logger, and actual byte progress delivery. A core `Pipeline` composition test verifies the metadata adapter's contract and structured description/formats.
- Cancellation: a blocking fake downloader exits through its progress hook before the task returns cancellation; its dedicated output directory is removed only afterwards.
## Blockers
None. Core verified.
## Consequential decisions
Upgrade trigger: cancellation and cleanup across async orchestration and blocking processes.
Evidence: download workers must stop before pipeline deletes owned files; caller-owned inputs must survive transformations.

Decision: shield the yt-dlp worker and await its terminal result after cancellation or timeout before deleting its dedicated output directory.
Evidence: `asyncio.to_thread()` cannot stop a blocking yt-dlp call; deleting the directory while it still writes risks incomplete output and a file-lifetime race.
Alternatives: abandon the thread and remove its directory immediately; run yt-dlp with an unmanaged shell process.
Impact: progress hooks request cancellation, the bounded worker finishes before cleanup, and downloads do not leave a background writer in a removed directory.

Decision: publish ffmpeg output by hard-linking the validated staged file into the caller destination, then unlinking the stage.
Evidence: replacing the destination after a preflight existence check can overwrite a file another actor creates while ffmpeg is running.
Alternatives: `os.replace()` after validation; reserve the destination with a placeholder before work starts.
Impact: a late competing destination is retained and the transform fails without overwriting caller data.
