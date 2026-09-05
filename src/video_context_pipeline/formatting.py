"""Public presentation formatting, kept separate from provider prompt content."""

from __future__ import annotations

from collections.abc import Sequence

from .errors import ValidationError
from .models import TranscriptSegment


def transcript_plain_text(value: str | Sequence[TranscriptSegment]) -> str:
    """Return readable transcript text without leaking segment objects or JSON."""
    if isinstance(value, str):
        return value
    if not isinstance(value, Sequence):
        raise ValidationError("transcript text must be a string or transcript segments")
    parts: list[str] = []
    for segment in value:
        if not isinstance(segment, TranscriptSegment):
            raise ValidationError(
                "transcript segments must be TranscriptSegment objects"
            )
        parts.append(segment.text.strip())
    return "\n".join(parts)
