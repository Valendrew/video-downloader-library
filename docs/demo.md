# Browser demo

The optional demo runs the library from a browser using a FastAPI backend and plain
HTML, CSS, and JavaScript in `demo/static/`. It offers independent components, the
actual `Pipeline`, and an application-composed audio flow. The Python library and
its public interfaces do not depend on the demo.

**There is no login. Anyone who can reach the page can run enabled operations using
the server's provider keys.** A browser session isolates its uploads, jobs, and
artifacts from other sessions; it does not restrict who may use the service.

## Run locally

From the repository root, install Python 3.11+, [uv](https://docs.astral.sh/uv/getting-started/installation/),
FFmpeg, ffprobe, and [Deno](https://docs.deno.com/runtime/getting_started/installation/)
or Node.js (see [host prerequisites](install.md)).
The backend discovers these host executables; deployment packages them in the image.

```bash
uv sync --locked --extra all --group demo
cp demo/.env.example .env
```

Edit `.env` and set only the keys for the providers you want to enable:

```dotenv
GEMINI_API_KEY=
SUPADATA_API_KEY=
```

Blank or absent keys disable the corresponding provider operations. Downloads and
local media processing need no provider API keys. Credentials stay on the server;
the page receives availability information, never key values. Operational settings
come from explicit page inputs, not additional environment variables. The demo
constructs library settings directly; the library's broader
[environment loader](configuration.md) remains available to Python applications.

```bash
uv run --locked --extra all --group demo --env-file .env uvicorn demo.server:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Open [the local demo](http://127.0.0.1:8000). The provider-free
[health endpoint](http://127.0.0.1:8000/health) checks that the web application is up;
it does not verify keys or call a media source. Keep one worker: job and session
state are stored in that process's memory.

## Use the three modes

### Independent components

Choose a component, then provide its required inputs and applicable settings.
Inspect a supported public URL to see metadata, formats, and thumbnail references;
select an inspected format explicitly to download media. The audio planner reports
its selection and conversion requirement without downloading. Source-thumbnail
download uses the library's preferred available image policy, not a specific
thumbnail resolution selector.

Supadata transcribes public URLs as text or timed segments. Gemini analyzes uploaded
local video as prose or structured events. Local uploads also support probe, audio
extraction, audio conversion, and metadata enrichment to a new file. Results show
structured data and downloadable artifacts when an operation produces files.

### Pipeline

Choose metadata, transcription, media, and/or visual outputs. This mode calls the
library's `Pipeline` with only the selected providers. Visual analysis requires an
explicit video format selection and download settings, even if you do not request
media as a returned output. You can explicitly include transcript context when both
transcription and visuals are requested.

Every requested stage must succeed. A failure produces no partial pipeline result;
pending work is cancelled where possible and owned media is cleaned up. The
pipeline removes a visual-only internal download after processing. See
[Pipeline semantics](components/pipeline.md).

### Audio flow

Inspect the URL, enter a compatible-bitrate ratio, and review the returned audio
plan before running it. The demo composes library operations: download the reviewed
selection, convert to MP3 when the plan requires it, and optionally write tags and
source or uploaded cover art to a copy. Enter the conversion bitrate and FFmpeg
timeout when applicable.

A compatible plan can retain its selected MP3/M4P or AAC MP4/M4A source; this flow
does not promise MP3 for every plan. A fallback plan requires the separate MP3
conversion step. Requesting tags or artwork makes enrichment part of the required
work; failures do not silently omit it. Source artwork comes from
`download_thumbnail()`, and uploaded artwork is passed to local enrichment.

## Explicit settings

Required operational fields start blank. Fill every applicable field; a missing or
invalid value is rejected. A placeholder is guidance, not a submitted default.
The `?` help controls open with a click, touch, or keyboard Enter/Space and also
show help on hover. Presets select operations without filling service settings.
Select detected runtime and FFmpeg/ffprobe paths explicitly; these refer to the
server's installed tools. Use uploaded files or compatible completed session
artifacts as independent-service inputs. Probe a file to record its measured type
and duration for later automatic visual processing.

| Operation | Inputs and controls |
| --- | --- |
| URL inspection/download | Supported URL, request timeout, explicit format selection for download, optional uploaded or pasted Netscape cookies |
| Audio planning | Inspection and positive compatible-bitrate ratio; review selected format and MP3 conversion requirement |
| Supadata | Text/segments output, HTTP timeout, queued-job timeout, polling interval, retry count, retry delay |
| Gemini | Model, resolution, thinking level, processing mode, static FPS when applicable, automatic-mode duration threshold, HTTP timeout, retries/backoff, upload-size threshold, file polling deadline/interval |
| Visual request | Text/events output, timestamp mode, analysis start/end, timestamp windows and inspection windows where applicable, optional independent transcript context |
| Local processing | Uploaded file, operation timeout, explicit codec/container/bitrate for extraction or conversion; tag mapping and optional artwork for enrichment |
| Pipeline | Requested stages, settings for each selected provider, media selection for visual input, explicit transcript-context choice |
| Audio flow | Reviewed plan, required conversion settings, optional tags and source/uploaded artwork |

See [configuration](configuration.md), [request schemas](schemas.md), and each
component guide for accepted values and conditions. Automatic Gemini processing
needs known duration; agentic processing requires the full video. Timestamp labels
and inspection windows serve different purposes. The demo does not invent settings
or replacement quality when a request is invalid.

## Feature coverage

This table tracks the library capability exposed by the demo, rather than implying
that a live source or provider was verified in a demo test.

| Library capability | Demo coverage | Boundary / reference |
| --- | --- | --- |
| URL metadata inspection | Independent inspect; pipeline metadata | [Inspection](components/downloads.md#inspect-available-formats); supported public platforms only |
| Format and thumbnail enumeration | Inspection results | Unknown metadata remains unknown; image enumeration makes no thumbnail download |
| Explicit media download | Independent download; pipeline media | [Selected format](components/downloads.md#download-your-selection); no silent quality replacement |
| Audio download planning | Independent planner; reviewed audio flow | [Planner](components/downloads.md#plan-an-audio-download); ratio required, no download in planner |
| Source-thumbnail download | Independent thumbnail; audio-flow cover art | [Preferred available thumbnail](components/downloads.md#download-source-cover-art); no fixed dimensions promised |
| Supadata text and segments | Independent transcription; pipeline transcript | [Transcription](components/transcription.md); generated public-URL transcripts only |
| Gemini visual text and events | Independent uploaded video; pipeline visual | [Visual understanding](components/visual.md); processing/timing controls exposed |
| Transcript context for visuals | Independent context; pipeline context option | Context remains reference data, separate from user-facing results |
| Probe media | Independent local tool | [Probe](components/media-tools.md#measure-a-file); measured metadata |
| Extract audio | Independent local tool; audio-flow conversion for video input | [Extraction](components/media-tools.md#extract-audio-from-video); explicit codec/container/bitrate |
| Convert audio | Independent local tool; required MP3 step in fallback audio plans | [Conversion](components/media-tools.md#convert-an-audio-file); explicit supported output combination |
| Tags and cover art | Independent enrichment; optional audio-flow enrichment | [Enrichment](components/media-tools.md#write-metadata-to-a-copy); writes a copy |
| Optional all-or-nothing pipeline | Dedicated Pipeline mode | [Pipeline](components/pipeline.md); actual library orchestrator |
| Owned artifact cleanup | Session downloads, cancellation, expiry and shutdown | Demo lifecycle below; library [ownership](schemas.md#mediaartifact) stays unchanged |
| Downloader reference workflow | Inspect → review audio plan → download → required conversion → optional tags and source/uploaded cover → browser download | Uses public library services; the demo owns jobs and file serving |
| Recipe-context reference workflow | Pipeline metadata description, Supadata transcript, and Gemini event descriptions/times | Recipe generation, prompt assembly, databases, and caption/Gemini-audio fallbacks remain outside the library/demo |

Transcription intentionally uses Supadata only. There is no local-audio transcription,
Gemini transcription, alternate caption provider, or provider workaround in the demo.
If a reference requires missing library download or processing behavior, stop and
report that gap before extending the demo.

## Files, cancellation, and privacy

Uploads and pasted/uploaded cookies are written to session-owned temporary storage.
Cookie contents are never returned in results or logs. The browser cannot select an
arbitrary server file path. Local originals remain on the user's device; transforms
operate on server copies. Result URLs are scoped to their originating session.
Cookies are consumed by one submitted operation; upload or paste them again for
the download after reviewing an audio plan. No content or cookies are saved in
browser storage. An opaque HTTP-only cookie identifies the session.

The dependency view shows initial pipeline stages running in parallel and their
completion barrier before visual analysis. Elapsed times are measured; download
progress labels estimated byte totals, while other operations use indeterminate
progress. Results provide readable content, tables/timelines, JSON, and normal
browser downloads. Event timestamps remain approximate and supplied windows are
labels. Media previews depend on the browser's codec support.

Successful job artifacts are retained for 60 minutes after completion. Active use
and ongoing transfers protect files from expiry while they are being consumed.
Failed and cancelled jobs clean up owned files after their work stops; a blocking
downloader can delay cancellation and cleanup. Application shutdown cleans up owned
temporary storage. Download anything you need before expiry or restart. Browser
sessions and job history have no database or durable storage.

The application logs factual operational events and suppresses access logs in the
supplied commands. It must not log API keys, cookies, private inputs, returned
content, or cost/usage estimates. Provider errors are presented without exposing
credentials or raw private request content.

## Container and manual Render deployment

The supplied `demo/Dockerfile` contains Python 3.11, uv 0.12.10, FFmpeg/ffprobe, and
Deno 2.5.6. It installs locked `all` extras and the optional `demo` group, and runs as
a non-root user. `.dockerignore` excludes local credentials, cookies, private
references, environments, and caches. No secret value is copied into the image.
See the official [uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/)
and [Deno Docker guide](https://docs.deno.com/runtime/reference/docker/) for the image sources.

To validate locally on a machine with Docker:

```bash
docker build -f demo/Dockerfile -t video-context-demo .
docker run --rm -p 8000:10000 --env-file .env video-context-demo
```

Check `/health`, the page, and provider-free local processing. Use small inputs on
free hosting; media downloads and processing share its limited memory and CPU.

Deployment is manual; adding these files does not publish the demo. When you choose
to deploy a repository containing the files:

1. Create a Render web service with Docker runtime, repository-root build context,
   and Dockerfile path `./demo/Dockerfile`. Leave the Docker Command override blank
   to use the image command. See [Docker on Render](https://render.com/docs/docker).
2. Select the Free plan, health path `/health`, and disable automatic deploys. The
   included `render.yaml` expresses these choices with `runtime: docker`,
   `plan: free`, and `autoDeployTrigger: off`; see the
   [Blueprint reference](https://render.com/docs/blueprint-spec).
3. Add only `GEMINI_API_KEY` and/or `SUPADATA_API_KEY` in the service's Environment
   page, or choose **Add from .env** to import the private key-only file. They are
   deliberately absent from the Blueprint so neither is mandatory.
   Never put secret values in repository files. See
   [Render environment variables](https://render.com/docs/configure-environment-variables).
4. Trigger the initial deployment after reviewing these settings. The container
   binds `0.0.0.0:$PORT`, with a local container fallback of 10000, and uses one
   Uvicorn worker. This matches Render's
   [web service port requirements](https://render.com/docs/web-services#port-binding).
5. Check `/health` and the page on the assigned URL. Confirm provider availability;
   run paid checks only deliberately. Later changes require a manual deployment.

The service has no database or persistent disk. Free Render services spin down after
15 minutes without inbound traffic and can take about a minute to wake. Their local
files disappear on restart, redeploy, or spin-down, so the 60-minute demo retention
window is an upper bound within a running process, not a durability guarantee. See
[Render Free limitations](https://render.com/docs/free).

## Verification boundaries

Offline demo checks cover settings validation, selective provider availability,
public configuration coverage, pipeline composition, audio-plan review, session
isolation, artifact transfer/expiry, and failure/cancellation cleanup. The full
55-test offline suite passed on Python 3.11; the 15 focused demo tests passed on
Python 3.14. Generated media exercised real FFmpeg extraction and cover-art
enrichment while preserving caller files. Lint, type checks, strict documentation,
and the package build passed; the wheel contains no demo package.

Browser checks covered desktop/mobile layout, blank and conditional settings,
keyboard help, uploads, a real probe/extraction/download flow, session reset, and
fixture-backed audio-plan review, estimated byte progress, cancellation, thumbnail
previews, and transcript timelines with literal text rendering. Source-workflow
browser fixtures made no provider calls. Run repeatable offline checks with the
commands in [development](development.md#maintain-the-browser-demo).
Existing [provider validation](provider-validation.md) records library checks and
remaining source/provider gaps; it is not evidence of a live demo deployment.

Render documentation and the Python 3.11/Deno 2.5.6 image manifests were checked on
2026-09-06; uv's official Docker guide documents the 0.12.10 image tag. Container
build/run and Render deployment were not verified in the implementation environment
because Docker was unavailable. No paid provider validation is implied by offline
checks or by a successful health response.
