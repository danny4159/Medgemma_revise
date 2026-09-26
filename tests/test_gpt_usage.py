"""GPT 표시 사용량과 품질 유지 기준. 실제 모델 호출 없음."""

import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gpt_usage
import orchestrator as loop


class GPTUsageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.log = self.root / "plan_codex.log"

    def block(self, sid, tokens, error=False):
        value = f"OpenAI Codex v0.155.1\nmodel: gpt-6-astra\nreasoning effort: high\nsession id: {sid}\n"
        if error:
            value += "ERROR: usage limit\n"
        if tokens is not None:
            value += f"tokens used\n{tokens:,}\n"
        return value

    def test_failed_and_retried_sessions_are_visible_without_billing_estimate(self):
        self.log.write_text(self.block("one", 1234, True) + self.block("two", 2345))
        data = gpt_usage.summarize_log(self.log)
        self.assertEqual(data["displayed_tokens"], 3579)
        self.assertEqual(data["session_count"], 2)
        self.assertEqual(data["error_sessions"], 1)
        self.assertNotIn("cost_usd", data)

    def test_repeated_session_uses_maximum_and_unreported_is_not_assumed_free(self):
        self.log.write_text(self.block("one", 1000) + self.block("one", 1500) + self.block("two", None))
        data = gpt_usage.summarize_log(self.log)
        self.assertEqual(data["displayed_tokens"], 1500)
        self.assertEqual(data["unreported_calls"], 1)
        self.assertIsNone(data["sessions"]["two"]["displayed_tokens"])

    def test_unknown_format_is_marked_unreported(self):
        self.log.write_text("unexpected CLI format\n")
        self.assertEqual(gpt_usage.summarize_log(self.log)["unreported_calls"], 1)

    def test_report_is_read_only(self):
        d = self.root / "iter_001"
        d.mkdir()
        log = d / "plan_codex.log"
        log.write_text(self.block("one", 1234))
        before = log.read_bytes()
        report = gpt_usage.usage_report(self.root)
        self.assertIn("1,234", report)
        self.assertIn("구독 한도 소진율이 아닙니다", report)
        self.assertEqual(log.read_bytes(), before)
        self.assertEqual(list(d.iterdir()), [log])

    def test_codex_failure_still_saves_usage_without_hiding_error(self):
        def run(*args, **kwargs):
            self.log.write_text(self.block("one", 1000, True))
            raise loop.UsageLimitError("한도", "usage limit")

        with patch.object(loop, "run_streaming", side_effect=run), \
                patch.object(loop, "resource_context", return_value=""), self.assertRaises(loop.UsageLimitError):
            loop.run_codex(argparse.Namespace(gpt_timeout=0, gpus=None), "계획", self.root / "raw.json", self.log, "deep")
        self.assertEqual(json.loads((self.root / "plan_usage.json").read_text())["error_sessions"], 1)

    def test_model_efforts_and_round_budget_are_unchanged(self):
        for tier, effort in (("deep", "high"), ("normal", "medium"), ("light", "low")):
            self.assertEqual(loop.tier_spec("gpt", tier), {"model": "gpt-6-astra", "effort": effort})
        with patch("sys.argv", ["orchestrator.py"]):
            self.assertEqual(loop.parse_args().max_think_rounds, 4)


if __name__ == "__main__":
    unittest.main()
