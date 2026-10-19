"""같은 iter 인계와 리뷰 후 승인. 실제 모델·Telegram·GPU 호출 없음."""
import argparse
import contextlib
import json
import sys
import unittest
from unittest.mock import patch

import orchestrator as loop
import test_orchestrator_workflow as fixtures


class BoundaryTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    git = fixtures.WorkflowTests.git
    record = fixtures.WorkflowTests.record
    plan = fixtures.WorkflowTests.plan

    def review(self, verdict="CONTINUE"):
        self.plan(1)
        for name in ("plan.md", "claude_report.md"):
            loop.save(loop.iter_dir(1) / name, "내용")
        value = {"verdict": verdict, "one_line_summary": "관찰은 유망하나 불확정",
                 "reason": "표본이 작음", "next_task": "기존 출력부터 분석",
                 "approach_status": "inconclusive"}
        self.record(1, "review.json", value)
        return value

    def args(self, *extra):
        with patch.object(sys, "argv", ["orchestrator.py", *extra]):
            return loop.parse_args()

    def test_default_off_explicit_on_and_done_not_gated(self):
        review = self.review()
        self.assertFalse(loop.boundary_confirmation_required(self.args(), 1, review))
        for extra in ([], ["--auto"], ["--no-ask-until", "23:59"]):
            args = self.args("--confirm-each-iter", *extra)
            self.assertTrue(loop.boundary_confirmation_required(args, 1, review))
            self.assertFalse(loop.boundary_confirmation_required(args, 1, {"verdict": "DONE"}))

    def test_pause_no_next_directory_and_no_implicit_approval(self):
        review = self.review()
        with patch.object(loop, "ask", return_value="q"), patch.object(loop, "set_stage"):
            self.assertFalse(loop.confirm_next_iteration(review, 1))
        self.assertEqual(loop.current_iteration(), 1)
        self.assertFalse(loop.iter_dir(2).exists())
        self.assertFalse((loop.iter_dir(1) / "done.json").exists())
        self.assertEqual(loop.stage_of(1), "다음 반복 승인 대기")
        self.assertTrue(loop.boundary_confirmation_required(self.args("--auto"), 1, review))
        with patch.object(loop, "ask", return_value=None), patch.object(loop, "set_stage"):
            self.assertFalse(loop.confirm_next_iteration(review, 1))

    def test_feedback_persists_without_advancing_and_approved_restart_no_reask(self):
        review = self.review()
        with patch.object(loop, "ask", side_effect=["f", "f 학습 말고 오류 분석부터"]) as ask, \
                patch.object(loop, "set_stage"):
            self.assertTrue(loop.confirm_next_iteration(review, 1))
        message = ask.call_args.args[1]
        for term in ("이번에 확인한 것", "의미·남은 한계", "추천하는 다음 작업", "ok", "f 수정할 내용", "q"):
            self.assertIn(term, message)
        self.assertEqual(loop.current_iteration(), 1)
        self.assertIn("학습 말고 오류 분석부터", loop.next_iteration_feedback(2))
        with patch.object(loop, "ask", side_effect=AssertionError("중복 승인 요청")):
            self.assertTrue(loop.confirm_next_iteration(review, 1))
        self.record(1, "done.json", {"verdict": "CONTINUE"})
        self.assertEqual(loop.current_iteration(), 2)

    def test_changed_review_requires_fresh_approval_and_preserves_old(self):
        review = self.review()
        with patch.object(loop, "ask", return_value="ok"), patch.object(loop, "set_stage"):
            self.assertTrue(loop.confirm_next_iteration(review, 1))
        review["next_task"] = "다른 질문 검토"
        with patch.object(loop, "ask", return_value="q") as ask, patch.object(loop, "set_stage"):
            self.assertFalse(loop.confirm_next_iteration(review, 1))
            ask.assert_called_once()
        self.assertEqual(len(list((loop.iter_dir(1) / "boundary_decisions").glob("*.json"))), 1)

    def test_full_loop_stops_at_boundary_even_full_and_needs_human(self):
        for verdict in ("CONTINUE", "NEEDS_HUMAN"):
            with self.subTest(verdict=verdict):
                self.review(verdict)
                args = self.args("--confirm-each-iter", "--auto", "--max-iters", "2")
                with contextlib.ExitStack() as stack:
                    for name in ("configure_engineer", "ensure_research_repo", "set_stage", "check_stop",
                                 "handle_paper", "step_commit", "handle_milestone", "commit_records"):
                        stack.enter_context(patch.object(loop, name))
                    stack.enter_context(patch.object(loop, "STOP_FILE", self.root / "STOP"))
                    stack.enter_context(patch.object(loop, "CONDA_ENV", sys_prefix()))
                    stack.enter_context(patch.object(loop, "Human"))
                    stack.enter_context(patch.object(loop, "load_goal", return_value=("목표", False)))
                    stack.enter_context(patch.object(loop, "code_version", return_value="test"))
                    stack.enter_context(patch.object(loop, "ask", return_value="q"))
                    stack.enter_context(patch.object(loop, "human_away", return_value=True))
                    for name in ("step_plan", "step_claude", "step_review", "handle_needs_human"):
                        stack.enter_context(patch.object(loop, name, side_effect=AssertionError(name)))
                    stack.enter_context(patch.object(loop, "HUMAN", None))
                    loop.run_loop(args)
                self.assertEqual(loop.current_iteration(), 1)
                self.assertFalse((loop.iter_dir(1) / "done.json").exists())

    def test_approved_feedback_reaches_next_plan_before_second_boundary(self):
        self.review()
        calls = []

        def next_plan(args, goal, n):
            self.assertTrue((loop.iter_dir(1) / "done.json").exists())
            self.assertIn("오류 분석 먼저", loop.next_iteration_feedback(n))
            calls.append(n)
            self.plan(n)
            for name in ("plan.md", "claude_report.md"):
                loop.save(loop.iter_dir(n) / name, "새 내용")
            self.record(n, "review.json", {"verdict": "CONTINUE", "one_line_summary": "분석 완료",
                                           "reason": "확인 필요", "next_task": "후속 비교"})

        with contextlib.ExitStack() as stack:
            for name in ("configure_engineer", "ensure_research_repo", "set_stage", "check_stop",
                         "handle_paper", "step_commit", "handle_milestone", "commit_records"):
                stack.enter_context(patch.object(loop, name))
            stack.enter_context(patch.object(loop, "STOP_FILE", self.root / "STOP"))
            stack.enter_context(patch.object(loop, "CONDA_ENV", sys_prefix()))
            stack.enter_context(patch.object(loop, "Human"))
            stack.enter_context(patch.object(loop, "load_goal", return_value=("목표", False)))
            stack.enter_context(patch.object(loop, "code_version", return_value="test"))
            stack.enter_context(patch.object(loop, "ask", side_effect=["f 오류 분석 먼저", "q"]))
            stack.enter_context(patch.object(loop, "step_plan", side_effect=next_plan))
            stack.enter_context(patch.object(loop, "HUMAN", None))
            loop.run_loop(self.args("--confirm-each-iter", "--max-iters", "2"))
        self.assertEqual(calls, [2])
        self.assertEqual(loop.current_iteration(), 2)
        self.assertFalse((loop.iter_dir(2) / "done.json").exists())


class HandoffTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    git = fixtures.WorkflowTests.git
    record = fixtures.WorkflowTests.record
    plan = fixtures.WorkflowTests.plan
    args = BoundaryTests.args

    def setup_handoff(self):
        self.plan(1)
        d = loop.iter_dir(1)
        loop.save(d / "plan.md", "원 연구 계획")
        self.record(1, "engineer_backend.json", {"backend": "codex"})
        loop.save(d / "codex_engineer_session.txt", "old-session")
        loop.save(d / "codex_engineer_stream.jsonl", "old-stream")
        self.record(1, "claude_result.raw.json", {"result": "미완료 출력"})
        loop.save(self.repo / "partial.py", "보존할 코드")
        return self.args("--handoff-engineer", "claude", "--handoff-note", "종료 확인; checkpoint 경로 확인; 남은 평가 재개")

    def test_handoff_keeps_number_plan_code_and_archives_session(self):
        args = self.setup_handoff()
        with patch.object(loop, "AGENT_DIR", self.root / "agent"):
            loop.prepare_engineer_handoff(args)
        d = loop.iter_dir(1)
        self.assertEqual(loop.current_iteration(), 1)
        self.assertEqual(loop.engineer_backend(n=1), "claude")
        self.assertEqual((d / "plan.md").read_text(), "원 연구 계획")
        self.assertEqual((self.repo / "partial.py").read_text(), "보존할 코드")
        self.assertEqual((d / "codex_engineer_stream.jsonl").read_text(), "old-stream")
        self.assertFalse((d / "codex_engineer_session.txt").exists())
        self.assertFalse((d / "claude_result.raw.json").exists())
        self.assertFalse((d / "superseded.json").exists())
        archive = next((d / "engineer_handoffs").glob("*/codex_engineer_session.txt"))
        self.assertEqual(archive.read_text(), "old-session")
        self.assertIn("남은 평가 재개", loop.engineer_handoff_context(1))

    def test_half_handoff_recovers_without_rearchiving_new_backend(self):
        args = self.setup_handoff()
        original = loop.save_atomic

        def fail(path, text):
            if path.name == "transaction.json" and '"applied"' in text:
                raise OSError("중단")
            original(path, text)

        with patch.object(loop, "AGENT_DIR", self.root / "agent"):
            with patch.object(loop, "save_atomic", side_effect=fail), self.assertRaises(OSError):
                loop.prepare_engineer_handoff(args)
            loop.prepare_engineer_handoff(self.args())
        archives = list((loop.iter_dir(1) / "engineer_handoffs").glob("*/transaction.json"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(loop.load_json(archives[0])["status"], "applied")
        self.assertEqual(loop.current_iteration(), 1)
        self.assertEqual(loop.engineer_backend(n=1), "claude")

    def test_handoff_rejects_completed_or_missing_note_and_replan(self):
        args = self.setup_handoff()
        args.handoff_note = ""
        with self.assertRaises(loop.AgentError):
            loop.prepare_engineer_handoff(args)
        args.handoff_note = "종료 확인"
        loop.save(loop.iter_dir(1) / "claude_report.md", "완료")
        with self.assertRaises(loop.AgentError):
            loop.prepare_engineer_handoff(args)
        with self.assertRaises(SystemExit):
            self.args("--handoff-engineer", "claude", "--replan", "새 연구")

    def test_prepare_only_no_agent_calls(self):
        self.setup_handoff()
        with patch.object(loop, "AGENT_DIR", self.root / "agent"), \
                patch.object(sys, "argv", ["orchestrator.py", "--handoff-engineer", "claude",
                                         "--handoff-note", "종료 확인; checkpoint 재개", "--prepare-only"]), \
                patch.object(loop, "run_loop") as run, patch.object(loop, "Human") as human:
            loop.main()
            run.assert_not_called()
            human.assert_not_called()
        self.assertEqual(loop.current_iteration(), 1)

    def test_roundtrip_handoff_never_reuses_old_provider_session(self):
        args = self.setup_handoff()
        with patch.object(loop, "AGENT_DIR", self.root / "agent"):
            loop.prepare_engineer_handoff(args)
            loop.save(loop.iter_dir(1) / "claude_session.txt", "claude-attempt")
            loop.save(loop.iter_dir(1) / "claude_stream.jsonl", "claude-stream")
            loop.prepare_engineer_handoff(self.args("--handoff-engineer", "codex",
                                                   "--handoff-note", "다시 종료 확인; 같은 checkpoint 재개"))
        d = loop.iter_dir(1)
        self.assertEqual(loop.engineer_backend(n=1), "codex")
        self.assertFalse((d / "codex_engineer_session.txt").exists())
        self.assertFalse((d / "claude_session.txt").exists())
        self.assertEqual(len(list((d / "engineer_handoffs").glob("*/transaction.json"))), 2)
        self.assertEqual(loop.current_iteration(), 1)


def sys_prefix():
    from pathlib import Path
    return Path(sys.prefix)


if __name__ == "__main__":
    unittest.main()
