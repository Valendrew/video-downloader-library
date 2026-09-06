# Provider validation

Direct checks on 2026-09-05, before adapter implementation. Credentials came from the private `.env`; no credentials or raw media are committed. These checks establish the listed observations only, not general accuracy or availability.

## Gemini

Both exact model IDs returned HTTP 200 from the model metadata endpoint. The controlled silent video contains red/RED 100 at 0–2 seconds, green/GREEN 200 at 2–4, blue/BLUE 300 at 4–6. Resolution is 640×360 at 24 source FPS.

Requests use `POST /v1beta/interactions`, `store=false`, a video content item, explicit processing/resolution/thinking, and a JSON schema directly in `response_format`. No output-token cap, stop sequence or event count limit was sent. A preliminary `json_schema` wrapper was rejected with HTTP 400 and corrected; it is not used by the implementation.

| Model | Mode | Resolution / thinking | Requested FPS | Observed outcome |
|---|---|---|---|---|
| `gemini-3.5-flash-lite` | agentic | high / high | Not sent | Completed; structured events received |
| `gemini-3.5-flash-lite` | agentic | low / low | Not sent | Completed; structured events received |
| `gemini-3.5-flash-lite` | agentic | medium / medium | Not sent | Completed; structured events received |
| `gemini-3.5-flash-lite` | static | high / high | 0.5 | Completed; structured events received |
| `gemini-3.5-flash-lite` | static | low / low | 2 | Completed; structured events received |
| `gemini-3.5-flash-lite` | static | low / minimal | 2 | Completed; structured events received |
| `gemini-3.5-flash-lite` | static | medium / medium | 1 | Completed; structured events received |
| `gemini-3.8-flash` | agentic | high / high | Not sent | Not verified: too_many_requests |
| `gemini-3.8-flash` | agentic | low / low | Not sent | Completed; structured events received |
| `gemini-3.8-flash` | agentic | medium / medium | Not sent | Completed; structured events received |
| `gemini-3.8-flash` | static | high / high | 0.5 | Completed; structured events received |
| `gemini-3.8-flash` | static | low / low | 2 | Completed; structured events received |
| `gemini-3.8-flash` | static | medium / medium | 1 | Completed; structured events received |

Completed Static responses identified the three labels and transition starts at 0, 2 and 4 seconds. Completed Agentic responses included `processing_call` and `processing_result` steps. Accepted FPS and changing API-reported usage are observations, not proof of the exact internal frame schedule. This simple fixture does not establish performance on recipes, fast motion, small text or long videos.

Transient HTTP 429 quota and HTTP 500 high-demand responses occurred on Gemini 3.8. Its Agentic high/high combination was not verified successfully. Do not label transient failures as unsupported parameters.

The Files API resumable initialization and upload returned HTTP 200; polling reached ACTIVE; deletion returned HTTP 200. Flash Lite used the uploaded file and assigned the three correct caller-defined window IDs. The Gemini 3.8 no-timestamp request returned HTTP 500, so that particular live check remains unverified. No large-file boundary or long-running background request was tested.

