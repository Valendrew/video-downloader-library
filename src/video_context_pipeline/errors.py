"""Public exceptions raised by video-context-pipeline."""


class VideoContextPipelineError(Exception):
    """Base exception for expected library failures."""


class ConfigurationError(VideoContextPipelineError):
    """A configuration value is absent or invalid."""


class ValidationError(VideoContextPipelineError):
    """A request or provider response violates a public contract."""


class ProviderError(VideoContextPipelineError):
    """A provider could not complete a requested operation."""

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


class PipelineError(VideoContextPipelineError):
    """An atomic pipeline request could not complete."""
