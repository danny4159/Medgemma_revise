"""외부 모델 호출 없이 read-only 재연결 timeout의 한정 복구를 검증한다."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import orchestrator as loop


class CodexTimeoutRecoveryTests(unittest.TestCase):
    cmd = ["codex", "exec", "-s", "read-only", "-"]

    def classify(self, tail, cmd=None):
        return loop.stream_timeout_error(cmd or self.cmd, Path("plan.log"), 1800, tail)

    def test_last_reconnect_is_retryable(self):
        for option in ("-s", "--sandbox"):
            error = self.classify(["ERROR: Reconnecting... 2/5\n", "ERROR: Reconnecting... 3/5\n", "\n"],
                                  ["/opt/bin/codex", "exec", option, "read-only", "-"])
            self.assertIsInstance(error, loop.RetryableError)
            self.assertNotIsInstance(error, loop.UsageLimitError)

    def test_plain_timeout_or_recovered_stream_is_not_retried(self):
        for tail in ([], ["thinking\n"], ["ERROR: Reconnecting... 2/5\n", "exec\n"],
                     ["quoted ERROR: Reconnecting... 2/5"], ["ERROR: Unauthorized"]):
            self.assertIs(type(self.classify(tail)), loop.AgentError)

    def test_engineers_and_other_commands_keep_timeout_semantics(self):
        for cmd in (["claude", "-p"], ["codex", "exec", "-s", "workspace-write"],
                    ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"],
                    ["python", "exec", "-s", "read-only"]):
            self.assertIs(type(self.classify(["ERROR: Reconnecting... 3/5"], cmd)), loop.AgentError)

    def test_streaming_timeout_routes_reconnect_and_preserves_log(self):
        popen = subprocess.Popen
        child = "import time; print('ERROR: Reconnecting... 3/5', flush=True); time.sleep(10)"
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "plan.log"
            log.write_text("previous attempt\n", encoding="utf-8")
            with patch.object(loop.subprocess, "Popen",
                              side_effect=lambda cmd, **kw: popen([sys.executable, "-c", child], **kw)), \
                    patch.dict(loop.STATE, {"stop_now": False, "proc": None}):
                with self.assertRaises(loop.RetryableError):
                    loop.run_streaming(self.cmd, log, 0.5, os.environ.copy(), lambda line: None,
                                       stdin_text="test")
                self.assertIsNone(loop.STATE["proc"])
            self.assertIn("previous attempt", log.read_text())
            self.assertIn("ERROR: Reconnecting... 3/5", log.read_text())

    def test_existing_bounded_retry_is_used(self):
        error = self.classify(["ERROR: Reconnecting... 3/5"])
        with patch.object(loop, "sleep_with_stop") as sleep, patch.object(loop, "notify"), \
                patch.dict(loop.STATE, {"limit_wait": None, "limit_retry_at": None}):
            with patch.object(loop, "run_codex", side_effect=[error, "done"]) as run:
                self.assertEqual(loop.with_retries("GPT", run), "done")
            sleep.assert_called_once_with(loop.RETRY_DELAYS[0])
            with patch.object(loop, "run_codex", side_effect=error) as run:
                with self.assertRaisesRegex(loop.AgentError, "다시 시도했지만 실패"):
                    loop.with_retries("GPT", run)
                self.assertEqual(run.call_count, len(loop.RETRY_DELAYS) + 1)


if __name__ == "__main__":
    unittest.main()
