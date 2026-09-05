"""Injected async interfaces implemented by provider adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from .config import MediaRequest, TranscriptRequest, VisualRequest
from .models import MediaArtifact, ProviderOutput, TranscriptSegment, VideoEvent


@runtime_checkable
class MetadataProvider(Protocol):
    async def inspect(self, url: str) -> ProviderOutput[Mapping[str, Any]]:
        """Inspect a supported public URL."""


@runtime_checkable
class TranscriptProvider(Protocol):
    async def transcribe(
        self, url: str, request: TranscriptRequest
    ) -> ProviderOutput[str | tuple[TranscriptSegment, ...]]:
        """Return the caller-selected plain text or timed transcript representation."""


@runtime_checkable
class MediaProvider(Protocol):
    async def download(
        self, url: str, request: MediaRequest
    ) -> ProviderOutput[MediaArtifact]:
        """Produce a local media artifact with accurate ownership information."""


@runtime_checkable
class VisualProvider(Protocol):
    async def understand(
        self,
        media: MediaArtifact,
        request: VisualRequest,
        *,
        transcript_context: str | None,
    ) -> ProviderOutput[str | tuple[VideoEvent, ...]]:
        """Understand a local video, optionally using supplied transcript context."""
