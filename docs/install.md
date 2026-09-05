# Install

Video Context Pipeline requires Python 3.11 or newer. From a local checkout, create a
locked environment with the provider extras you need:

```bash
uv sync --locked --extra gemini --group dev
# or: --extra supadata, --extra download, --extra providers, or --extra all
```

`providers` and `all` include both HTTP providers and the downloader.

GitHub release `v0.1.0` is prepared but is not published. After it is deliberately
published, download its pinned wheel and `SHA256SUMS`, then verify the artifact:

```bash
curl -LO https://github.com/Valendrew/video-downloader-library/releases/download/v0.1.0/SHA256SUMS
curl -LO https://github.com/Valendrew/video-downloader-library/releases/download/v0.1.0/video_context_pipeline-0.1.0-py3-none-any.whl
sha256sum --ignore-missing -c SHA256SUMS
uv add 'video-context-pipeline[gemini] @ https://github.com/Valendrew/video-downloader-library/releases/download/v0.1.0/video_context_pipeline-0.1.0-py3-none-any.whl'
```

The equivalent pip command is
`pip install 'video-context-pipeline[gemini] @ https://github.com/Valendrew/video-downloader-library/releases/download/v0.1.0/video_context_pipeline-0.1.0-py3-none-any.whl'`.
The future `v0.1.0` Git tag is also an optional source-installation pin.

The downloader requires `yt-dlp` and a configured JavaScript runtime mapping for
hosts that need one. Install a supported runtime such as Node.js or Deno on the host.
Local media operations require separately installed `ffmpeg` and `ffprobe`; neither
tool is bundled in the wheel. Their formats and codecs depend on their installed
builds.

Build the documentation from the checkout with:

```bash
uv sync --locked --extra all --group dev
uv run mkdocs build --strict
```
