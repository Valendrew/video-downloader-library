# Errors and logging

## Choose what to catch

All library exceptions derive from `VideoContextPipelineError`.

| Exception | Meaning | Typical response |
| --- | --- | --- |
| `ConfigurationError` | Missing or invalid settings or request choices. | Correct configuration before retrying. |
| `ValidationError` | Input or returned data violates a public contract. | Check the URL, file, interval, or response shape. |
| `ProviderError` | An independent provider operation failed. | Inspect `http_status` when available; apply your application's error policy. |
| `PipelineError` | A coordinated run failed. | Treat the run as failed; there is no partial result. |

For a pipeline call inside an async function:

```python
from video_context_pipeline import VideoContextPipelineError

try:
    result = await pipeline.run(url, request)
except VideoContextPipelineError as error:
    # Send a suitable error to your application's UI or job state.
    print(type(error).__name__)
else:
    with result:
        print(tuple(result.outputs))
```

A pipeline provider failure can be wrapped in `PipelineError`; do not assume that
exception exposes the provider's `http_status`. Cancellation propagates separately
as `asyncio.CancelledError` after cleanup.

## Failure and cleanup

Pipeline runs are strict: when multiple requested stages run together, all requested
stages must succeed before results are returned. A failure or cancellation cleans up
completed library-owned media and produces no partial pipeline result. Independent
components can be called separately when partial work is useful to the application.

## Configure logging

The package does not configure logging. Standard loggers still emit normally under an
application's logging policy; Python's default `lastResort` handler may show warnings
or errors. Call `configure_json_logging()` when the application wants a JSON handler:

```python
from video_context_pipeline.logging import configure_json_logging

logger = configure_json_logging()
logger.info("application configured")
```

The helper enables INFO logging for its handler, adds an actual UTC timestamp, and
chooses ERROR for failed records, WARNING for retrying records, and INFO otherwise.
Lifecycle records include a correlated request ID and allowlisted factual fields.
Terminal provider records include the HTTP status when available, otherwise `null`.

## What is logged

Logs intentionally exclude raw media, transcript or visual content, API keys, URLs,
raw error bodies, and cost or dollar estimates. Provider-reported usage can be
returned in result data, but no cost estimate is calculated.

Timeouts, retries, and polling deadlines are caller-selected operational limits. They
can fail a download or provider operation; they are not a promise of completion.

## Release returned media

Use `cleanup()` to release returned owned media, or make it automatic with a context
manager:

```python
with result:
    use(result.outputs)
# result.cleanup() has run for owned media
```
