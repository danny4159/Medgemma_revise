"""실제 모델·GPU·Telegram 없이 무제한 루프와 기존 종료 조건을 검증한다."""

import contextlib
import io
import sys
import unittest
from unittest.mock import patch

import orchestrator as loop
import test_orchestrator_workflow as fixtures


class ContinuousLoopTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    git = fixtures.WorkflowTests.git
    record = fixtures.WorkflowTests.record
    plan = fixtures.WorkflowTests.plan

    def arguments(self, *options):
        with patch.object(sys, "argv", ["orchestrator.py", *options]):
            return loop.parse_args()

    def simulate(self, verdicts, *options, fail_at=None, stop_at=None):
        args = self.arguments(*options)
        planned = []

        def plan(args, goal, n):
            if n > len(verdicts):
                raise AssertionError("종료 조건을 지나 다음 반복을 시작함")
            planned.append(n)
            self.plan(n, experiment_role="diagnostic")
            (loop.iter_dir(n) / "plan.md").write_text("계획", encoding="utf-8")

        def implement(args, goal, n):
            if n == fail_at:
                raise loop.AgentError("복구 불가능 오류")
            if n == stop_at:
                raise loop.StopRequested("사용자 정지")
            (loop.iter_dir(n) / "claude_report.md").write_text("실행 보고서", encoding="utf-8")

        def review(args, goal, n):
            self.record(n, "review.json", {"verdict": verdicts[n - 1], "one_line_summary": "결과",
                                          "approach_status": "inconclusive"})

        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(loop, "STOP_FILE", self.root / "STOP"))
            human = stack.enter_context(patch.object(loop, "Human"))
            human.return_value.telegram = False
            stack.enter_context(patch.object(loop, "HUMAN", None))
            stack.enter_context(patch.object(loop, "load_goal", return_value=("유지할 목표", False)))
            stack.enter_context(patch.object(loop, "code_version", return_value="test"))
            for name in ("ensure_research_repo", "set_stage", "check_stop", "handle_paper",
                         "step_commit", "handle_milestone", "commit_records"):
                stack.enter_context(patch.object(loop, name))
            stack.enter_context(patch.object(loop, "step_checkpoint", return_value="go"))
            stack.enter_context(patch.object(loop, "review_decision", return_value=(True, "필수 리뷰")))
            stack.enter_context(patch.object(loop, "step_plan", side_effect=plan))
            stack.enter_context(patch.object(loop, "step_claude", side_effect=implement))
            stack.enter_context(patch.object(loop, "step_review", side_effect=review))
            decision = stack.enter_context(patch.object(loop, "handle_needs_human", return_value=False))
            notify = stack.enter_context(patch.object(loop, "notify"))
            loop.run_loop(args)
            return planned, [call.args[0] for call in notify.call_args_list], decision.call_count

    def test_default_is_unlimited_but_still_smart(self):
        args = self.arguments()
        self.assertEqual(args.max_iters, 0)
        self.assertEqual(args.autonomy, "smart")
        self.assertIsNone(args.no_ask_until)

    def test_explicit_limit_and_zero(self):
        self.assertEqual(self.arguments("--max-iters", "3").max_iters, 3)
        self.assertEqual(self.arguments("--max-iters", "0").max_iters, 0)

    def test_negative_limit_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            self.arguments("--max-iters", "-1")
        self.assertEqual(error.exception.code, 2)

    def test_default_continues_past_three_and_stops_on_done(self):
        planned, notices, _ = self.simulate(["CONTINUE"] * 4 + ["DONE"])
        self.assertEqual(planned, [1, 2, 3, 4, 5])
        self.assertIn("반복 횟수 제한 없이", notices[0])
        self.assertFalse(any("최대 반복 수" in text for text in notices))
        self.assertTrue((loop.iter_dir(5) / "done.json").exists())

    def test_positive_limit_still_stops(self):
        planned, notices, _ = self.simulate(["CONTINUE"] * 4, "--max-iters", "3")
        self.assertEqual(planned, [1, 2, 3])
        self.assertTrue(any("최대 반복 수(3)" in text for text in notices))

    def test_human_decision_not_bypassed(self):
        planned, _, decisions = self.simulate(["CONTINUE", "NEEDS_HUMAN"])
        self.assertEqual(planned, [1, 2])
        self.assertEqual(decisions, 1)
        self.assertFalse((loop.iter_dir(2) / "done.json").exists())

    def test_unrecoverable_error_still_exits(self):
        with self.assertRaisesRegex(loop.AgentError, "복구 불가능"):
            self.simulate(["CONTINUE"] * 2, fail_at=2)
        self.assertFalse((loop.iter_dir(2) / "done.json").exists())

    def test_stop_request_still_exits(self):
        with self.assertRaisesRegex(loop.StopRequested, "사용자 정지"):
            self.simulate(["CONTINUE"] * 2, stop_at=2)
        self.assertFalse((loop.iter_dir(2) / "done.json").exists())


if __name__ == "__main__":
    unittest.main()
