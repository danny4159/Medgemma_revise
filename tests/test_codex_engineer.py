"""구현 담당 선택·스트림·재개·실패 보존. 실제 모델/GPU 호출 없음."""

import argparse
import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import codex_engineer as engine
import orchestrator as loop
import test_orchestrator_workflow as workflow


REPORT = "# 요약\n구현·실험 확인\nSELF_CHECK: PASS\nSUMMARY: 완료"


class EngineerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.args = argparse.Namespace(engineer="codex", gpus="0,1", claude_timeout=0)

    def test_cli_options_and_legacy_alias(self):
        for tier, timeout in (("--engineer-tier", "--engineer-timeout"),
                              ("--claude-tier", "--claude-timeout")):
            with patch.object(sys, "argv", ["orchestrator.py", "--engineer", "codex",
                                            tier, "heavy", timeout, "123"]):
                args = loop.parse_args()
            self.assertEqual((args.engineer, args.claude_tier, args.claude_timeout), ("codex", "heavy", 123))
        with patch.object(sys, "argv", ["orchestrator.py"]):
            self.assertIsNone(loop.parse_args().engineer)

    def test_new_and_resume_command_policy_and_stdin(self):
        for resume in (None, "saved-id"):
            with self.subTest(resume=resume):
                log = self.root / "codex_engineer_stream.jsonl"
                session = self.root / "codex_engineer_session.txt"
                prompt = "한글 입력" * 50000

                def run(cmd, log_path, timeout, env, on_line, **kwargs):
                    self.assertEqual(cmd[-1], "-")
                    self.assertNotIn(prompt, cmd)
                    self.assertIn('sandbox_mode="workspace-write"', cmd)
                    self.assertIn('approval_policy="never"', cmd)
                    self.assertIn("sandbox_workspace_write.writable_roots=[]", cmd)
                    self.assertIn("allow_login_shell=false", cmd)
                    self.assertIn("sandbox_workspace_write.network_access=true", cmd)
                    self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", cmd)
                    self.assertEqual("resume" in cmd, bool(resume))
                    if resume:
                        self.assertEqual(cmd[3], resume)
                    self.assertEqual(kwargs["cwd"], loop.RESEARCH_DIR)
                    self.assertTrue(kwargs["stdin_text"].endswith(prompt))
                    self.assertIn("SELF_CHECK", kwargs["stdin_text"])
                    self.assertEqual(timeout, 0)
                    self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0,1")
                    self.assertNotIn("CODEX_API_KEY", env)
                    self.assertNotIn("OPENAI_API_KEY", env)
                    events = [
                        {"type": "thread.started", "thread_id": "saved-id"},
                        {"type": "turn.started"},
                        {"type": "item.completed", "item": {"type": "agent_message", "text": REPORT}},
                        {"type": "turn.completed", "usage": {"input_tokens": 50, "cached_input_tokens": 30,
                                                              "output_tokens": 10}},
                    ]
                    with log_path.open("a") as f:
                        for e in events:
                            line = json.dumps(e) + "\n"
                            f.write(line)
                            on_line(line)
                            if e["type"] == "thread.started":
                                self.assertEqual(session.read_text(), "saved-id")

                with patch.object(loop, "run_streaming", side_effect=run), \
                        patch.dict(os.environ, CODEX_API_KEY="test", OPENAI_API_KEY="test"):
                    result = loop.run_codex_engineer(self.args, prompt, log, "standard", session, resume)
                self.assertEqual(result["result"], REPORT)
                self.assertEqual(result["backend"], "codex")
                usage = engine.summarize_stream(log)
                count = 2 if resume else 1
                self.assertEqual(usage["usage"]["input_tokens"], 50)  # 같은 누적값을 두 번 더하지 않음
                self.assertEqual(usage["completed_turns"], count)
                self.assertIn("Codex 구현", engine.usage_report(self.root.parent))

    def test_missing_completion_and_limit_are_not_reports(self):
        cases = [(None, loop.RetryableError), ("You've hit your usage limit", loop.UsageLimitError)]
        for message, error in cases:
            def run(cmd, log, timeout, env, on_line, **kwargs):
                on_line(json.dumps({"type": "item.completed", "item": {
                    "type": "agent_message", "text": "중간 답변"}}))
                if message:
                    on_line(json.dumps({"type": "turn.failed", "error": {"message": message}}))
            with patch.object(loop, "run_streaming", side_effect=run):
                with self.assertRaises(error):
                    loop.run_codex_engineer(self.args, "실행", self.root / "log", "light")

    def test_tool_permission_denial_is_forwarded(self):
        stream = engine.Stream()
        stream.feed({"type": "item.completed", "item": {"type": "command_execution",
                    "command": "python test.py", "exit_code": 1, "aggregated_output": "Permission denied"}})
        self.assertEqual(len(stream.permission_denials), 1)

    def test_usage_cumulative_resume_matches_real_cli_contract(self):
        path = self.root / "stream.jsonl"
        events = [
            {"type": "thread.started", "thread_id": "s1"},
            {"type": "turn.completed", "usage": {"input_tokens": 30315, "output_tokens": 88}},
            {"type": "thread.started", "thread_id": "s1"},
            {"type": "turn.completed", "usage": {"input_tokens": 61039, "output_tokens": 160}},
            {"type": "thread.started", "thread_id": "s2"},
            {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 20}},
        ]
        path.write_text("\n".join(json.dumps(e) for e in events))
        data = engine.summarize_stream(path)
        self.assertEqual(data["usage"]["input_tokens"], 61139)
        self.assertEqual(data["usage"]["output_tokens"], 180)

    def test_selection_persists_but_partial_legacy_session_cannot_switch(self):
        with patch.object(loop, "AGENT_DIR", self.root), patch.object(loop, "RUNS_DIR", self.root / "runs"), \
                patch.object(loop, "current_iteration", return_value=1):
            self.args.engineer = None
            loop.configure_engineer(self.args)
            self.assertEqual(self.args.engineer, "claude")
            self.args.engineer = "codex"
            loop.configure_engineer(self.args)
            self.args.engineer = None
            loop.configure_engineer(self.args)
            self.assertEqual(self.args.engineer, "codex")
            loop.save(loop.iter_dir(1) / "claude_session.txt", "legacy-session")
            self.args.engineer = "codex"
            with self.assertRaises(loop.AgentError):
                loop.configure_engineer(self.args)
            self.args.engineer = None
            loop.configure_engineer(self.args)
            self.assertEqual(self.args.engineer, "claude")
            loop.save(loop.iter_dir(1) / "claude_report.md", REPORT)
            self.args.engineer = None
            loop.configure_engineer(self.args)
            self.assertEqual(self.args.engineer, "codex")  # 완료한 구현 이후에는 저장된 다음 담당 적용

    def test_bind_prevents_mixed_backend_and_status_is_correct(self):
        with patch.object(loop, "RUNS_DIR", self.root / "runs"):
            self.assertEqual(loop.bind_engineer(self.args, 1), "codex")
            loop.save(loop.iter_dir(1) / "plan.md", "계획")
            loop.save(loop.iter_dir(1) / "git.json", "{}")
            self.assertEqual(loop.stage_of(1), "Codex 구현")
            self.args.engineer = "claude"
            with self.assertRaises(loop.AgentError):
                loop.bind_engineer(self.args, 1)

    def test_prepare_only_saves_selection_without_starting_loop(self):
        with patch.object(loop, "AGENT_DIR", self.root), patch.object(loop, "RUNS_DIR", self.root / "runs"), \
                patch.object(loop, "current_iteration", return_value=1), \
                patch.object(loop, "orchestrator_lock", return_value=contextlib.nullcontext()), \
                patch.object(loop, "apply_pending_replan", return_value=None), \
                patch.object(loop, "run_loop") as run, \
                patch.object(sys, "argv", ["orchestrator.py", "--prepare-only", "--engineer", "codex"]):
            loop.main()
            run.assert_not_called()
            self.assertEqual(loop.load_json(self.root / "engineer_selection.json"),
                             {"backend": "codex", "codex_engineer_sandbox": "workspace-write"})

    def test_host_permissions_require_explicit_selection_and_persist(self):
        with patch.object(loop, "AGENT_DIR", self.root), patch.object(loop, "RUNS_DIR", self.root / "runs"), \
                patch.object(loop, "current_iteration", return_value=1):
            loop.configure_engineer(self.args)
            self.assertEqual(self.args.codex_engineer_sandbox, "workspace-write")
            self.args.codex_engineer_sandbox = "danger-full-access"
            loop.configure_engineer(self.args)
            args = argparse.Namespace(engineer=None, codex_engineer_sandbox=None)
            loop.configure_engineer(args)
            self.assertEqual(args.codex_engineer_sandbox, "danger-full-access")
            spec = loop.tier_spec("codex_engineer", "standard")
            self.assertIn('sandbox_mode="workspace-write"', engine.command(spec))
            self.assertIn('sandbox_mode="danger-full-access"', engine.command(spec, "session", args.codex_engineer_sandbox))


