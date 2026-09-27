"""GPU·외부 에이전트 없이 자원 정책 전달과 timeout 동작을 검증한다."""

import argparse
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import orchestrator as loop


class ResourcePolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.policy = self.root / "RESOURCE_POLICY.md"
        self.policy.write_text("현재 허용된 두 GPU를 활용한다.", encoding="utf-8")
        self.args = argparse.Namespace(gpus="0,1", gpt_timeout=30, claude_timeout=0)
        self.patch_policy = patch.object(loop, "RESOURCE_POLICY_FILE", self.policy)
        self.patch_policy.start()
        self.addCleanup(self.patch_policy.stop)
        self.research_policy = self.root / "RESEARCH_POLICY.md"
        self.research_policy.write_text("가설 실패와 코드 보존을 분리한다.", encoding="utf-8")
        research_patch = patch.object(loop, "RESEARCH_POLICY_FILE", self.research_policy)
        research_patch.start()
        self.addCleanup(research_patch.stop)
        self.usage_policy = self.root / "CLAUDE_USAGE_POLICY.md"
        self.usage_policy.write_text("일반 구현은 standard, 필수 검증 유지", encoding="utf-8")
        usage_patch = patch.object(loop, "CLAUDE_USAGE_POLICY_FILE", self.usage_policy)
        usage_patch.start()
        self.addCleanup(usage_patch.stop)
        self.reporting_style = self.root / "REPORTING_STYLE.md"
        self.reporting_style.write_text("핵심 먼저, 상세 검증 유지", encoding="utf-8")
        style_patch = patch.object(loop, "REPORTING_STYLE_FILE", self.reporting_style)
        style_patch.start()
        self.addCleanup(style_patch.stop)

    def test_codex_receives_policy_and_retains_read_only(self):
        output = self.root / "plan.json"

        def run(cmd, *args, **kwargs):
            self.assertEqual(cmd[-1], "-")
            payload = kwargs["stdin_text"]
            self.assertIn("현재 허용된 두 GPU", payload)
            self.assertIn("가설 실패와 코드 보존", payload)
            self.assertIn("일반 구현은 standard", payload)
            self.assertIn("핵심 먼저, 상세 검증 유지", payload)
            self.assertTrue(payload.endswith("실험 계획"))
            self.assertEqual(cmd[cmd.index("-s") + 1], "read-only")
            output.write_text("{}", encoding="utf-8")

        with patch.object(loop, "run_streaming", side_effect=run):
            self.assertEqual(loop.run_codex(self.args, "실험 계획", output, self.root / "log", "deep"), "{}")

    def test_claude_resume_reloads_policy(self):
        commands = []

        def run(cmd, log, timeout, env, on_line, **kwargs):
            commands.append(cmd)
            on_line('{"type":"result","result":"완료","is_error":false}')

        with patch.object(loop, "run_streaming", side_effect=run):
            loop.run_claude(self.args, "구현", self.root / "log", "heavy")
            self.policy.write_text("수정된 자원 정책", encoding="utf-8")
            self.research_policy.write_text("수정된 연구 운영 정책", encoding="utf-8")
            self.usage_policy.write_text("수정된 사용량 정책", encoding="utf-8")
            self.reporting_style.write_text("수정된 보고서 기준", encoding="utf-8")
            loop.run_claude(self.args, "재개", self.root / "log", "heavy", resume_id="session")
        self.assertIn("현재 허용된 두 GPU", commands[0][-1])
        self.assertIn("핵심 먼저, 상세 검증 유지", commands[0][-1])
        self.assertIn("수정된 자원 정책", commands[1][-1])
        self.assertIn("수정된 연구 운영 정책", commands[1][-1])
        self.assertIn("수정된 사용량 정책", commands[1][-1])
        self.assertIn("수정된 보고서 기준", commands[1][-1])
        self.assertEqual(commands[1][commands[1].index("--resume") + 1], "session")

    def test_inherited_gpu_restriction_and_explicit_timeout(self):
        self.args.gpus = None
        self.args.claude_timeout = 7200
        with patch.dict(os.environ, {"CUDA_VISIBLE_DEVICES": "1"}):
            text = loop.resource_context(self.args)
            self.assertIn("CUDA_VISIBLE_DEVICES: 1\n", text)
            self.assertIn("7200초", text)
            self.assertEqual(loop.agent_env(None)["CUDA_VISIBLE_DEVICES"], "1")

    def test_missing_policy_fails_before_agent_run(self):
        self.policy.unlink()
        with patch.object(loop, "run_streaming") as run:
            with self.assertRaises(loop.AgentError):
                loop.run_claude(self.args, "구현", self.root / "log", "heavy")
            run.assert_not_called()

    def test_resume_includes_current_goal_and_feedback(self):
        (self.root / "snapshot_before.json").write_text("{}", encoding="utf-8")
        (self.root / "claude_session.txt").write_text("old-session", encoding="utf-8")
        (self.root / "human_to_claude.md").write_text("새 추가 지시", encoding="utf-8")
        (self.root / "execution_amendment.md").write_text("재개 보완 지시", encoding="utf-8")
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(loop, "iter_dir", return_value=self.root))
            stack.enter_context(patch.object(loop, "ensure_branch", return_value={"branch": "test"}))
            stack.enter_context(patch.object(loop.history, "begin"))
            stack.enter_context(patch.object(loop.history, "prepare_assets"))
            stack.enter_context(patch.object(loop, "checkpoint_code"))
            stack.enter_context(patch.object(loop, "claude_tier", return_value="heavy"))
            stack.enter_context(patch.object(loop, "record_tier"))
            stack.enter_context(patch.object(loop, "record_event"))
            stack.enter_context(patch.object(loop, "with_retries", side_effect=lambda name, call: call()))
            run = stack.enter_context(patch.object(loop, "run_claude", side_effect=RuntimeError("검증용 종료")))
            with self.assertRaisesRegex(RuntimeError, "검증용 종료"):
                loop.step_claude(self.args, "현재 연구 목표", 8)
        prompt = run.call_args.args[1]
        self.assertIn("현재 연구 목표", prompt)
        self.assertIn("새 추가 지시", prompt)
        self.assertIn("재개 보완 지시", prompt)
        self.assertIn(str(self.root / "plan.md"), prompt)
        self.assertEqual(run.call_args.kwargs["resume_id"], "old-session")

    def test_missing_research_policy_fails_before_agent_run(self):
        self.research_policy.unlink()
        with patch.object(loop, "run_streaming") as run:
            with self.assertRaises(loop.AgentError):
                loop.run_claude(self.args, "구현", self.root / "log", "heavy")
            run.assert_not_called()


class TimeoutTests(unittest.TestCase):
    def test_zero_timeout_does_not_create_kill_timer(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(loop.threading, "Timer") as timer:
                lines = []
                loop.run_streaming([sys.executable, "-c", "print('ok')"],
                                   Path(directory) / "log", 0, os.environ.copy(), lines.append)
                timer.assert_not_called()
                self.assertEqual("".join(lines).strip(), "ok")
        self.assertIsNone(loop.STATE["proc"])

    def test_positive_timeout_still_terminates_process(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(loop.AgentError, "시간 초과"):
                loop.run_streaming([sys.executable, "-c", "import time; time.sleep(2)"],
                                   Path(directory) / "log", 0.05, os.environ.copy(), lambda line: None)
        self.assertIsNone(loop.STATE["proc"])

    def test_cli_default_and_explicit_timeout(self):
        with patch.object(sys, "argv", ["orchestrator.py"]):
            self.assertEqual(loop.parse_args().claude_timeout, 0)
        with patch.object(sys, "argv", ["orchestrator.py", "--claude-timeout", "7200"]):
            self.assertEqual(loop.parse_args().claude_timeout, 7200)
        with patch.object(sys, "argv", ["orchestrator.py", "--claude-timeout", "-1"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                loop.parse_args()
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
