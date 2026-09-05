# Video Context Pipeline

Turn public videos into metadata, transcripts, downloaded media, and visual observations.
A typed, asynchronous Python library with independent components and an optional pipeline.

- **Inspect and download** public YouTube, Instagram, and TikTok URLs with yt-dlp.
- **Transcribe** a public video URL with Supadata, as text or timed segments.
- **Analyze visuals** in a local video with Gemini, as prose or structured events.
- **Process local media** with FFmpeg: probe, extract audio, convert, and tag a copy.

The pipeline returns every requested output together. If a stage fails, it cancels
pending work where possible, cleans up owned media, and raises an error.

## Installation

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From a checkout:

```bash
git clone https://github.com/Valendrew/video-downloader-library.git
cd video-downloader-library
uv sync --locked --extra all
```

Choose `gemini`, `supadata`, or `download` instead of `all` to install only the
provider dependencies you need. FFmpeg, ffprobe, and a JavaScript runtime are separate
host tools. See the [installation guide](docs/install.md) for application integration
and tool setup.

## First steps

Start with an offline configuration example:

```bash
uv run python examples/offline_configuration.py
```

Then follow [your first request](docs/quickstart.md) for a complete transcription
example. Settings are explicit; the optional environment loader reads only selected
services and never opens `.env` files.

## Documentation

Browse the [documentation site](https://valendrew.github.io/video-downloader-library/)
or read the guides in this checkout:

| Learn about | Guide |
| --- | --- |
| Credentials, timeouts, and service settings | [Configuration](docs/configuration.md) |
| Gemini, Supadata, and yt-dlp setup | [Providers](docs/providers/index.md) |
| Combining components | [Pipeline](docs/components/pipeline.md) |
| Request fields and returned data | [Schemas and requests](docs/schemas.md) |
| Failures and file cleanup | [Errors and logging](docs/errors-and-logging.md) |

## Development

```bash
uv sync --locked --extra all --group dev
uv run python -m unittest discover -s tests
uv run mkdocs serve
```

See [development](docs/development.md) for checks and builds, and
[documentation development](docs/documentation.md) for local previews.

## License

MIT. Optional dependencies and host tools retain their own licenses.
See [dependencies and provenance](docs/dependencies.md).
