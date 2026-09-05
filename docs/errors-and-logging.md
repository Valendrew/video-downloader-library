# Errors and logging

Invalid local input and configuration raise `ConfigurationError` or `ValidationError`.
Provider failures raise `ProviderError`; when known it exposes an `http_status`.
`PipelineError` reports a failed coordinated run. All derive from
`VideoContextPipelineError`.

Pipeline runs are strict: when multiple requested stages run together, all requested
stages must succeed before results are returned. A failure or cancellation cleans up
completed library-owned media and produces no partial pipeline result. Independent
components can be called separately when partial work is useful to the application.

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

Logs intentionally exclude raw media, transcript or visual content, API keys, URLs,
raw error bodies, and cost or dollar estimates. Provider-reported usage can be
returned in result data, but no cost estimate is calculated.

Timeouts, retries, and polling deadlines are caller-selected operational limits. They
can fail a download or provider operation; they are not a promise of completion.

Use `cleanup()` to release returned owned media, or make it automatic with a context
manager:

```python
with result:
    use(result.outputs)
# result.cleanup() has run for owned media
```
