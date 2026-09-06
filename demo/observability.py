"""Demo-owned stage tracking and a content-free bridge to library logging."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, TypeVar

from .schema import State, StepInfo

T = TypeVar("T")


@dataclass
class Step:
    name: str
    dependencies: list[str]
    state: State = "pending"
    started: float | None = None
    finished: float | None = None
    progress: dict[str, Any] | None = None

    def info(self) -> StepInfo:
        elapsed = (
            0.0
            if self.started is None
            else (self.finished or monotonic()) - self.started
        )
        return StepInfo(
            id=self.name,
            dependencies=self.dependencies,
            state=self.state,
            elapsed_seconds=elapsed,
            progress=self.progress,
        )


@dataclass
class Monitor:
    identifier: str
    steps: dict[str, Step]
    created: float = field(default_factory=monotonic)
    logs: list[dict[str, Any]] = field(default_factory=list)

    def event(self, stage: str, state: str, **facts: Any) -> None:
        self.logs.append(
            {
                "elapsed_seconds": monotonic() - self.created,
                "request_id": self.identifier,
                "stage": stage,
                "status": state,
                **facts,
            }
        )
        # Bounded operational records; no content or provider exception messages.
        del self.logs[:-500]

    async def run(self, name: str, operation: Callable[[], Awaitable[T]]) -> T:
        step = self.steps[name]
        if name == "visual" and "barrier" in self.steps:
            barrier = self.steps["barrier"]
            barrier.state = "completed"
            barrier.started = barrier.finished = monotonic()
            self.event("barrier", "completed")
        step.state, step.started = "running", monotonic()
        self.event(name, "running")
        try:
            result = await operation()
        except asyncio.CancelledError:
            step.state = "cancelled"
            raise
        except Exception:
            step.state = "failed"
            raise
        else:
            step.state = "completed"
            return result
        finally:
            step.finished = monotonic()
            self.event(name, step.state, duration_seconds=step.finished - step.started)

    def cancelling(self) -> None:
        for step in self.steps.values():
            if step.state == "running":
                step.state = "cancelling"
        self.event("job", "cancelling")

    def finish(self, state: State) -> None:
        for step in self.steps.values():
            if step.state in {"pending", "running", "cancelling"}:
                step.state = "completed" if state == "completed" else "cancelled"
                step.finished = monotonic()
        self.event("job", state)

    def logger(self) -> logging.Logger:
        result = logging.Logger(f"demo.job.{self.identifier}", logging.INFO)
        result.propagate = False
        result.addHandler(FactualHandler(self))
        return result


class FactualHandler(logging.Handler):
    """Ignore free-form log messages and accept only typed operational facts."""

    def __init__(self, monitor: Monitor) -> None:
        super().__init__()
        self.monitor = monitor
        self.loop = asyncio.get_running_loop()

    def emit(self, record: logging.LogRecord) -> None:
        fields = getattr(record, "vcp_fields", None)
        if not isinstance(fields, Mapping):
            return
        facts: dict[str, Any] = {}
        for key in (
            "duration_seconds",
            "retries",
            "bytes",
            "total_bytes",
            "downloaded_bytes",
            "attempt",
            "http_status",
            "output_count",
            "fps",
        ):
            value = fields.get(key)
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            ):
                facts[key] = value
        if isinstance(fields.get("total_is_estimate"), bool):
            facts["total_is_estimate"] = fields["total_is_estimate"]
        if fields.get("phase") in ("request", "poll"):
            facts["phase"] = fields["phase"]
        if fields.get("error_type") in (
            "ProviderError",
            "ValidationError",
            "ConfigurationError",
            "PipelineError",
            "TimeoutError",
        ):
            facts["error_type"] = fields["error_type"]
        stage = fields.get("stage")
        if not isinstance(stage, str) or stage not in {
            "pipeline",
            "metadata",
            "download",
            "thumbnail",
            "transcript",
            "visual",
            "probe",
            "extract",
            "convert",
            "enrich",
            "cleanup",
            "upload",
            "generation",
            "poll",
            "request",
        }:
            stage = "provider"
        status = fields.get("status")
        if not isinstance(status, str) or status not in {
            "started",
            "completed",
            "failed",
            "cancelled",
            "retry",
            "retrying",
            "queued",
            "active",
            "running",
            "empty",
        }:
            status = "event"
        self.loop.call_soon_threadsafe(
            lambda: self.monitor.event(stage, status, **facts)
        )