class CodexWorkflowTests(unittest.TestCase):
    # Git 기반 기존 fixture만 재사용한다.
    setUp = workflow.WorkflowTests.setUp
    git = workflow.WorkflowTests.git
    record = workflow.WorkflowTests.record
    plan = workflow.WorkflowTests.plan

    def test_review_reads_codex_log_even_when_next_backend_is_claude(self):
        self.plan(1, claude_tier="standard")
        self.record(1, "engineer_backend.json", {"backend": "codex"})
        args = argparse.Namespace(engineer="claude", gpt_tier=None)

        def inspect(args, prompt, *a, **kw):
            self.assertIn("Codex 구현 보고서", prompt)
            self.assertIn("iter_001/codex_engineer_stream.jsonl", prompt)
            self.assertNotIn("iter_001/claude_stream.jsonl", prompt)
            raise loop.StopRequested("검토 입력 확인 완료")

        with patch.object(loop, "run_codex", side_effect=inspect):
            with self.assertRaises(loop.StopRequested):
                loop.step_review(args, "목표", 1)
    def test_codex_dispatch_cached_result_and_commit(self):
        self.plan(1, claude_tier="standard", experiment_role="method", review_mode="skip")
        args = argparse.Namespace(engineer="codex", claude_tier=None, always_review=False)

        def run(*a, **kw):
            (self.repo / "implementation.py").write_text("VALUE = 1\n")
            return {"result": REPORT, "session_id": "codex-session", "backend": "codex"}

        with patch.object(loop, "run_codex_engineer", side_effect=run) as codex, \
                patch.object(loop, "run_claude") as claude:
            loop.step_claude(args, "목표", 1)
            self.assertEqual(codex.call_count, 1)
            claude.assert_not_called()
            meta = loop.load_json(loop.iter_dir(1) / "claude_meta.json")
            self.assertEqual(meta["backend"], "codex")
            self.assertEqual(meta["stream_log"], "codex_engineer_stream.jsonl")
            self.assertEqual(self.git("show", "HEAD:implementation.py"), "VALUE = 1")
            self.assertTrue(loop.review_decision(args, 1)[0])
            # 보고서 저장 직전 중단을 모사. cached 응답으로 복원하고 모델은 재호출하지 않는다.
            (loop.iter_dir(1) / "claude_report.md").unlink()
            loop.step_claude(args, "목표", 1)
            self.assertEqual(codex.call_count, 1)

    def test_codex_failure_preserves_code_and_session_then_resumes(self):
        self.plan(1, claude_tier="standard")
        args = argparse.Namespace(engineer="codex", claude_tier=None)

        def fail(args, prompt, log, tier, session, **kwargs):
            loop.save(session, "codex-session")
            (self.repo / "partial.py").write_text("PARTIAL = True\n")
            raise loop.StopRequested("테스트 중단")

        with patch.object(loop, "run_codex_engineer", side_effect=fail):
            with self.assertRaises(loop.StopRequested):
                loop.step_claude(args, "목표", 1)
        self.assertFalse((loop.iter_dir(1) / "claude_report.md").exists())
        self.assertEqual(self.git("show", "HEAD:partial.py"), "PARTIAL = True")
        with patch.object(loop, "run_codex_engineer", return_value={"result": REPORT}) as codex:
            loop.step_claude(args, "목표", 1)
            self.assertEqual(codex.call_args.kwargs["resume_id"], "codex-session")


if __name__ == "__main__":
    unittest.main()
