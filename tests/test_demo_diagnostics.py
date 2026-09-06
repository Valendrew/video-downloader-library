"""Provider failures remain actionable without exposing private exception content."""

import asyncio
import unittest

import httpx

from demo.diagnostics import failure_message
from demo.observability import Monitor
from video_context_pipeline import PipelineError, ProviderError, ValidationError
from video_context_pipeline.providers._http import request_json


class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    def test_wrapped_pipeline_failure_reports_safe_cause(self):
        outer = PipelineError("private outer text")
        outer.__cause__ = ExceptionGroup(
            "private group", [ProviderError("private body", http_status=429)]
        )
        message = failure_message(outer)
        self.assertIn("HTTP 429", message)
        self.assertIn("No partial outputs", message)
        self.assertNotIn("private", message)

    def test_known_validation_and_unknown_errors_are_redacted(self):
        self.assertIn(
            "Gemini needs video",
            failure_message(ValidationError("Gemini requires a video media artifact")),
        )
        for exception in (
            RuntimeError("private-key"),
            ProviderError("private-cookie"),
            ValidationError("private-content"),
        ):
            self.assertNotIn("private", failure_message(exception))
        self.assertIn(
            "job_timeout_seconds",
            failure_message(ProviderError("Supadata transcript job timed out")),
        )

    async def test_transport_timeout_and_connection_failures_are_distinct(self):
        for kind, expected in (
            (httpx.ReadTimeout, "provider request timed out"),
            (httpx.ConnectError, "provider connection could not be completed"),
        ):
            with self.subTest(kind=kind):

                async def handler(request):
                    raise kind("private-url", request=request)

                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(handler)
                ) as client:
                    with self.assertRaises(ProviderError) as error:
                        await request_json(
                            client,
                            "GET",
                            "https://example.com",
                            headers={},
                            timeout_seconds=1,
                            max_retries=0,
                            retry_delay_seconds=0.01,
                        )
                self.assertEqual(str(error.exception), expected)

    async def test_phase_retry_and_error_types_are_allowlisted(self):
        monitor = Monitor("test", {})
        logger = monitor.logger()
        for status in ("queued", "active", "retrying"):
            logger.info(
                "private message",
                extra={
                    "vcp_fields": {
                        "status": status,
                        "stage": "transcript",
                        "phase": "poll",
                        "error_type": "ProviderError",
                    }
                },
            )
        logger.info(
            "private message",
            extra={
                "vcp_fields": {
                    "status": "private-status",
                    "stage": "transcript",
                    "phase": "private-phase",
                    "error_type": "private-type",
                }
            },
        )
        await asyncio.sleep(0)
        self.assertEqual(
            [entry["status"] for entry in monitor.logs[:3]],
            ["queued", "active", "retrying"],
        )
        self.assertTrue(all(entry["phase"] == "poll" for entry in monitor.logs[:3]))
        self.assertNotIn("private", str(monitor.logs))
