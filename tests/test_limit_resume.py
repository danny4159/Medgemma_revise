"""실제 모델·시간 대기 없이 구조화된 한도 판정과 자동 재개를 검증한다."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import orchestrator as loop


MESSAGE = "You've hit your monthly spend limit · your session limit resets 9:20pm (Asia/Seoul)"


class LimitResumeTests(unittest.TestCase):
    def setUp(self):
        self.info = {"status": "rejected", "rateLimitType": "five_hour", "resetsAt": 2000}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        state = patch.dict(loop.STATE, n=None, limit_wait=None, limit_retry_at=None)
        state.start()
        self.addCleanup(state.stop)

    def test_structured_rejection_beats_conflicting_monthly_message(self):
        for kind in ("five_hour", "seven_day"):
            error = loop.failure_error("exit 1", MESSAGE, limit_info={**self.info, "rateLimitType": kind})
            self.assertIsInstance(error, loop.UsageLimitError)
            self.assertEqual(error.limit_type, kind)
            self.assertEqual(error.reset_at, 2000)

    def test_warnings_unknown_or_missing_metadata_do_not_override_spend_limit(self):
        for info in (None, {}, [], {**self.info, "status": "allowed_warning"},
                     {**self.info, "status": "allowed"}, {**self.info, "rateLimitType": "monthly"}):
            with self.subTest(info=info):
                self.assertIsInstance(loop.failure_error("exit", MESSAGE, limit_info=info), loop.SpendLimitError)

    def test_invalid_reset_falls_back_to_polling(self):
        for value in (None, True, "tomorrow", float('nan'), float('inf'), -1, 10**20):
            error = loop.failure_error("exit", MESSAGE, limit_info={**self.info, "resetsAt": value})
            self.assertIsNone(error.reset_at)
            with patch.dict(loop.LIMIT, poll=1800, max=28800):
                self.assertEqual(loop.usage_retry_delay(error, 0), 1800)

    def test_reset_then_poll_then_success_records_wait_and_resume(self):
        error = loop.failure_error("exit", MESSAGE, limit_info=self.info)
        clock = [1000]
        delays = []
        def sleep(seconds):
            delays.append(seconds)
            clock[0] += seconds
        with patch.dict(loop.STATE, n=26), patch.dict(loop.LIMIT, poll=1800, max=28800), \
                patch.object(loop.time, "time", side_effect=lambda: clock[0]), \
                patch.object(loop, "sleep_with_stop", side_effect=sleep), \
                patch.object(loop, "record_event") as event, patch.object(loop, "notify") as notify:
            from unittest.mock import Mock
            fn = Mock(side_effect=[error, error, "done"])
            self.assertEqual(loop.with_retries("Claude", fn), "done")
            self.assertEqual(delays, [1061, 1800])
            self.assertEqual(fn.call_count, 3)
            self.assertEqual([c.args[1] for c in event.call_args_list], ['limit_wait', 'limit_wait', 'limit_resume'])
            self.assertIn('재시도', notify.call_args_list[0].args[0])
            self.assertIsNone(loop.STATE['limit_wait'])
            self.assertIsNone(loop.STATE['limit_retry_at'])

    def test_reset_beyond_budget_stops_without_early_model_retry(self):
        error = loop.failure_error("exit", MESSAGE, limit_info={**self.info, "resetsAt": 999999})
        with patch.dict(loop.LIMIT, poll=1800, max=28800), patch.object(loop.time, "time", return_value=1000), \
                patch.object(loop, "sleep_with_stop") as sleep, patch.object(loop, "notify"):
            from unittest.mock import Mock
            fn = Mock(side_effect=error)
            with self.assertRaisesRegex(loop.AgentError, '대기 상한'):
                loop.with_retries("Claude", fn)
            fn.assert_called_once()
            sleep.assert_called_once_with(28800)

    def test_stop_during_wait_prevents_retry(self):
        error = loop.failure_error("exit", MESSAGE, limit_info=self.info)
        with patch.object(loop, "sleep_with_stop", side_effect=loop.StopRequested('stop')), \
                patch.object(loop, "notify"):
            from unittest.mock import Mock
            fn = Mock(side_effect=error)
            with self.assertRaises(loop.StopRequested):
                loop.with_retries("Claude", fn)
            fn.assert_called_once()

    def test_claude_nonzero_and_result_error_use_latest_event(self):
        for nonzero in (True, False):
            with self.subTest(nonzero=nonzero):
                def run(cmd, log, timeout, env, on_line, **kwargs):
                    on_line(json.dumps({'type':'rate_limit_event', 'rate_limit_info':self.info}))
                    on_line(json.dumps({'type':'result', 'is_error':True, 'result':MESSAGE}))
                    if nonzero:
                        raise loop.SpendLimitError(MESSAGE)
                with patch.object(loop, "resource_context", return_value=''), \
                        patch.object(loop, "run_streaming", side_effect=run):
                    with self.assertRaises(loop.UsageLimitError) as caught:
                        loop.run_claude(argparse.Namespace(gpus='0,1', claude_timeout=0), '작업',
                                        self.root / 'stream', 'standard')
                    self.assertEqual(caught.exception.reset_at, 2000)

    def test_latest_allowed_event_and_new_call_do_not_reuse_rejection(self):
        for recover in (False, True):
            def run(cmd, log, timeout, env, on_line, **kwargs):
                if recover:
                    on_line(json.dumps({'type':'rate_limit_event', 'rate_limit_info':self.info}))
                on_line(json.dumps({'type':'rate_limit_event', 'rate_limit_info':{**self.info, 'status':'allowed'}}))
                raise loop.SpendLimitError(MESSAGE)
            with patch.object(loop, "resource_context", return_value=''), \
                    patch.object(loop, "run_streaming", side_effect=run):
                with self.assertRaises(loop.SpendLimitError):
                    loop.run_claude(argparse.Namespace(gpus=None, claude_timeout=0), '작업',
                                    self.root / 'stream', 'standard')

    def test_timeout_not_reclassified_by_rate_limit_event(self):
        def run(cmd, log, timeout, env, on_line, **kwargs):
            on_line(json.dumps({'type':'rate_limit_event', 'rate_limit_info':self.info}))
            raise loop.AgentError('시간 초과')
        with patch.object(loop, "resource_context", return_value=''), patch.object(loop, "run_streaming", side_effect=run):
            with self.assertRaisesRegex(loop.AgentError, '시간 초과') as caught:
                loop.run_claude(argparse.Namespace(gpus=None, claude_timeout=1), '작업', self.root / 'stream', 'standard')
            self.assertNotIsInstance(caught.exception, loop.UsageLimitError)
