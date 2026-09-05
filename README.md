# Video Context Pipeline

Typed asynchronous building blocks for inspecting public videos, downloading media,
transcribing a public video URL, and understanding visible video content. Components
work independently. `Pipeline` runs requested stages together and returns output only
when every requested stage succeeds.

From a local checkout, install the locked development environment and the extras you
need:

```bash
uv sync --locked --extra all --group dev
```

Release `v0.1.0` is prepared but unavailable until it is deliberately published. Once
published, verify its pinned GitHub release artifact before installing it:

```bash
curl -LO https://github.com/Valendrew/video-downloader-library/releases/download/v0.1.0/SHA256SUMS
curl -LO https://github.com/Valendrew/video-downloader-library/releases/download/v0.1.0/video_context_pipeline-0.1.0-py3-none-any.whl
sha256sum -c SHA256SUMS
uv add 'video-context-pipeline[gemini] @ https://github.com/Valendrew/video-downloader-library/releases/download/v0.1.0/video_context_pipeline-0.1.0-py3-none-any.whl'
```

The equivalent pip command is
`pip install 'video-context-pipeline[gemini] @ https://github.com/Valendrew/video-downloader-library/releases/download/v0.1.0/video_context_pipeline-0.1.0-py3-none-any.whl'`.
An optional source installation can use the future `v0.1.0` Git tag.

The library accepts public HTTP(S) URLs on YouTube, Instagram, and TikTok, including
their subdomains. It does not accept local or internal URLs. Downloaded `MediaArtifact`
files are local artifacts; an owned artifact may be removed by `cleanup()`, while a
caller-owned path is never removed.

See the [documentation](https://valendrew.github.io/video-downloader-library/) for
installation, configuration, schemas, components, and provider-validation limits.
That Pages site is prepared for an explicit deployment and may not yet be enabled.

## Quick start

The example constructs configuration only. It deliberately makes no provider call.

```bash
uv run python examples/offline_configuration.py
```

The [examples](examples/) construct configuration and requests without making provider
calls. Copy `.env.example` to a private environment-management location and supply
real keys only when you intentionally make provider calls; the library does not read
`.env` files.

## License and dependencies

This project is MIT-licensed. Provider extras and installed tools keep their own
licenses. See [dependencies and code provenance](docs/dependencies.md).
