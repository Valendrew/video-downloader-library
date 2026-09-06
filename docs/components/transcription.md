# Transcribe a public video

Use Supadata to turn a public video URL into text or timed speech segments.
Local audio files are not accepted by this adapter. You do not need to download media.

## Before you start

Install the `supadata` extra and prepare `SupadataSettings` using
[the provider guide](../providers/supadata.md#configure). The example below uses those
settings and makes a provider request when awaited. For a runnable script including
settings, see [your first request](../quickstart.md).

## Request timed segments

```python
from video_context_pipeline import SupadataSettings, TranscriptRequest
from video_context_pipeline.providers.supadata import SupadataProvider

async def transcribe(url: str, settings: SupadataSettings) -> None:
    provider = SupadataProvider()
    result = await provider.transcribe(
        url,
        TranscriptRequest(format="transcript_segments", settings=settings),
    )
    for segment in result.data:
        print(segment.start_seconds, segment.end_seconds, segment.text)
```

Times are seconds on the source timeline. `end_seconds` may be `None` if unavailable.
An empty successful response has no segments and `result.status == "empty"`.

## Request readable text

Change the request format to `transcript_text` and read `result.data` as a string.
The adapter formats this text from the same canonical segment response; changing the
output format does not select a different transcription mode.

## Behavior and limits

The adapter always requests Supadata's generated transcript mode, without a language
override or provider fallback. Returned language information is available in
`result.language`. Timeouts, retries, and queued-job polling are explicit settings.

`request_timeout_seconds` bounds each HTTP attempt, including the initial generation
request. Retries can make the full operation longer than that value.
`job_timeout_seconds` starts after a job ID is received and bounds its polling;
increasing it cannot fix a timeout in the initial request. Operational records
distinguish the initial `request` phase from `poll`, and report changes to
`queued`, `active`, or terminal job status. A completed job without content is an
invalid response, not a reason to keep polling until the deadline.

See [Supadata](../providers/supadata.md) for upstream docs and validation limits,
[schemas](../schemas.md#transcriptrequest) for the data contract, or
[Pipeline](pipeline.md) to combine transcription with another output.
