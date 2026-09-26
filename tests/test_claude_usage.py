"""사용량 정책·집계·오류 처리 회귀 검사. 실제 모델·GPU·알림 호출 없음."""

import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import orchestrator as loop
from claude_usage import summarize_stream, usage_report


class UsageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.stream = self.root / "claude_stream.jsonl"

    def write_events(self, events):
        self.stream.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")

    def event(self, identity="r1", session="s1", cost=1, output=100, **extra):
        return {
            "type": "result", "uuid": identity, "session_id": session,
            "total_cost_usd": cost, "num_turns": 3, "is_error": False,
            "modelUsage": {"sonnet": {"outputTokens": output, "thinkingTokens": 20,
                                      "cacheReadInputTokens": 1000, "costUSD": cost}},
            "usage": {"output_tokens": output}, **extra,
        }

    def test_session_cumulative_values_and_duplicate_results_are_not_added(self):
        first = self.event()
        second = self.event("r2", cost=2, output=180, usage={"output_tokens": 80})
        quota = self.event("r3", cost=2, output=180, usage={"output_tokens": 0}, is_error=True, num_turns=1)
        self.write_events([first, second, quota, quota])
        summary = summarize_stream(self.stream)
        self.assertEqual(summary["reported_cost_usd"], 2)
        self.assertEqual(summary["model_usage"]["sonnet"]["outputTokens"], 180)
        self.assertEqual(summary["model_usage"]["sonnet"]["thinkingTokens"], 20)
        self.assertEqual(summary["sessions"]["s1"]["invocation_usage"]["output_tokens"], 180)
        self.assertEqual(summary["num_turns"], 7)
        self.assertEqual(summary["error_results"], 1)
        self.assertEqual(summary, summarize_stream(self.stream))

    def test_new_sessions_are_added_and_models_remain_separate(self):
        self.write_events([self.event(), self.event("r2", "s2", cost=3,
                          modelUsage={"opus": {"outputTokens": 400}})])
        data = summarize_stream(self.stream)
        self.assertEqual(data["reported_cost_usd"], 4)
        self.assertEqual(set(data["model_usage"]), {"sonnet", "opus"})

    def test_permission_denials_are_deduplicated(self):
        denials = [{"tool_use_id": "t1", "tool_name": "Bash"}]
        self.write_events([self.event(permission_denials=denials), self.event("r2", permission_denials=denials)])
        self.assertEqual(summarize_stream(self.stream)["permission_denials"], 1)

    def test_partial_or_missing_result_is_flagged_not_priced(self):
        self.write_events([self.event(), {"type": "assistant", "session_id": "s1"}])
        data = summarize_stream(self.stream)
        self.assertEqual(data["reported_cost_usd"], 1)
        self.assertTrue(data["warnings"])
        self.stream.write_text('{"type":', encoding="utf-8")
        data = summarize_stream(self.stream)
        self.assertTrue(data["warnings"])
        self.assertEqual(data["reported_cost_usd"], 0)

    def test_legacy_missing_fields_are_tolerated(self):
        self.write_events([{"type": "result", "result": "완료"}])
        self.assertTrue(summarize_stream(self.stream)["warnings"])

    def test_report_is_read_only_and_deduplicates_sessions_across_logs(self):
        for n in (1, 2):
            d = self.root / f"iter_{n:03d}"
            d.mkdir()
            (d / self.stream.name).write_text(json.dumps(self.event()) + "\n", encoding="utf-8")
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        report = usage_report(self.root)
        self.assertIn("$1.0000", report)
        self.assertIn("실제 청구액", report)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_failed_call_persists_usage_before_raising_spend_limit(self):
        event = self.event(is_error=True, result="You've hit your monthly spend limit · resets at 9am")
        args = argparse.Namespace(gpus=None, claude_timeout=0)

        def run(cmd, log_path, timeout, env, on_line, **kwargs):
            self.assertEqual(cmd[cmd.index("--model") + 1], "sonnet")
            self.write_events([event])
            on_line(json.dumps(event))

        with patch.object(loop, "run_streaming", side_effect=run), patch.object(loop, "resource_context", return_value=""):
            with self.assertRaises(loop.SpendLimitError):
                loop.run_claude(args, "구현", self.stream, "standard")
        stored = json.loads((self.root / "claude_usage.json").read_text())
        self.assertEqual(stored["error_results"], 1)
        self.assertEqual(stored["reported_cost_usd"], 1)

    def test_interrupted_call_persists_usage_without_hiding_stop(self):
        def run(*args, **kwargs):
            self.write_events([{"type": "assistant", "session_id": "s"}])
            raise loop.StopRequested("테스트 중단")

        with patch.object(loop, "run_streaming", side_effect=run), patch.object(loop, "resource_context", return_value=""):
            with self.assertRaisesRegex(loop.StopRequested, "테스트 중단"):
                loop.run_claude(argparse.Namespace(gpus=None, claude_timeout=0), "구현", self.stream, "standard")
        self.assertTrue(json.loads((self.root / "claude_usage.json").read_text())["warnings"])


