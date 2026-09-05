"""Supadata transcript adapter using its documented generated-transcript API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from math import isfinite
from time import monotonic
from typing import Any
from urllib.parse import quote

import httpx

from ..config import TranscriptRequest
from ..errors import ProviderError
from ..formatting import transcript_plain_text
from ..logging import current_request_id, request_correlation, safe_log_fields
from ..models import OutputFormat, OutputStatus, ProviderOutput, TranscriptSegment
from ..pipeline import validate_platform_url
from ._http import request_json

_API_URL = "https://api.supadata.ai/v1/transcript"
_FAILED_JOB_STATUSES = frozenset({"failed", "error", "cancelled", "canceled"})


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProviderError(f"Supadata returned an invalid {name}")
    number = float(value)
    if not isfinite(number) or number < 0:
        raise ProviderError(f"Supadata returned an invalid {name}")
    return number


class SupadataProvider:
    """Async transcript provider; an injected client enables deterministic testing."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._client = client
        self._logger = logger or logging.getLogger(
            "video_context_pipeline.providers.supadata"
        )

    async def transcribe(
        self, url: str, request: TranscriptRequest
    ) -> ProviderOutput[str | tuple[TranscriptSegment, ...]]:
        with request_correlation(current_request_id()):
            started = monotonic()
            self._emit("provider started", status="started", stage="transcript")
            try:
                validated_url = validate_platform_url(url)
                headers = {"x-api-key": request.settings.api_key}
                if self._client is None:
                    async with httpx.AsyncClient(follow_redirects=False) as client:
                        result = await self._transcribe(
                            client, validated_url, request, headers
                        )
                else:
                    result = await self._transcribe(
                        self._client, validated_url, request, headers
                    )
            except asyncio.CancelledError:
                self._emit(
                    "provider cancelled",
                    status="cancelled",
                    stage="transcript",
                    duration_seconds=monotonic() - started,
                )
                raise
            except Exception as exc:
                self._emit(
                    "provider failed",
                    status="failed",
                    stage="transcript",
                    error_type=type(exc).__name__,
                    http_status=getattr(exc, "http_status", None),
                    duration_seconds=monotonic() - started,
                )
                raise
            self._emit(
                "provider completed",
                status=result.status.value,
                stage="transcript",
                output_count=len(result.data),
                phase="characters" if isinstance(result.data, str) else "segments",
                duration_seconds=monotonic() - started,
            )
            return result

    async def _transcribe(
        self,
        client: httpx.AsyncClient,
        url: str,
        request: TranscriptRequest,
        headers: Mapping[str, str],
    ) -> ProviderOutput[str | tuple[TranscriptSegment, ...]]:
        settings = request.settings
        response = await request_json(
            client,
            "GET",
            _API_URL,
            headers=headers,
            params={"url": url, "mode": "generate", "text": "false"},
            timeout_seconds=settings.request_timeout_seconds,
            max_retries=settings.max_retries,
            retry_delay_seconds=settings.retry_delay_seconds,
            on_retry=self._retry,
        )
        payload = await self._wait_for_result(client, response.data, request, headers)
        return self._convert(payload, request)

    async def _wait_for_result(
        self,
        client: httpx.AsyncClient,
        initial: Any,
        request: TranscriptRequest,
        headers: Mapping[str, str],
    ) -> Mapping[str, Any]:
        if not isinstance(initial, Mapping):
            raise ProviderError("Supadata returned an invalid transcript response")
        payload: Mapping[str, Any] = initial
        job_id = payload.get("jobId")
        if not isinstance(job_id, str) or not job_id.strip():
            if "content" not in payload:
                raise ProviderError(
                    "Supadata returned an incomplete transcript response"
                )
            job_id = None
        deadline = monotonic() + request.settings.job_timeout_seconds
        while True:
            status = payload.get("status")
            if isinstance(status, str) and status.lower() in _FAILED_JOB_STATUSES:
                raise ProviderError("Supadata transcript job failed")
            if "content" in payload:
                return payload
            if job_id is None:
                raise ProviderError(
                    "Supadata returned an incomplete transcript response"
                )
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise ProviderError("Supadata transcript job timed out")
            await asyncio.sleep(min(request.settings.poll_interval_seconds, remaining))
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise ProviderError("Supadata transcript job timed out")
            response = await request_json(
                client,
                "GET",
                f"{_API_URL}/{quote(job_id, safe='')}",
                headers=headers,
                timeout_seconds=min(
                    request.settings.request_timeout_seconds, remaining
                ),
                max_retries=request.settings.max_retries,
                retry_delay_seconds=request.settings.retry_delay_seconds,
                on_retry=self._retry,
                deadline_monotonic=deadline,
            )
            if not isinstance(response.data, Mapping):
                raise ProviderError("Supadata returned an invalid transcript response")
            payload = response.data

    def _convert(
        self, payload: Mapping[str, Any], request: TranscriptRequest
    ) -> ProviderOutput[str | tuple[TranscriptSegment, ...]]:
        content = payload.get("content")
        if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
            raise ProviderError("Supadata returned malformed transcript content")
        language = payload.get("lang")
        if language is not None and (
            not isinstance(language, str) or not language.strip()
        ):
            raise ProviderError("Supadata returned an invalid transcript language")
        segments: list[TranscriptSegment] = []
        for item in content:
            if not isinstance(item, Mapping):
                raise ProviderError("Supadata returned malformed transcript content")
            text, offset, duration = (
                item.get("text"),
                item.get("offset"),
                item.get("duration"),
            )
            if not isinstance(text, str) or not text.strip():
                raise ProviderError("Supadata returned malformed transcript content")
            start = _number(offset, "offset") / 1000
            end = start + _number(duration, "duration") / 1000
            segments.append(TranscriptSegment(start, end, text))
        segment_result = tuple(segments)
        status = OutputStatus.EMPTY if not segment_result else OutputStatus.CONTENT
        data: str | tuple[TranscriptSegment, ...]
        if request.format is OutputFormat.TRANSCRIPT_TEXT:
            data = transcript_plain_text(segment_result)
        else:
            data = segment_result
        return ProviderOutput(
            request.format, data, "supadata", status, language=language
        )

    def _retry(self, attempt: int, http_status: int | None) -> None:
        fields: dict[str, Any] = {
            "status": "retrying",
            "stage": "transcript",
            "attempt": attempt,
        }
        if http_status is not None:
            fields["http_status"] = http_status
        self._emit("provider retry", **fields)

    def _emit(self, message: str, **fields: Any) -> None:
        level = (
            logging.ERROR
            if fields.get("status") == "failed"
            else logging.WARNING
            if fields.get("status") == "retrying"
            else logging.INFO
        )
        self._logger.log(
            level,
            message,
            extra={
                "vcp_fields": safe_log_fields(
                    provider="supadata", request_id=current_request_id(), **fields
                )
            },
        )
