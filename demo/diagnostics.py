"""Actionable diagnostics without exposing arbitrary exception or provider content."""

from __future__ import annotations

from video_context_pipeline import ProviderError, VideoContextPipelineError

# Only these audited library-authored messages may cross the web boundary.
_MESSAGES = {
    "Gemini requires a video media artifact": "Gemini needs video, but the downloaded or selected artifact was classified as audio. Inspect its format or probe the file before retrying.",
    "timed visual output requires a known media duration or explicit analyzed_end_seconds": "Timed visual output needs a known duration or an explicit analysis end. Probe an uploaded/downloaded artifact first, or supply analyzed_end_seconds.",
    "automatic Gemini processing requires known media duration": "Automatic processing requires a known duration. Probe the media first or explicitly choose static processing.",
    "automatic visual processing requires known media duration_seconds": "This source did not report a duration. Automatic pipeline processing cannot run; probe a downloaded artifact and use independent visual analysis, or explicitly select static processing.",
    "visual analysis interval lies outside the known media duration": "The selected analysis interval exceeds the video's known duration. Correct the start/end values.",
    "agentic Gemini processing does not support a partial analyzed interval": "Agentic processing requires the full video. Remove partial analysis bounds or explicitly choose static processing.",
    "visual windows lie outside the known media duration": "One or more visual windows exceed the video's known duration.",
    "provider request timed out": "The provider HTTP request timed out after the configured request timeout and retries. This is separate from queued-job and uploaded-file polling deadlines.",
    "provider connection could not be completed": "The server could not connect to the provider after the configured retries. Check server network access and provider availability.",
    "provider request deadline elapsed": "The provider polling deadline elapsed before the next request could finish.",
    "Supadata transcript job timed out": "Supadata returned a job ID, but its transcript was not ready before job_timeout_seconds. Inspect queued/active status in the operational logs.",
    "Supadata transcript job failed": "Supadata marked this transcript job as failed. Check this request in the Supadata dashboard; increasing the timeout will not repair a failed job.",
    "Supadata completed a job without transcript content": "Supadata marked the job complete but omitted its transcript content. The provider response is incomplete.",
    "Gemini uploaded file processing timed out": "Google did not finish processing the uploaded video before file_poll_deadline_seconds.",
    "Gemini uploaded file processing failed": "Google reported that uploaded-video processing failed.",
    "Gemini interaction did not complete": "Google returned an interaction that was not completed. No visual result was published.",
    "Gemini returned malformed visual JSON": "Google returned a visual response that did not match the requested JSON representation.",
    "yt-dlp operation timed out": "Source inspection or download exceeded request_timeout_seconds.",
}


def failure_message(error: BaseException) -> str:
    """Inspect causal/grouped failures, matching only known types and exact text."""
    pending = [error]
    seen: set[int] = set()
    explanations: list[str] = []
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, BaseExceptionGroup):
            pending.extend(item.exceptions)
        if item.__cause__ is not None:
            pending.append(item.__cause__)
        explanation = None
        if isinstance(item, ProviderError) and type(item.http_status) is int:
            status = item.http_status
            if status == 429:
                explanation = "Provider rate or quota limit reached (HTTP 429). Check the provider dashboard before retrying."
            elif status in {401, 403}:
                explanation = f"Provider authentication or access was rejected (HTTP {status}). Check the server key and its model/service access."
            elif status in {400, 404, 413, 422}:
                explanation = f"Provider rejected the request (HTTP {status}). Check the selected model, input, and request settings."
            elif 500 <= status <= 599:
                explanation = f"Provider service failed (HTTP {status}). The remote service could not complete the request."
        if explanation is None and isinstance(item, VideoContextPipelineError):
            explanation = _MESSAGES.get(str(item))
        if explanation and explanation not in explanations:
            explanations.append(explanation)
    if not explanations:
        explanations.append(
            "Operation failed. Check the input, provider availability, and explicit settings."
        )
    return " ".join(explanations) + " No partial outputs were published."
