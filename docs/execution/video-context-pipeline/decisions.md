# Shared implementation decisions

## Explicit visual download selection

Decision: keep `visual_media` on the pipeline request, separate from standalone visual settings.
Evidence: video understanding accepts an existing artifact; downloader settings would be unrelated in that call.
Alternative: require download parameters on every visual request.
Impact: standalone components stay focused, while pipeline downloads still require an explicit format.

## Useful console logging

Decision: explicit JSON logging setup enables INFO, avoids duplicate handlers and disables duplicate propagation. Allowlisted fields include actual request settings, response status, output counts and byte progress. Pipeline logs elapsed duration, preserves supplied correlation and reports cleanup errors.
Evidence: a helper that only attached a handler would leave INFO hidden under Python's default WARNING level, preventing hosting-platform inspection.
Alternative: require every application to discover and set the logger level separately.
Impact: calling the documented helper produces factual lifecycle logs immediately; import remains free of logging side effects. Fifteen focused core tests pass after this integration correction.

## Gemini clipping fields

Decision: convert public numeric seconds to API duration strings (`"2s"`) for Static `start_offset` and `end_offset`.
Evidence: numeric guide examples returned HTTP 400; official OpenAPI specifies strings; a corrected direct Flash Lite request returned HTTP 200 and only the expected clipped scene.
Alternative: follow the numeric guide examples or silently omit clipping.
Impact: preserve the approved interval behavior using an observed API format. Agentic partial-interval requests must fail explicitly because that mode does not support these clipping parameters.

## Final integration corrections

Gemini logs its chosen request settings before network submission, and records parsed
response facts even when usage is absent. Terminal HTTP failures expose the observed
status code without exposing response bodies or credentials. Logging uses actual UTC
record timestamps and severity appropriate to failures and retries.

CI uses explicit unittest discovery because bare `python -m unittest` found no tests
in this repository layout. Local validation used the same discovery command on both
supported interpreter versions. Installation examples point to future versioned GitHub
release wheels, since PyPI publication is deferred.
