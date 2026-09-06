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

`MediaInspection` contains `formats`, `duration_seconds`, `title`, `description`,
and `thumbnails`. Each `MediaThumbnail` exposes `url`, `thumbnail_id`, `width`, and
`height`; unknown fields remain `None`. The tuple preserves provider order and is
empty when no usable HTTP(S) thumbnail URLs are reported. A top-level thumbnail URL
is included if absent from the list. Inspection does not download images.
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

Missing codec metadata does not mean an audio-only source. An MP4 whose video codec
is unknown uses the container's `video/mp4` type; an explicit `vcodec="none"`
identifies audio-only MP4. Some Instagram downloads omit both codecs and duration.
Use the independent [probe service](media-tools.md#measure-a-file) when measured
stream types or duration are needed; the downloader does not invent a duration.

## Download source cover art

```python
cover = await provider.download_thumbnail(url, settings)
with cover.data as thumbnail:
    tagged = await tools.enrich_metadata(
        audio,
        destination=Path("tagged.mp3"),
        metadata={"title": inspection.title or ""},
        thumbnail=thumbnail.path,
    )
```

Here `audio` is a local MP3 artifact, `tools` is configured as in
[local media tools](media-tools.md), and `Path` comes from `pathlib`.
`download_thumbnail()` fetches source artwork independently of media download and
returns `ProviderOutput[MediaArtifact]` with `format="media"` and an `image/*` media
type inferred from the downloaded extension. It uses the same explicit timeout,
cookies, output directory, and runtime configuration as media operations.

The operation uses yt-dlp's preferred available thumbnail policy: yt-dlp tries its
preferred candidate first and may try another if that image is unavailable. It does
not promise particular dimensions or an image encoding. It downloads no audio or
video and does not invoke FFmpeg. Missing, empty, or unrecognized image output raises
`ProviderError`; artwork is never silently omitted from a requested operation.
FFmpeg validates/decodes the image when embedding it, converting cover art to JPEG.

Keep the image alive until enrichment finishes. Its context manager removes the
owned image and temporary directory. Failure, timeout, and cancellation clean up
operation-owned files; cancellation waits for the blocking downloader to finish,
which can extend beyond the configured timeout. Normal `download()` still returns
only the selected media file. See `examples/source_thumbnail.py` for composition
with cleanup when either download or enrichment fails.

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
description, duration, formats, and thumbnail dictionaries. Configure it with the same settings and media
provider, then inject it as `metadata_provider` in [Pipeline](pipeline.md).

[yt-dlp setup and upstream documentation →](../providers/ytdlp.md)