A later Flash Lite check verified an untimed response and Static clipping. Numeric `start_offset: 2` / `end_offset: 4`, as shown in the video guide, returned HTTP 400. The [official OpenAPI specification](https://ai.google.dev/static/api/interactions.openapi.json) instead defines these fields as duration strings. Sending `start_offset: "2s"`, `end_offset: "4s"`, and `fps: 1` returned HTTP 200 and only the green/`GREEN 200` observation. Public configuration remains numeric seconds; the adapter converts it to the verified wire representation.

## Supadata

A direct GET `/v1/transcript` for the public YouTube video `jNQXAC9IVRw`, with `mode=generate`, `text=false`, and no `lang`, returned HTTP 200. It reported English and four segments with text, offset and duration in milliseconds. This confirms the generated-segment response shape for that example.

The Instagram example `Chunk8-jurw` returned HTTP 200 with an empty `content` array. This verifies the empty-result response shape; it does not independently establish whether the source contains speech. The TikTok example `6748451240264420610` returned HTTP 404. Successful TikTok generation remains unverified.

Queued jobs are documented but were not observed in these calls. Cover their handling with simulated responses, and do not claim live verification.

## Download and local media tools

`yt-dlp[default]==2026.8.19` was the latest stable PyPI version at implementation start. YouTube inspection returned video ID and 19-second duration. `worst[ext=mp4]` was unavailable on this sample; selecting inspected format 134 downloaded an MP4 successfully. This was an explicit second test of another selection, not a runtime fallback.

Instagram sample `Chunk8-jurw` inspected successfully, with unknown duration and a CSRF warning. TikTok sample `6748451240264420610` failed with a login-required error. Successful authenticated TikTok download is not verified. URLs were taken from the upstream yt-dlp extractor tests. No authentication probe is provided.

A local FFmpeg WAV-to-MP3 conversion succeeded and ffprobe confirmed codec MP3 and duration 1 second. FFmpeg and ffprobe are installed. YouTube extraction was checked using an explicit Node.js runtime; document Deno/Node setup for hosts.

### Source thumbnails (2026-09-05)

A direct `YtDlpMediaProvider.download_thumbnail()` call for the same public YouTube
sample, with an explicit Node.js runtime and 30-second timeout, downloaded a
23,038-byte WebP image. The adapter used `skip_download=True`, `writethumbnail=True`,
and `write_all_thumbnails=False` with yt-dlp 2026.8.19. The owned artifact was cleaned
up after the check. These correspond to upstream
[thumbnail and skip-download options](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#thumbnail-options).
No paid provider calls were made. Thumbnail downloads on Instagram, TikTok, and
cookie-authenticated sources remain unverified.

Offline tests cover normalized inspection/metadata, missing and invalid output,
owned-path enforcement, partial-file cleanup, timeout/cancellation, and embedding a
fixture image returned by a fake downloader into MP3 and M4A with real FFmpeg.
Those embedding tests use a generated PPM image, not the live WebP download.

## Instagram download diagnosis

A limited direct check of a reported Instagram post reproduced a progressive MP4
with missing codec and duration metadata. Before the correction it was classified
as `audio/mp4`; ffprobe measured H.264 video plus AAC audio, 57.26 seconds, in a
23,185,035-byte file. Unknown MP4 video-codec metadata now retains `video/mp4` rather
than being treated as explicit audio-only metadata. No duration is synthesized.

Regression tests cover unknown versus explicit audio/video codecs, safe nested
pipeline errors, distinct transport failures, and Supadata queue transitions and
incomplete terminal responses. Supadata/Gemini request parameters are unchanged.
After confirming that Render uses the same private keys as the original checkout,
one no-retry check per service was run locally against the reported URL:

| Service | Explicit diagnostic settings | Observed result |
| --- | --- | --- |
| Supadata | `mode=generate`, `text=false`; 180-second HTTP and job limits, 3-second polling interval, zero retries | HTTP 200 and non-empty transcript in 7.7 seconds; no queued job |
| Gemini | `gemini-3.8-flash`, Static at 1 FPS, low resolution/thinking, untimed text output; 60-second request limit, zero retries; 20 MB upload threshold, 120-second file deadline, 2-second file polling | Files API upload/readiness and Interactions API succeeded; non-empty analysis in about 16 seconds after downloading; remote deletion returned HTTP 200 |

These calls confirm successful responses for this URL and those settings, not
transcript/analysis accuracy. Local temporary media was removed. The earlier
180-second Supadata timeout on Render was not reproduced, and its exact cause
remains unconfirmed; a successful local call does not verify the deployed host or
its submitted settings. No additional paid retries were made.

## Repeating checks

Manual scripts in `scripts/` explicitly read an environment file; the library itself never does so. Scripts send real requests and are excluded from routine CI. Private responses and media are kept under ignored `.validation/`. Successful matrix cases are not repeated automatically.

## Sources

- [Gemini video processing](https://ai.google.dev/gemini-api/docs/video-understanding)
- [Interactions request and response reference](https://ai.google.dev/api/interactions-api)
- [Gemini Files API](https://ai.google.dev/gemini-api/docs/files)
- [Supadata transcript endpoint](https://docs.supadata.ai/api-reference/endpoint/transcript/transcript)
- [Supadata job results](https://docs.supadata.ai/api-reference/endpoint/transcript/transcript-get)
- [yt-dlp release](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19)
