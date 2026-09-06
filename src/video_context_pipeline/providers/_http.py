"""Private HTTP helpers shared by the optional provider adapters."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import isfinite
from time import monotonic
from typing import Any, Callable

import httpx

from ..errors import ProviderError

_TRANSIENT_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class JsonResponse:
    status_code: int
    data: Any
    headers: Mapping[str, str]


def _retry_after(value: str | None, fallback: float) -> float:
    """Return a bounded-by-caller retry delay, respecting a valid server value."""
    if value is None:
        return fallback
    try:
        delay = float(value)
        return max(fallback, delay) if isfinite(delay) and delay >= 0 else fallback
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return fallback
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(fallback, (retry_at - datetime.now(UTC)).total_seconds(), 0.0)


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    timeout_seconds: float,
    max_retries: int,
    retry_delay_seconds: float,
    params: Mapping[str, str] | None = None,
    json: Any = None,
    content: Any = None,
    content_factory: Callable[[], Any] | None = None,
    on_retry: Callable[[int, int | None], None] | None = None,
    deadline_monotonic: float | None = None,
) -> JsonResponse:
    """Issue one provider request with explicit, same-provider transient retries."""
    for attempt in range(max_retries + 1):
        timeout = timeout_seconds
        if deadline_monotonic is not None:
            timeout = min(timeout, deadline_monotonic - monotonic())
            if timeout <= 0:
                raise ProviderError("provider request deadline elapsed")
        try:
            async with asyncio.timeout(timeout):
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    content=content_factory()
                    if content_factory is not None
                    else content,
                    timeout=timeout,
                    follow_redirects=False,
                )
        except (httpx.TimeoutException, TimeoutError):
            if attempt == max_retries:
                raise ProviderError("provider request timed out") from None
            if on_retry is not None:
                on_retry(attempt + 1, None)
            await asyncio.sleep(
                _within_deadline(retry_delay_seconds, deadline_monotonic)
            )
            continue
        except httpx.TransportError:
            if attempt == max_retries:
                raise ProviderError(
                    "provider connection could not be completed"
                ) from None
            if on_retry is not None:
                on_retry(attempt + 1, None)
            await asyncio.sleep(
                _within_deadline(retry_delay_seconds, deadline_monotonic)
            )
            continue
        if response.status_code in _TRANSIENT_STATUSES and attempt < max_retries:
            if on_retry is not None:
                on_retry(attempt + 1, response.status_code)
            await asyncio.sleep(
                _within_deadline(
                    _retry_after(
                        response.headers.get("Retry-After"), retry_delay_seconds
                    ),
                    deadline_monotonic,
                )
            )
            continue
        if not 200 <= response.status_code < 300:
            raise ProviderError(
                f"provider request failed with HTTP status {response.status_code}",
                http_status=response.status_code,
            )
        try:
            data = response.json()
        except ValueError:
            if response.content:
                raise ProviderError(
                    "provider returned a malformed JSON response"
                ) from None
            data = None
        return JsonResponse(response.status_code, data, dict(response.headers))
    raise AssertionError("retry loop did not return or raise")


def _within_deadline(delay: float, deadline_monotonic: float | None) -> float:
    if deadline_monotonic is None:
        return delay
    remaining = deadline_monotonic - monotonic()
    if remaining <= 0:
        raise ProviderError("provider request deadline elapsed")
    return min(delay, remaining)
