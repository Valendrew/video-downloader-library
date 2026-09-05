# Work with local media

`FFmpegMediaTools` probes files, extracts or converts audio, and writes tagged copies.
It works independently of the pipeline and needs no provider credentials.

## Configure executables

Install FFmpeg and ffprobe separately. Replace these example paths with your installed
executables; the timeout is an explicit per-operation limit.

```python
from pathlib import Path
from video_context_pipeline.media import FFmpegMediaTools

tools = FFmpegMediaTools(
    ffmpeg_path=Path("/usr/bin/ffmpeg"),
    ffprobe_path=Path("/usr/bin/ffprobe"),
    timeout_seconds=60.0,
)
```

The constructor also accepts an optional standard Python `logger`. Methods below are
asynchronous; run them inside your application's async function.

## Measure a file

```python
metadata = await tools.probe(Path("input.mp4"))
print(metadata.duration_seconds, metadata.codecs, metadata.size_bytes)
```

The result is `MediaMetadata`, imported from `video_context_pipeline.media`.
It reports measured duration, media type, codecs, bitrate in bits per second, and file
size in bytes. Missing duration or bitrate remains `None`.

## Extract audio from video

```python
from video_context_pipeline import MediaArtifact

source = MediaArtifact(path=Path("input.mp4"), media_type="video/mp4", owned=False)
audio = await tools.extract_audio(
    source,
    destination=Path("audio.mp3"),
    codec="mp3",
    container="mp3",
    bitrate_kbps=192,
)
```

The source must have a `video/` media type. The destination must be new; an existing
file is never overwritten. The returned value is a `MediaArtifact` describing the
new audio file. Your source stays intact.

## Convert an audio file

Use `convert_audio()` with the same destination, codec, container, and bitrate
arguments, but supply an artifact with an `audio/` media type.

| Codec | Container | Typical destination |
| --- | --- | --- |
| `mp3` | `mp3` | `audio.mp3` |
| `aac` | `m4a` | `audio.m4a` |
| `aac` | `mp4` | `audio.mp4` |

All choices are explicit; `bitrate_kbps` must be a positive integer. Actual codec
availability depends on your FFmpeg build.

## Write metadata to a copy

```python
tagged = await tools.enrich_metadata(
    audio,
    destination=Path("tagged.mp3"),
    metadata={"title": "My recording", "artist": "Example"},
    thumbnail=None,
)
```

Metadata keys must be non-empty strings and values must be strings. Supply an existing
thumbnail `Path` to embed cover art. Supported source containers are MP3, M4A, and MP4.
This creates a new file, preserving the source and rejecting an existing destination.
To use the video's original artwork, first call
[`YtDlpMediaProvider.download_thumbnail()`](downloads.md#download-source-cover-art)
and pass the returned artifact's `path` while its context manager is active. Network
retrieval stays in the provider; local enrichment also works with caller-owned images.
Probing audio with attached cover art reports an audio media type.

## File ownership

Successful transforms write to the caller-named destination and return library-owned
artifacts. Calling their `cleanup()` removes those newly created outputs. Consume or
copy them before cleanup; the original caller-owned source is preserved. Temporary files created
for an operation are cleaned up on failure. See [artifact ownership](../schemas.md#mediaartifact).
