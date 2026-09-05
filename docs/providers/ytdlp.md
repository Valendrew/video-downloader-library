# yt-dlp

The yt-dlp adapter inspects available formats and downloads your selected media.
The library restricts input to supported public YouTube, Instagram, and TikTok URLs,
even though upstream yt-dlp supports many more sites.

## Install

```bash
uv sync --locked --extra download
```

The extra pins yt-dlp and includes its default dependencies. Install a JavaScript
runtime separately when the source requires it.

## Configure a runtime and storage

```python
from video_context_pipeline import MediaSettings
from video_context_pipeline.providers.ytdlp import YtDlpMediaProvider

settings = MediaSettings(
    request_timeout_seconds=60.0,
    cookie_file=None,
    output_directory=None,
)
provider = YtDlpMediaProvider(
    js_runtimes={"node": {"path": "/usr/bin/node"}},
)
```

Replace `/usr/bin/node` with your installed executable path. For Deno, use a `deno`
key and its executable path. The runtime mapping is an explicit constructor argument;
the adapter does not discover your preferred runtime.

Use a `Path` for `cookie_file` when your source needs cookies, and an optional
`output_directory` for storage. Each download has an owned directory and artifact;
choosing a storage location does not make downloaded files caller-owned.

The provider also accepts optional `downloader_factory`, `logger`, and `progress`
arguments. `progress` receives `DownloadProgress` values for application progress displays.

## Inspect before selecting

[The download guide](../components/downloads.md) explains inspection, format selection,
and audio planning. Format identifiers depend on the source: do not assume an example
ID exists for every URL. The adapter does not silently pick another format if your
selection fails.

## Use metadata in a pipeline

```python
from video_context_pipeline.providers.ytdlp import YtDlpMetadataProvider

metadata_provider = YtDlpMetadataProvider(
    settings=settings,
    media_provider=provider,
)
```

This adapter exposes inspection data as a named metadata output. It uses the same
runtime and settings as the downloader.

## Explore the original documentation

- [yt-dlp README](https://github.com/yt-dlp/yt-dlp#readme): options, formats, embedding, and authentication.
- [JavaScript runtime setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS): runtime requirements and installation.
- [yt-dlp FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ): extraction and download troubleshooting.

Source availability can depend on login, cookies, and extractor behavior. See
[recorded checks](../provider-validation.md#download-and-local-media-tools) for the
platforms and operations tested by this project.
