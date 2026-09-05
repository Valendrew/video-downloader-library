# Your first request

Generate a transcript from a public video URL, then read its text. This example uses
Supadata alone; it needs neither a downloader nor a pipeline.

## 1. Install the provider

From the repository checkout:

```bash
uv sync --locked --extra supadata
```

## 2. Supply your key

Make `SUPADATA_API_KEY` available in your process environment through your shell or
secret manager. The library does not load `.env` files automatically.

## 3. Create and run the script

Save this as `transcribe.py` in the checkout. Running it makes a real Supadata request.
The timeout and retry values are explicit choices for this example.

```python
import asyncio
import os

from video_context_pipeline import SupadataSettings, TranscriptRequest
from video_context_pipeline.providers.supadata import SupadataProvider

async def main() -> None:
    settings = SupadataSettings(
        api_key=os.environ["SUPADATA_API_KEY"],
        request_timeout_seconds=30.0,
        job_timeout_seconds=120.0,
        poll_interval_seconds=2.0,
        max_retries=2,
        retry_delay_seconds=1.0,
    )
    request = TranscriptRequest(format="transcript_text", settings=settings)
    result = await SupadataProvider().transcribe(
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        request,
    )
    if result.status == "empty":
        print("No transcript content was returned.")
    else:
        print(result.data)

if __name__ == "__main__":
    asyncio.run(main())
```

```bash
uv run python transcribe.py
```

In an application that already runs an event loop, await your async function instead
of calling `asyncio.run()` inside that loop.

## 4. Understand the result

`result` is a `ProviderOutput`. Its `data` is text because the request selected
`transcript_text`; `status` distinguishes content from an empty successful response.
`language` may contain the provider's reported language. Failures raise an exception;
see [errors and logging](errors-and-logging.md).

For segment timing, request `transcript_segments` and iterate over `result.data`.
The [transcription guide](components/transcription.md) shows how. To combine outputs,
continue with the [pipeline guide](components/pipeline.md).
