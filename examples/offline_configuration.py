"""Construct every provider configuration from fake environment values; makes no API calls."""

from video_context_pipeline import load_environment

FAKE_ENV = {
    # Caller choices: Flash Lite, medium resolution, and medium thinking.
    "GEMINI_API_KEY": "not-a-real-key",
    "VCP_GEMINI_MODEL": "gemini-3.5-flash-lite",
    "VCP_GEMINI_MEDIA_RESOLUTION": "medium",
    "VCP_GEMINI_THINKING_LEVEL": "medium",
    # Caller choices: automatic mode uses this FPS below its duration threshold.
    "VCP_GEMINI_PROCESSING_MODE": "automatic",
    "VCP_GEMINI_STATIC_FPS": "1",
    "VCP_GEMINI_AGENTIC_THRESHOLD_SECONDS": "120",
    # Caller choices: provider request/retry/upload/poll operational limits.
    "VCP_GEMINI_REQUEST_TIMEOUT_SECONDS": "60",
    "VCP_GEMINI_MAX_RETRIES": "2",
    "VCP_GEMINI_RETRY_BACKOFF_SECONDS": "1",
    "VCP_GEMINI_FILE_UPLOAD_THRESHOLD_BYTES": "20000000",
    "VCP_GEMINI_FILE_POLL_DEADLINE_SECONDS": "300",
    "VCP_GEMINI_FILE_POLL_INTERVAL_SECONDS": "2",
    "SUPADATA_API_KEY": "not-a-real-key",
    # Caller choices: Supadata request, job, polling, and retry limits.
    "VCP_SUPADATA_REQUEST_TIMEOUT_SECONDS": "30",
    "VCP_SUPADATA_JOB_TIMEOUT_SECONDS": "120",
    "VCP_SUPADATA_POLL_INTERVAL_SECONDS": "2",
    "VCP_SUPADATA_MAX_RETRIES": "2",
    "VCP_SUPADATA_RETRY_DELAY_SECONDS": "1",
}


settings = load_environment(
    include_gemini=True, include_supadata=True, environ=FAKE_ENV
)
assert settings.gemini is not None and settings.supadata is not None
print("constructed Gemini and Supadata settings without a provider call")
