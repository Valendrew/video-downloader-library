# Local media tools

`FFmpegMediaTools(ffmpeg_path=..., ffprobe_path=..., timeout_seconds=..., logger=None)`
uses caller-selected executable paths and a positive per-operation timeout. It works on
local `MediaArtifact` files:

```python
metadata = await tools.probe(Path("input.mp4"))
audio = await tools.extract_audio(
    source, destination=Path("audio.mp3"), codec="mp3", container="mp3", bitrate_kbps=192,
)
```

`probe()` reports measured duration, media type, codecs, bitrate, and size.
`extract_audio()` requires a video artifact; `convert_audio()` requires an audio
artifact. Both require a new destination and explicit codec, container, and positive
bitrate. Valid pairs are MP3/MP3, AAC/M4A, and AAC/MP4.

`enrich_metadata(source, destination=..., metadata=..., thumbnail=None)` makes a new
MP3, M4A, or MP4 copy with string metadata and an optional existing thumbnail. None of
these methods overwrite a source or an existing destination. `ffmpeg` and `ffprobe`
must be installed separately.

