"""장문 입력 무손실 전달·실행 실패 기록·Telegram 경로. 실제 모델/통신은 호출하지 않는다."""

import argparse
import contextlib
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import orchestrator as loop
from notifier import Human


class PromptTransportTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.log = self.root / "plan_codex.log"
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(loop.STATE, proc=None, stop_now=False))

    def test_codex_long_unicode_input_preserves_all_bytes_and_options(self):
        # 명령행 단일 인자 한도(약 128 KiB)보다 큰 입력을 실제 자식 프로세스로 전달한다.
        policy = "정책: 목표·권한·원본 보존\n"
        prompt = "  시작\r\n" + "한글🙂 '따옴표' \"JSON\" $변수\\경로\n" * 12000 + "끝  \n"
        payload = (policy + prompt).encode("utf-8")
        self.assertGreater(len(payload), 131072)
        output = self.root / "raw.json"
        schema = self.root / "schema.json"
        args = argparse.Namespace(gpus="0,1", gpt_timeout=10, claude_timeout=0)
        original = loop.run_streaming
        child = ("import sys,hashlib,json; from pathlib import Path; d=sys.stdin.buffer.read(); "
                 "Path(sys.argv[1]).write_text(json.dumps({'bytes':len(d),'sha256':hashlib.sha256(d).hexdigest()})); "
                 "print('완료')")

        def run(cmd, log, timeout, env, on_line, **kwargs):
            self.assertEqual(cmd[-1], "-")
            self.assertEqual(cmd[cmd.index("-s") + 1], "read-only")
            self.assertEqual(cmd[cmd.index("--output-schema") + 1], str(schema))
            self.assertEqual(cmd[cmd.index("-m") + 1], loop.tier_spec("gpt", "deep")["model"])
            self.assertIn('web_search="live"', cmd)
            self.assertIn('model_reasoning_effort="high"', cmd)
            self.assertNotIn(prompt, cmd)
            self.assertEqual(kwargs["stdin_text"].encode("utf-8"), payload)
            return original([sys.executable, "-c", child, str(output)], log, timeout, env,
                            on_line, cwd=self.root, **kwargs)

        with patch.object(loop, "resource_context", return_value=policy), \
                patch.object(loop, "run_streaming", side_effect=run):
            result = json.loads(loop.run_codex(args, prompt, output, self.log, "deep", schema))
        self.assertEqual(result, {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
        log = self.log.read_text()
        self.assertIn(f"bytes={len(payload)}", log)
        self.assertIn(result["sha256"], log)
        self.assertNotIn("목표·권한·원본 보존", log)
        self.assertIsNone(loop.STATE["proc"])

    def test_claude_long_input_and_resume_preserve_bytes_options_and_session(self):
        policy = "정책 원문\n"
        prompt = "  시작\r\n" + "한글🙂 '$변수' \\\n" * 15000 + "끝  \n"
        payload = (policy + prompt).encode("utf-8")
        self.assertGreater(len(payload), 131072)
        args = argparse.Namespace(gpus="0,1", claude_timeout=10)
        original = loop.run_streaming
        child = (
            "import sys,hashlib,json; d=sys.stdin.buffer.read(); "
            "print(json.dumps({'type':'system','session_id':'saved-session'})); "
            "print(json.dumps({'type':'result','is_error':False,"
            "'result':{'bytes':len(d),'sha256':hashlib.sha256(d).hexdigest()}}))"
        )
        for resume in (None, "saved-session"):
            with self.subTest(resume=resume):
                session = self.root / "session.txt"

                def run(cmd, log, timeout, env, on_line, **kwargs):
                    self.assertEqual(cmd[:2], ["claude", "-p"])
                    for flag, value in (("--input-format", "text"),
                                        ("--output-format", "stream-json"),
                                        ("--permission-mode", "acceptEdits"),
                                        ("--model", "sonnet"), ("--effort", "medium"),
                                        ("--settings", str(loop.AGENT_DIR / "claude_settings.json")),
                                        ("--append-system-prompt-file", str(loop.PROMPT_DIR / "claude_engineer.md")),
                                        ("--add-dir", str(loop.PROJECT_DIR))):
                        self.assertEqual(cmd[cmd.index(flag) + 1], value)
                    if resume:
                        self.assertEqual(cmd[cmd.index("--resume") + 1], resume)
                    else:
                        self.assertNotIn("--resume", cmd)
                    self.assertNotIn(policy + prompt, cmd)
                    self.assertLess(max(len(v.encode()) for v in cmd), 131072)
                    self.assertEqual(kwargs["stdin_text"].encode(), payload)
                    self.assertEqual(kwargs["cwd"], loop.RESEARCH_DIR)
                    self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0,1")
                    kwargs["cwd"] = self.root
                    return original([sys.executable, "-c", child], log, timeout, env, on_line, **kwargs)

                with patch.object(loop, "resource_context", return_value=policy), \
                        patch.object(loop, "run_streaming", side_effect=run):
                    result = loop.run_claude(args, prompt, self.log, "standard", session, resume)
                self.assertEqual(session.read_text(), "saved-session")
                self.assertEqual(result["result"], {"bytes": len(payload),
                                                  "sha256": hashlib.sha256(payload).hexdigest()})

    def test_output_before_reading_large_input_does_not_deadlock(self):
        prompt = "입력\n" * 50000
        lines = []
        child = ("import sys; sys.stdout.write('x'*200000+'\\n'); sys.stdout.flush(); "
                 "print(len(sys.stdin.buffer.read()))")
        loop.run_streaming([sys.executable, "-c", child], self.log, 10, os.environ.copy(),
                           lines.append, stdin_text=prompt)
        self.assertEqual(int(lines[-1]), len(prompt.encode()))

    def test_no_input_and_empty_input_reach_eof(self):
        for value in (None, ""):
            lines = []
            loop.run_streaming([sys.executable, "-c", "import sys; print(len(sys.stdin.buffer.read()))"],
                               self.log, 10, os.environ.copy(), lines.append, stdin_text=value)
            self.assertEqual("".join(lines), "0\n")

    def test_temporary_input_is_closed_after_success_and_nonzero_exit(self):
        create_file = tempfile.TemporaryFile
        handles = []

        def create(*args, **kwargs):
            handle = create_file(*args, **kwargs)
            handles.append(handle)
            return handle

        with patch.object(loop.tempfile, "TemporaryFile", side_effect=create):
            loop.run_streaming([sys.executable, "-c", "print('ok')"], self.log, 10,
                               os.environ.copy(), lambda line: None, stdin_text="원문")
            with self.assertRaises(loop.RetryableError):
                loop.run_streaming([sys.executable, "-c", "raise SystemExit(2)"], self.log, 10,
                                   os.environ.copy(), lambda line: None, stdin_text="원문")
        self.assertEqual(len(handles), 2)
        self.assertTrue(all(handle.closed for handle in handles))
        self.assertIsNone(loop.STATE["proc"])

    def test_timeout_still_works_with_large_unread_input(self):
        with self.assertRaisesRegex(loop.AgentError, "시간 초과"):
            loop.run_streaming([sys.executable, "-c", "import time; time.sleep(20)"], self.log, 0.1,
                               os.environ.copy(), lambda line: None, stdin_text="긴 입력" * 50000)
        self.assertIsNone(loop.STATE["proc"])

    def test_launch_errors_are_non_retryable_and_do_not_expose_prompt(self):
        for number in (errno.E2BIG, errno.ENOENT, errno.EACCES):
            with self.subTest(errno=number), patch.object(loop.subprocess, "Popen",
                    side_effect=OSError(number, os.strerror(number))):
                with self.assertRaises(loop.AgentError) as raised:
                    loop.run_streaming(["codex", "exec", "-"], self.log, 0, os.environ.copy(),
                                       lambda line: None, stdin_text="알림에 나오면 안 되는 원문")
            self.assertNotIsInstance(raised.exception, loop.RetryableError)
            self.assertIn(f"errno={number}", str(raised.exception))
            self.assertNotIn("알림에 나오면 안 되는 원문", str(raised.exception))
            self.assertIsNone(loop.STATE["proc"])
        self.assertIn("[launch_error]", self.log.read_text())

    def test_input_storage_failure_is_reported_before_launch(self):
        with patch.object(loop.tempfile, "TemporaryFile", side_effect=OSError(errno.ENOSPC, "No space")), \
                patch.object(loop.subprocess, "Popen") as launch, self.assertRaises(loop.AgentError):
            loop.run_streaming(["codex"], self.log, 0, os.environ.copy(), lambda line: None,
                               stdin_text="원문")
        launch.assert_not_called()


class FailureNotificationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(loop, "RUNS_DIR", self.root / "runs"))
        stack.enter_context(patch.dict(loop.STATE, n=18, stage="GPT 사고 라운드 2", proc=None, stop_now=False))
        stack.enter_context(patch.object(loop, "rebuild_index"))
        stack.enter_context(patch.object(loop, "commit_records"))
        human = Human.__new__(Human)
        human.telegram, human.chat_id, human.warned = True, "test-chat", False
        stack.enter_context(patch.object(loop, "HUMAN", human))
        self.api = stack.enter_context(patch.object(human, "_api", return_value={"ok": True}))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

    def assert_stopped_and_notified(self):
        event = json.loads((self.root / "runs/iter_018/events.jsonl").read_text())
        self.assertEqual(event["stage"], "stopped")
        self.assertEqual(event["during"], "GPT 사고 라운드 2")
        self.api.assert_called_once()
        method, params = self.api.call_args.args
        self.assertEqual(method, "sendMessage")
        self.assertIn("중단", params["text"])
        return event, params["text"]

    def test_launch_error_reaches_record_and_telegram(self):
        def main():
            loop.run_streaming(["codex", "exec", "-"], self.root / "call.log", 0,
                               os.environ.copy(), lambda line: None, stdin_text="원문")

        with patch.object(loop, "main", side_effect=main), \
                patch.object(loop.subprocess, "Popen", side_effect=OSError(errno.E2BIG, "Argument list too long")):
            self.assertEqual(loop.cli_main(), 1)
        event, text = self.assert_stopped_and_notified()
        self.assertIn("errno=7", event["reason"])
        self.assertIn("errno=7", text)

    def test_unexpected_exception_is_recorded_and_notified_without_message_leak(self):
        with patch.object(loop, "main", side_effect=RuntimeError("민감할 수 있는 상세 메시지")):
            self.assertEqual(loop.cli_main(), 1)
        event, text = self.assert_stopped_and_notified()
        self.assertIn("RuntimeError", event["reason"])
        self.assertIn("RuntimeError", text)
        self.assertNotIn("민감할 수 있는", text)

    def test_interrupt_and_normal_exit_codes_are_unchanged(self):
        with patch.object(loop, "main", return_value=None):
            self.assertEqual(loop.cli_main(), 0)
        self.api.assert_not_called()
        with patch.object(loop, "main", side_effect=KeyboardInterrupt):
            self.assertEqual(loop.cli_main(), 130)
        event = json.loads((self.root / "runs/iter_018/events.jsonl").read_text())
        self.assertEqual(event["reason"], "Ctrl+C")


if __name__ == "__main__":
    unittest.main()
