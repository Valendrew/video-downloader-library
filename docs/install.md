# Installation

Use Python **3.11 or newer** and [install uv](https://docs.astral.sh/uv/getting-started/installation/).
The base package has no runtime dependencies. Install extras for the components you use.

## Work from a checkout

```bash
git clone https://github.com/Valendrew/video-downloader-library.git
cd video-downloader-library
uv sync --locked --extra all
```

This installs the local library and all provider extras into `.venv`. To select one
service, replace `all` with an extra from the table below.

## Add the library to your application

From your application's uv project, add an editable path to your local checkout:

```bash
uv add --editable '/absolute/path/to/video-downloader-library[supadata]'
```

Replace the path with your checkout location and choose the extra you need. An editable
installation uses your local source changes immediately. The distribution is named
`video-context-pipeline`; Python imports use `video_context_pipeline`.

## Choose dependencies

| Extra | Installs | Use it for |
| --- | --- | --- |
| No extra | Base library only | Types, configuration, and your own provider implementations |
| `supadata` | HTTPX | Public URL transcription |
| `gemini` | HTTPX | Local video understanding |
| `download` | yt-dlp with its default extras | Metadata and media downloads |
| `providers` or `all` | All of the above | Combined workflows |

For example, from the library checkout:

```bash
uv sync --locked --extra supadata --extra download
```

See [dependencies and licenses](dependencies.md) for provenance and transitive dependencies.

## Install host tools

Python extras do not install these executables:

| Tool | Needed by | Configuration |
| --- | --- | --- |
| FFmpeg and ffprobe | Local probing, audio conversion, and metadata enrichment | Explicit executable paths in `FFmpegMediaTools` |
| A supported JavaScript runtime | yt-dlp extraction on hosts that require it | Explicit `js_runtimes` mapping |

Install [FFmpeg](https://ffmpeg.org/download.html) and consult
[yt-dlp's runtime setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS).
Check the executables you plan to use:

```bash
ffmpeg -version
ffprobe -version
node --version
# If using Deno instead:
deno --version
```

Use the actual installed paths in your application. See [yt-dlp setup](providers/ytdlp.md)
and [local media tools](components/media-tools.md) for constructors.

## Verify the Python environment

```bash
uv run python examples/offline_configuration.py
```

This constructs settings with fake credentials and makes no provider requests.
Continue with [your first request](quickstart.md).

## Development and docs

[Development](development.md) covers linting, tests, and package builds.
[Documentation](documentation.md) covers the live preview and strict site build.
