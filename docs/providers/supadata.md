# Supadata

Supadata generates transcripts from public video URLs. This adapter returns either
readable transcript text or typed segments with start and end times. It accepts a URL,
so you do not need to download or extract audio first.

## Install

```bash
uv sync --locked --extra supadata
```

This command is for the library checkout. For application installs, see
[installation](../install.md#add-the-library-to-your-application).

## Configure

```python
import os
from video_context_pipeline import SupadataSettings

settings = SupadataSettings(
    api_key=os.environ["SUPADATA_API_KEY"],
    request_timeout_seconds=30.0,
    job_timeout_seconds=120.0,
    poll_interval_seconds=2.0,
    max_retries=2,
    retry_delay_seconds=1.0,
)
```

These values are explicit example choices, not library defaults. The request timeout
bounds an HTTP request. The job timeout bounds waiting for a queued transcript;
polling controls how often job results are checked. Retries and delay control transient
request failures. All durations must be positive; retries may be zero.

Alternatively, use the [Supadata environment loader](../configuration.md#supadata-environment).

## Construct the provider

```python
from video_context_pipeline.providers.supadata import SupadataProvider

provider = SupadataProvider()
```

The constructor also accepts optional `client` and `logger` keyword arguments for
HTTP client injection and application logging. Credentials belong in the request's
settings. See [transcription](../components/transcription.md) for a complete call.

## Adapter behavior

The adapter requests generated segments using `mode=generate` and `text=false`, with
no language override. It converts provider milliseconds to public seconds and formats
text from the same segments. There is no fallback to another provider or mode.
An empty segment response returns `status="empty"`.

Queued jobs are polled until completion or the configured deadline. Their handling is
tested offline; live queued-job behavior and successful TikTok generation remain
[unverified](../provider-validation.md#supadata).

## Explore the original documentation

- [Transcript endpoint](https://docs.supadata.ai/api-reference/endpoint/transcript/transcript): upstream request parameters and response examples.
- [Job results](https://docs.supadata.ai/api-reference/endpoint/transcript/transcript-get): asynchronous transcript results.
- [Supadata documentation](https://docs.supadata.ai/): authentication and other service capabilities.
