# Pipeline

`Pipeline` coordinates injected providers over one supported public video URL:

```python
from video_context_pipeline import Pipeline
from video_context_pipeline.providers.gemini import GeminiProvider
from video_context_pipeline.providers.supadata import SupadataProvider
from video_context_pipeline.providers.ytdlp import (
    YtDlpMediaProvider, YtDlpMetadataProvider,
)

async def collect(url, request, media_settings, node_path):
    downloader = YtDlpMediaProvider(js_runtimes={"node": {"path": node_path}})
    pipeline = Pipeline(
        metadata_provider=YtDlpMetadataProvider(
            settings=media_settings, media_provider=downloader,
        ),
        transcript_provider=SupadataProvider(),
        media_provider=downloader,
        visual_provider=GeminiProvider(),
    )
    return await pipeline.run(url, request)
```

Supply the explicit settings and request shown in [configuration](../configuration.md)
and [schemas](../schemas.md), and the installed Node executable path. This function
makes real provider calls when awaited. The returned result owns any requested media;
use it as a context manager or call `cleanup()` when finished. Creating a provider
object alone does not require credentials for an unused provider.

It checks the URL and every required provider before provider side effects. Requested
metadata, transcript, and media can run concurrently. A visual request needs a media
provider plus a visual provider; pass `visual_media` for a private, internal download
or `media` when the caller also wants that artifact returned. A pipeline visual request
cannot infer a format selection.

Pass `include_transcript_context=True` only with both transcript and visual requests.
The Gemini visual adapter may use that transcript as independent reference context,
while its visible observations remain visual-only.

See [schemas](../schemas.md) for `PipelineRequest` and ownership, [downloads](downloads.md)
for format selection, [transcription](transcription.md) for URL transcription, and
[visual understanding](visual.md) for visual settings.

