# Combine outputs with Pipeline

`Pipeline` coordinates providers for one public video URL. Request the outputs you
need; the run returns them together after every requested stage succeeds.

## Start with metadata and a transcript

Install the `supadata` and `download` extras. Prepare
[Supadata settings](../providers/supadata.md#configure) and your installed JavaScript
runtime path. This function constructs the download settings, providers, and request:

```python
from video_context_pipeline import (
    MediaSettings,
    Pipeline,
    PipelineRequest,
    PipelineResult,
    SupadataSettings,
    TranscriptRequest,
)
from video_context_pipeline.providers.supadata import SupadataProvider
from video_context_pipeline.providers.ytdlp import (
    YtDlpMediaProvider,
    YtDlpMetadataProvider,
)

async def collect(
    url: str,
    supadata_settings: SupadataSettings,
    node_path: str,
) -> PipelineResult:
    media_settings = MediaSettings(request_timeout_seconds=60.0)
    downloader = YtDlpMediaProvider(js_runtimes={"node": {"path": node_path}})
    pipeline = Pipeline(
        metadata_provider=YtDlpMetadataProvider(
            settings=media_settings,
            media_provider=downloader,
        ),
        transcript_provider=SupadataProvider(),
    )
    request = PipelineRequest(
        metadata=True,
        transcript=TranscriptRequest(
            format="transcript_text",
            settings=supadata_settings,
        ),
    )
    return await pipeline.run(url, request)
```

Await `collect(url, supadata_settings, node_path)` from your application to make real
provider calls. Read `result.output("metadata").data` and
`result.output("transcript").data` from the returned result. This request inspects
metadata and generates a transcript without downloading a media artifact.

## Match requested stages to providers

| Requested field | Required provider(s) |
| --- | --- |
| `metadata=True` | `metadata_provider` |
| `transcript` | `transcript_provider` |
| `media` | `media_provider` |
| `visual` | `visual_provider` and `media_provider` |

All constructor provider arguments are optional. A run validates its URL and required
providers before provider side effects. Metadata, transcript, and download work can
run concurrently. Visual analysis runs after those stages complete.

## Add visual analysis

Install `gemini`, configure [Gemini settings](../providers/gemini.md), and inspect the
source to select a video format. Given `downloader`, `media_settings`,
`gemini_settings`, and your chosen `selected_format_id`:

```python
from video_context_pipeline import MediaRequest, VisualRequest
from video_context_pipeline.providers.gemini import GeminiProvider

pipeline = Pipeline(media_provider=downloader, visual_provider=GeminiProvider())
request = PipelineRequest(
    visual=VisualRequest(
        format="video_events",
        settings=gemini_settings,
        timestamp_mode="none",
    ),
    visual_media=MediaRequest(
        settings=media_settings,
        selected_format_id=selected_format_id,
    ),
)
result = await pipeline.run(url, request)
events = result.output("visual").data
```

Use `visual_media` for an internal download: the pipeline removes it after successful
analysis and returns only `visual`. Use `media` instead to return the downloaded file
as well. Automatic Gemini processing needs known media duration; choose the processing
mode explicitly for sources where duration may be unavailable.

## Include transcript context

Add both a transcript and visual request, inject both providers, and set
`include_transcript_context=True`. The pipeline converts the transcript into independent
reference text for the visual provider. Gemini still describes visible observations.
The default is `False`, so requesting both outputs does not couple them automatically.

## Manage returned files

A result that contains requested media owns those downloaded files. Consume them in a
context manager or call `result.cleanup()` when finished:

```python
with await pipeline.run(url, request) as result:
    # Read or copy any returned media before leaving this block.
    print(tuple(result.outputs))
```

If a requested stage fails, pending work is cancelled where possible and completed
owned media is cleaned up. No partial result is returned. Cancellation is propagated
after cleanup. Call components independently if your application needs partial work.

[Request fields and result access →](../schemas.md#pipelinerequest)

[Failure handling and logging →](../errors-and-logging.md)
