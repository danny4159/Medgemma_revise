"""MR-RATE 우선 전환·구독 소진 인계. 실제 모델·GPU·네트워크 호출 없음."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import orchestrator as loop
import test_orchestrator_workflow as fixtures

ROOT = Path(__file__).resolve().parents[1]


class QuotaTests(unittest.TestCase):
    def test_subscription_only_and_explicit_opt_in(self):
        quota = loop.UsageLimitError("limit", limit_type="five_hour")
        with patch.object(loop, "sleep_with_stop") as sleep:
            with self.assertRaises(loop.UsageLimitError):
                loop.with_retries("Claude", Mock(side_effect=quota), handoff_on_quota=True)
            sleep.assert_not_called()
        for error in (loop.UsageLimitError("busy", "429 overloaded"),
                      loop.SpendLimitError("monthly spend"), loop.RetryableError("network")):
            self.assertFalse(loop.subscription_quota(error))
        self.assertTrue(loop.subscription_quota(loop.UsageLimitError("limit", "You've hit your usage limit")))

    def test_busy_still_retries_not_handoff(self):
        fn = Mock(side_effect=[loop.UsageLimitError("busy", "overloaded"), "done"])
        with patch.object(loop, "sleep_with_stop") as sleep, patch.object(loop, "notify"), \
                patch.dict(loop.STATE, n=None):
            self.assertEqual(loop.with_retries("Claude", fn, handoff_on_quota=True), "done")
            sleep.assert_called_once()

    def test_only_tagged_child_detected_and_not_killed(self):
        marker = f"{loop.PROJECT_DIR.resolve()}:998877"
        env = dict(os.environ, MEDGEMMA_ITERATION_OWNER=marker)
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], env=env)
        try:
            self.assertIn(child.pid, loop.iteration_processes(998877))
            self.assertNotIn(child.pid, loop.iteration_processes(998876))
            self.assertIsNone(child.poll())
        finally:
            child.terminate()
            child.wait()

    def test_agent_env_tags_iteration(self):
        with patch.dict(loop.STATE, n=121):
            self.assertEqual(loop.agent_env("0,1")["MEDGEMMA_ITERATION_OWNER"],
                             f"{loop.PROJECT_DIR.resolve()}:121")

    def test_no_switch_on_stop_or_other_backend(self):
        error = loop.UsageLimitError("limit", limit_type="seven_day")
        args = argparse.Namespace(engineer="claude", engineer_fallback="codex")
        with patch.object(loop, "check_stop", side_effect=loop.StopRequested("stop")), \
                patch.object(loop, "prepare_engineer_handoff") as handoff:
            with self.assertRaises(loop.StopRequested):
                loop.fallback_engineer_after_quota(args, 1, error)
            handoff.assert_not_called()
        args.engineer = "codex"
        with self.assertRaises(loop.UsageLimitError):
            loop.fallback_engineer_after_quota(args, 1, error)


class HandoffTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    git = fixtures.WorkflowTests.git
    record = fixtures.WorkflowTests.record
    plan = fixtures.WorkflowTests.plan

    def args(self, *extra):
        with patch.object(sys, "argv", ["orchestrator.py", *extra]):
            return loop.parse_args()

    def test_fallback_persists_and_keeps_iteration_plan_and_outputs(self):
        self.plan(1)
        d = loop.iter_dir(1)
        loop.save(d / "plan.md", "원 계획")
        loop.save(d / "claude_session.txt", "old-session")
        loop.save(d / "claude_stream.jsonl", "원 로그")
        loop.save(self.repo / "partial.py", "완료된 소스")
        self.record(1, "engineer_backend.json", {"backend": "claude"})
        args = self.args("--engineer", "claude", "--engineer-fallback", "codex")
        events = []
        with patch.object(loop, "AGENT_DIR", self.root / "agent"), \
                patch.dict(loop.STATE, proc=None), patch.object(loop, "check_stop"), \
                patch.object(loop, "set_stage"), \
                patch.object(loop, "iteration_processes", side_effect=[[123], []]), \
                patch.object(loop, "sleep_with_stop", side_effect=lambda n: events.append("wait")), \
                patch.object(loop, "checkpoint_code", side_effect=lambda *a: events.append("checkpoint") or {"sha":"source"}):
            loop.configure_engineer(args)
            self.assertEqual(args.engineer_fallback, "codex")
            loop.fallback_engineer_after_quota(args, 1, loop.UsageLimitError("limit", limit_type="five_hour"))
            self.assertEqual(events[0], "wait")
            self.assertIn("checkpoint", events)
            self.assertEqual(loop.current_iteration(), 1)
            self.assertEqual(loop.engineer_backend(n=1), "codex")
            self.assertEqual((d / "plan.md").read_text(), "원 계획")
            self.assertEqual((self.repo / "partial.py").read_text(), "완료된 소스")
            self.assertEqual((d / "claude_stream.jsonl").read_text(), "원 로그")
            self.assertFalse((d / "superseded.json").exists())
            self.assertEqual(len(list((d / "engineer_handoffs").glob("*/claude_session.txt"))), 1)
            resumed = self.args()
            loop.configure_engineer(resumed)
            self.assertEqual(resumed.engineer, "codex")
            self.assertEqual(resumed.engineer_fallback, "codex")
            disabled = self.args("--engineer-fallback", "none")
            loop.configure_engineer(disabled)
            self.assertEqual(disabled.engineer_fallback, "none")

    def test_default_does_not_switch(self):
        with patch.object(loop, "AGENT_DIR", self.root / "agent"):
            args = self.args()
            loop.configure_engineer(args)
            self.assertEqual(args.engineer_fallback, "none")
            with self.assertRaises(loop.UsageLimitError):
                loop.fallback_engineer_after_quota(args, 1, loop.UsageLimitError("limit", limit_type="five_hour"))


class ScopeTests(unittest.TestCase):
    def test_scope_and_preserved_old_track(self):
        focus = (ROOT / "agent/RESEARCH_FOCUS.md").read_text()
        for term in ("MR-RATE", "MedGemma 1.5", "40~60명", "자동 라벨", "공식 test",
                     "전체 snapshot_download", "강한 단순 대안", "iter_062/064/077/078/083",
                     "--engineer-fallback codex", "--autonomy full", "--always-review"):
            self.assertIn(term, focus)
        old = (ROOT / "agent/PAUSED_GROUNDING_TRACK.md").read_text()
        for term in ("기각", "752fba411759a093129c05feadfdff75e4d9a1b3", "재개", "iter_120"):
            self.assertIn(term, old)
        self.assertTrue((ROOT / "agent/interventions/archives/20261013_mrrate_switch/RESEARCH_FOCUS.md").exists())


if __name__ == "__main__":
    unittest.main()
