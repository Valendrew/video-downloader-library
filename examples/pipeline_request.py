"""Build an explicit pipeline request without calling a provider."""

from video_context_pipeline import (
    GeminiSettings,
    MediaRequest,
    MediaSettings,
    PipelineRequest,
    SupadataSettings,
    TranscriptRequest,
    VisualRequest,
)

media = MediaSettings(
    request_timeout_seconds=60.0, cookie_file=None, output_directory=None
)
transcript = TranscriptRequest(
    format="transcript_segments",
    settings=SupadataSettings(
        api_key="not-a-real-key",
        # Caller choices: request/job deadlines and retry cadence.
        request_timeout_seconds=30.0,
        job_timeout_seconds=120.0,
        poll_interval_seconds=2.0,
        max_retries=2,
        retry_delay_seconds=1.0,
    ),
)
visual = VisualRequest(
    format="video_events",
    settings=GeminiSettings(
        api_key="not-a-real-key",
        # Caller choices: model, resolution, thinking, and static frame rate.
        model="gemini-3.5-flash-lite",
        media_resolution="medium",
        thinking_level="medium",
        processing_mode="static",
        static_fps=1.0,
        agentic_threshold_seconds=None,
        # Caller choices: request/retry/upload/poll operational limits.
        request_timeout_seconds=60.0,
        max_retries=2,
        retry_backoff_seconds=1.0,
        file_upload_threshold_bytes=20_000_000,
        file_poll_deadline_seconds=300.0,
        file_poll_interval_seconds=2.0,
    ),
    timestamp_mode="approximate",
    analyzed_start_seconds=0.0,
    analyzed_end_seconds=60.0,
)
request = PipelineRequest(
    transcript=transcript,
    visual=visual,
    visual_media=MediaRequest(settings=media, selected_format_id="137"),
    include_transcript_context=True,
)
assert request.visual_media is not None
print(
    "constructed a strict transcript plus visual pipeline request without a provider call"
)
