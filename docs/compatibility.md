# Compatibility

The package supports Python 3.11 and newer. CI prepares checks for Python 3.11 and
current stable Python 3.14.

Supported public URL platforms are YouTube, Instagram, and TikTok. Support by the
library means URL validation and adapter selection, not a guarantee that every public
or authenticated item is available. A source may require login, cookies, or a
JavaScript runtime. The downloader uses an explicit Node.js or Deno-style runtime
mapping supplied by the caller; it does not discover one automatically.

Download inspection reports exact sizes when known and estimates separately. Audio
selection can use a directly compatible audio-only MP3/M4P or AAC-in-MP4/M4A source.
Otherwise, the explicit policy is to download `bestaudio/best` and require a separate
MP3 conversion. This is a caller-visible conversion policy, not an error fallback.

`ffmpeg` and `ffprobe` must be installed separately for local extraction, conversion,
metadata enrichment, and measurement. Audio transforms support MP3/MP3, AAC/M4A, and
AAC/MP4. A transform writes a new destination and never overwrites the source.

## Reference-application boundaries

The references are `external/video-recipe-extractor` at commit
`477b00f1389afd116806e114471e7870db7d1d0e` and `external/yt-dlp-ui` at
`2c68505c02761c4d4aa0ba43a3a195ef81e63d60`. Neither was modified or packaged.
Integration into their running applications is the next task, so end-to-end
compatibility and performance have not been measured here.

The recipe project's `mealvault/pipeline/context.py::format_output` combines these
fields; its integration adapter can keep that application presentation:

| Existing recipe input | Library output |
| --- | --- |
| `video_description` | `result.output("metadata").data["description"]` |
| `transcript` | `result.output("transcript").data` with `transcript_text` requested |
| Visual event `description` | `VideoEvent.description` from `video_events` |
| Visual event `timestamp` string | Format `timestamp_seconds` or `window` explicitly for the existing label |

The library returns typed events rather than the old event dictionaries. Request only
`visual` when the recipe application needs only Gemini output. Recipe generation,
combined prompt formatting, duration policy, database operations and HTTP/SSE endpoints
remain application responsibilities. The old captions/Gemini-audio fallback behavior
is intentionally replaced by mandatory Supadata generation whenever transcription is
requested; a terminal provider error raises instead of producing a partial recipe input.

A downloader application's format summary maps to `MediaInspection` and
`MediaFormat`; its explicit compatible-bitrate ratio and conversion decision map to
`plan_audio_download`; its progress display maps to `DownloadProgress`; and ownership
maps to `MediaArtifact.owned` and `cleanup()`. The application owns jobs, expiry,
browser UI, file serving, and retained files. To retain the current reference quality
policy, explicitly pass `compatible_bitrate_ratio=0.80`; there is no library default. The library creates no UI, job queue, or
file-serving endpoint.

See [provider validation](provider-validation.md) for the exact live observations and
remaining gaps. In particular, successful TikTok transcript generation, authenticated
TikTok downloads, queued Supadata jobs, Gemini 3.8 agentic high/high, a Gemini 3.8
untimed request, large-file boundaries, and long-running background requests remain
unverified. Transient quota or demand failures are not treated as unsupported settings.
