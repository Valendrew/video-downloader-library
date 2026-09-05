# Download and inspect media

Inspect a supported public video URL to discover available formats. Then choose the
format your application needs and download it. Format selection is explicit; the
adapter does not silently substitute a different quality.

## Before you start

Install the `download` extra and configure a JavaScript runtime using
[the yt-dlp guide](../providers/ytdlp.md). The examples below run in an async function,
with `provider`, `settings`, and a supported `url` supplied by your application.

## Inspect available formats

```python
inspection = await provider.inspect_media(url, settings)
print(inspection.title, inspection.duration_seconds)
for candidate in inspection.formats:
    print(candidate.format_id, candidate.extension, candidate.video_codec, candidate.audio_codec)
```

`MediaInspection` contains `formats`, `duration_seconds`, `title`, and `description`.
Each `MediaFormat` describes a format ID, extension, codecs, bitrates, and known or
estimated size. Unknown values remain `None`; an estimate is not an exact size.

## Download your selection

Pass a format ID chosen from the inspection. Here `selected_format_id` is the string
your application or user selected; its value depends on the URL.

```python
from video_context_pipeline import MediaRequest

download = await provider.download(
    url,
    MediaRequest(settings=settings, selected_format_id=selected_format_id),
)
with download.data as artifact:
    print(artifact.path, artifact.media_type)
    # Consume the file here, before the context manager removes it.
```

The result is a `ProviderOutput` with `format="media"`. Its `data` is an owned
`MediaArtifact`. Cleanup removes the downloaded file and its owned temporary directory.
Caller-owned source paths are preserved.

## Plan an audio download

```python
from video_context_pipeline.providers.ytdlp import plan_audio_download

plan = plan_audio_download(inspection, compatible_bitrate_ratio=0.80)
```

The positive ratio is your application's quality policy, not a library default.
The plan identifies a selected format and whether MP3 conversion is required.
A directly compatible choice must be audio-only MP3/M4P or AAC in MP4/M4A and meet the
bitrate ratio. Otherwise the plan selects `bestaudio/best` and requires separate conversion.
The planner does not download or convert anything.

Use [local media tools](media-tools.md) for that explicit conversion step. Inspect the
plan's `selected_format_id` and `requires_mp3_conversion` before choosing the next action.

## Return metadata through Pipeline

`YtDlpMetadataProvider` adapts inspection into a metadata output containing title,
description, duration, and formats. Configure it with the same settings and media
provider, then inject it as `metadata_provider` in [Pipeline](pipeline.md).

[yt-dlp setup and upstream documentation →](../providers/ytdlp.md)
