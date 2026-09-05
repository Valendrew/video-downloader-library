# Download and metadata

`YtDlpMediaProvider(js_runtimes=..., downloader_factory=None, logger=None,
progress=None)` inspects and downloads from a supported public URL. `js_runtimes` is
an explicit mapping of supported JavaScript runtimes; configure Node.js or Deno on
hosts that need one.

```python
inspection = await provider.inspect_media(url, media_settings)
download = await provider.download(
    url,
    MediaRequest(settings=media_settings, selected_format_id="134"),
)
```

Inspection returns `MediaInspection(formats, duration_seconds, title, description)`.
Each `MediaFormat` identifies its format ID, extension, audio/video codecs, audio and
total bitrates, and exact or estimated size. Choose `selected_format_id` yourself;
the downloader does not silently select or convert a different format.

`plan_audio_download(inspection, compatible_bitrate_ratio=...)` returns an explicit
source selection and whether separate MP3 conversion is required. A direct source is
accepted only when it is audio-only MP3/M4P or AAC in MP4/M4A and meets the caller's
positive bitrate ratio. Otherwise the plan is `bestaudio/best` plus required conversion.

`YtDlpMetadataProvider(settings=..., media_provider=...)` adapts an inspection to
pipeline metadata (title, description, duration, and formats). For local conversion
or probing after download, use [Local media tools](media-tools.md).

