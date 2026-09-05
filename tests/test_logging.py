from __future__ import annotations

import json
import logging
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from video_context_pipeline.logging import (
    JsonFormatter,
    configure_json_logging,
    safe_log_fields,
)  # noqa: E402


class LoggingTests(unittest.TestCase):
    def test_explicit_console_setup_enables_info_without_duplicate_handlers(
        self,
    ) -> None:
        logger = logging.Logger("vcp-test-console")
        configure_json_logging(logger)
        configure_json_logging(logger)
        self.assertTrue(logger.isEnabledFor(logging.INFO))
        self.assertEqual(len(logger.handlers), 1)
        self.assertFalse(logger.propagate)

    def test_json_logging_keeps_only_allowlisted_factual_fields(self) -> None:
        record = logging.LogRecord(
            "vcp", logging.INFO, __file__, 0, "finished", (), None
        )
        record.vcp_fields = safe_log_fields(
            request_id="request-1",
            stage="transcribe",
            retries=1,
            usage={"provider_units": 3},
        )
        rendered = json.loads(JsonFormatter().format(record))
        self.assertEqual(rendered["request_id"], "request-1")
        self.assertNotIn("url", rendered)
        self.assertNotIn("api_key", rendered)

    def test_secrets_payloads_and_inferred_metrics_are_rejected(self) -> None:
        for field in ("api_key", "url", "provider_body", "estimated_cost"):
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(ValueError, "unsafe"),
            ):
                safe_log_fields(**{field: "sensitive"})


if __name__ == "__main__":
    unittest.main()