class UsagePolicyTests(unittest.TestCase):
    def test_standard_is_sonnet_and_keeps_normal_review(self):
        self.assertEqual(loop.tier_spec("claude", "standard"), {"model": "sonnet", "effort": "medium"})
        with patch.object(loop, "tiers_used", return_value={"claude": "standard"}):
            self.assertEqual(loop.review_tier(argparse.Namespace(gpt_tier=None), 9), "normal")
        schema = json.loads((loop.PROMPT_DIR / "plan_schema.json").read_text())
        self.assertEqual(set(schema["properties"]["claude_tier"]["enum"]), set(loop.CLAUDE_TIERS))
        with patch.object(sys, "argv", ["orchestrator.py", "--claude-tier", "standard"]):
            self.assertEqual(loop.parse_args().claude_tier, "standard")

    def test_saved_tiers_and_explicit_override_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(loop, "iter_dir", return_value=Path(directory)), \
                patch.object(loop, "load_plan", return_value={"claude_tier": "heavy"}):
            self.assertEqual(loop.claude_tier(argparse.Namespace(claude_tier=None), 1), "heavy")
            self.assertEqual(loop.claude_tier(argparse.Namespace(claude_tier="standard"), 1), "standard")

    def test_research_review_remains_mandatory_for_standard(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(loop, "iter_dir", return_value=Path(directory)):
            for role in ("diagnostic", "method", "confirmatory"):
                with patch.object(loop, "load_plan", return_value={"experiment_role": role, "review_mode": "skip",
                                                                   "claude_tier": "standard"}):
                    self.assertTrue(loop.review_decision(argparse.Namespace(always_review=False), 1)[0])

    def test_monthly_spend_does_not_retry_even_when_reset_or_429_appears(self):
        error = loop.failure_error("오류", "429 You've hit your monthly spend limit · session resets at 9am")
        self.assertIsInstance(error, loop.SpendLimitError)
        with patch.object(loop, "sleep_with_stop") as sleep:
            with self.assertRaises(loop.SpendLimitError):
                loop.with_retries("Claude", lambda: (_ for _ in ()).throw(error))
            sleep.assert_not_called()
        self.assertIsInstance(loop.failure_error("오류", "429 rate limit"), loop.UsageLimitError)
        self.assertIsInstance(loop.failure_error("오류", "connection lost"), loop.RetryableError)

    def test_usage_cli_never_starts_agents_or_mutates_state(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(loop, "RUNS_DIR", Path(directory)), \
                patch.object(sys, "argv", ["orchestrator.py", "--usage"]), \
                patch.object(loop, "run_loop") as run, patch.object(loop, "Human") as human, \
                patch.object(loop, "apply_pending_replan") as replan, contextlib.redirect_stdout(io.StringIO()):
            loop.main()
            run.assert_not_called()
            human.assert_not_called()
            replan.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_read_only_git_added_without_broad_git_permission(self):
        settings = json.loads((loop.AGENT_DIR / "claude_settings.json").read_text())["permissions"]
        self.assertIn("Bash(git ls-files *)", settings["allow"])
        self.assertNotIn("Bash(git *)", settings["allow"])
        for command in ("commit", "checkout", "reset", "stash", "push"):
            self.assertIn(f"Bash(git {command} *)", settings["deny"])


if __name__ == "__main__":
    unittest.main()
