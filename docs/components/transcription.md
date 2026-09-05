# Transcription

`SupadataProvider(client=None, logger=None)` transcribes a supported **public video
URL**. It does not accept a local audio file. Use the independent
[Local media tools](media-tools.md) only to prepare local audio; they do not turn it
into Supadata input.

```python
result = await provider.transcribe(
    url,
    TranscriptRequest(format="transcript_segments", settings=supadata_settings),
)
```

Choose `transcript_segments` for canonical `TranscriptSegment` values, or
`transcript_text` for readable text formatted from those segments. The request uses
Supadata's generated transcript mode only. It has no language parameter, automatic
mode, or fallback provider. The result may be `empty` when the provider returns no
segments.

Set the request, job, polling, retry, and delay values in `SupadataSettings`; their
required arguments are documented in [configuration](../configuration.md).

