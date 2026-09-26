"""사용자 보완 재개·한계 검증 진입 조건. 실제 에이전트·GPU·알림은 사용하지 않는다."""

import argparse
import contextlib
import json
import sys
import unittest
from unittest.mock import patch

import orchestrator as loop
import test_orchestrator_workflow as fixtures


class ControlTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    git = fixtures.WorkflowTests.git
    record = fixtures.WorkflowTests.record
    plan = fixtures.WorkflowTests.plan

    def test_replan_preserves_old_stage_session_and_worktree(self):
        self.plan(1)
        old = loop.iter_dir(1)
        (old / "plan.md").write_text("이전 계획", encoding="utf-8")
        (old / "claude_session.txt").write_text("old-session", encoding="utf-8")
        (self.repo / "partial.py").write_text("VALUE = 1\n", encoding="utf-8")
        before = {p.name: p.read_bytes() for p in old.iterdir()}
        loop.queue_replan("정상 사용 한계부터 확인")
        self.assertEqual(loop.apply_pending_replan(), 2)
        for name, data in before.items():
            self.assertEqual((old / name).read_bytes(), data)
        self.assertFalse((old / "done.json").exists())
        self.assertTrue((old / "superseded.json").exists())
        self.assertEqual(loop.current_iteration(), 2)
        self.assertFalse((loop.iter_dir(2) / "claude_session.txt").exists())
        self.assertTrue((self.repo / "partial.py").exists())
        self.assertIn("정상 사용 한계", loop.intervention_context(2))
        self.assertEqual(loop.plan_tier(argparse.Namespace(gpt_tier=None), 2), "deep")
        self.assertTrue(loop.review_decision(argparse.Namespace(), 2)[0])
        self.assertIsNone(loop.apply_pending_replan())
        self.assertFalse(loop.RESUME_FILE.exists())

    def test_mid_transition_failure_recovers_same_target(self):
        self.plan(1)
        loop.queue_replan("사용자 새 판단")
        original = loop.save_atomic

        def fail(path, text):
            if path.name == "superseded.json":
                raise OSError("전환 중 중단")
            original(path, text)

        with patch.object(loop, "save_atomic", side_effect=fail):
            with self.assertRaisesRegex(OSError, "전환 중 중단"):
                loop.apply_pending_replan()
        self.assertEqual(len(loop.pending_interventions()), 1)
        self.assertEqual(loop.apply_pending_replan(), 2)
        self.assertEqual(loop.existing_iterations(), [1, 2])
        self.assertEqual(loop.pending_interventions(), [])

    def test_new_instruction_during_transition_is_not_discarded(self):
        self.plan(1)
        loop.queue_replan("첫 지시")
        original = loop.save_atomic

        def changed(path, text):
            original(path, text)
            if path.name == "intervention.json":
                loop.RESUME_FILE.write_text("다음 보완 지시", encoding="utf-8")

        with patch.object(loop, "save_atomic", side_effect=changed):
            loop.apply_pending_replan()
        self.assertEqual(loop.RESUME_FILE.read_text(), "다음 보완 지시")
        self.assertEqual(loop.apply_pending_replan(), 3)
        self.assertIn("다음 보완 지시", loop.intervention_context(3))

    def test_completed_iteration_is_untouched(self):
        self.plan(1)
        self.record(1, "done.json", {"verdict": "DONE"})
        loop.queue_replan("새 방향 검토")
        self.assertEqual(loop.apply_pending_replan(), 2)
        self.assertFalse((loop.iter_dir(1) / "superseded.json").exists())
        self.assertEqual(loop.load_json(loop.iter_dir(1) / "done.json")["verdict"], "DONE")

    def test_replan_after_review_keeps_review_and_commit(self):
        self.plan(1)
        self.record(1, "review.json", {"verdict": "CONTINUE", "approach_status": "improve"})
        self.record(1, "commit.json", {"sha": self.git("rev-parse", "HEAD")})
        old = (loop.iter_dir(1) / "commit.json").read_bytes()
        loop.queue_replan("후처리 전에 방향 수정")
        self.assertEqual(loop.apply_pending_replan(), 2)
        self.assertEqual((loop.iter_dir(1) / "commit.json").read_bytes(), old)
        self.assertTrue((loop.iter_dir(1) / "review.json").exists())

    def test_pending_feedback_cannot_be_overwritten(self):
        loop.queue_replan("먼저 들어온 지시")
        with self.assertRaises(loop.AgentError):
            loop.queue_replan("덮어쓰기")
        self.assertIn("먼저 들어온", loop.RESUME_FILE.read_text())

    def test_empty_feedback_blocks_instead_of_resuming_old_work(self):
        loop.RESUME_FILE.write_text("\n", encoding="utf-8")
        with self.assertRaises(loop.AgentError):
            loop.apply_pending_replan()

    def test_intervention_persists_but_does_not_cross_goal_change(self):
        loop.queue_replan("유지할 연구 기준")
        loop.apply_pending_replan()
        self.plan(2)
        self.assertIn("유지할 연구 기준", loop.intervention_context(2))
        loop.GOALS_FILE.write_text(json.dumps([
            {"start_iter": 1, "goal": "기존"}, {"start_iter": 2, "goal": "새 목표"},
        ]), encoding="utf-8")
        self.assertEqual(loop.intervention_context(2), "없음")

    def test_lock_rejects_second_runner(self):
        with loop.orchestrator_lock():
            with self.assertRaises(loop.AgentError):
                with loop.orchestrator_lock():
                    self.fail("중복 실행 허용")
        with loop.orchestrator_lock():
            pass

    def test_prepare_only_never_starts_agents_notifications_or_experiments(self):
        self.plan(1)
        with patch.object(sys, "argv", ["orchestrator.py", "--replan", "검증 우선", "--prepare-only"]), \
                patch.object(loop, "run_loop") as run, patch.object(loop, "Human") as human:
            loop.main()
            run.assert_not_called()
            human.assert_not_called()
        self.assertEqual(loop.current_iteration(), 2)

    def test_status_does_not_consume_pending_feedback(self):
        loop.queue_replan("대기 지시")
        with patch.object(sys, "argv", ["orchestrator.py", "--status"]), \
                patch.object(loop, "run_loop") as run, patch.object(loop, "Human") as human:
            loop.main()
            run.assert_not_called()
            human.assert_not_called()
        self.assertTrue(loop.RESUME_FILE.exists())
        self.assertEqual(loop.existing_iterations(), [])

    def update(self, status="validated"):
        return {"id": "grounding", "claim": "명시한 조건에서 실제 위치 오류 재현", "status": status,
                "evidence": ["results/heldout.json: 사전 지정 지표"],
                "usage_checks": ["공식 예제와 입력·출력 처리 대조 통과"], "remaining_questions": ["내부 원인은 미확인"]}

    def test_method_gate_blocks_auto_without_validated_evidence(self):
        self.plan(1, experiment_role="method", limitation_ids=["grounding"])
        with self.assertRaisesRegex(loop.AgentError, "방법 개발 진입 보류"):
            loop.step_checkpoint(argparse.Namespace(autonomy="full"), 1)
        self.assertEqual(loop.method_gate_errors(1, {"experiment_role": "diagnostic"}), [])

    def test_validated_review_unlocks_method_only_in_same_goal(self):
        self.plan(1)
        self.record(1, "review.json", {"valid_experiment": True, "blocking_issues": [],
                                       "limitation_updates": [self.update()]})
        plan = {"experiment_role": "method", "limitation_ids": ["grounding"]}
        self.assertEqual(loop.method_gate_errors(2, plan), [])
        loop.GOALS_FILE.write_text(json.dumps([
            {"start_iter": 1, "goal": "기존"}, {"start_iter": 2, "goal": "새 목표"},
        ]), encoding="utf-8")
        self.assertTrue(loop.method_gate_errors(2, plan))

    def test_invalid_experiment_or_missing_usage_checks_cannot_validate(self):
        for overrides in ({"valid_experiment": False}, {"blocking_issues": ["잘못된 정답"]},
                          {"limitation_updates": [{**self.update(), "usage_checks": []}]}):
            review = {"valid_experiment": True, "blocking_issues": [], "limitation_updates": [self.update()], **overrides}
            with self.assertRaises(loop.AgentError):
                loop.validate_limitation_updates(review)

    def test_retraction_keeps_history_and_relocks_method(self):
        self.plan(1)
        self.record(1, "review.json", {"valid_experiment": True, "limitation_updates": [self.update()]})
        self.plan(2)
        self.record(2, "review.json", {"valid_experiment": True,
                                       "limitation_updates": [self.update("rejected")]})
        self.assertEqual(loop.limitation_registry()["grounding"]["status"], "rejected")
        self.assertEqual(loop.load_review(1)["limitation_updates"][0]["status"], "validated")
        self.assertTrue(loop.method_gate_errors(3, {"experiment_role": "method", "limitation_ids": ["grounding"]}))

    def test_reasoning_notes_are_not_silently_truncated(self):
        notes = "가" * 6000 + "끝의 핵심 근거"
        self.record(1, "round.json", {"research_notes": notes, "open_questions": ["후속 질문"]})
        text = loop.think_section([loop.iter_dir(1) / "round.json"], 2, 4, False)
        self.assertIn(notes, text)
        self.assertIn("후속 질문", text)

    def test_normal_restart_replans_before_fresh_implementation(self):
        self.plan(1)
        (loop.iter_dir(1) / "plan.md").write_text("보류할 기존 계획", encoding="utf-8")
        (loop.iter_dir(1) / "claude_session.txt").write_text("old", encoding="utf-8")
        calls = []

        def plan(args, goal, n):
            calls.append(("plan", n))
            self.plan(n, experiment_role="diagnostic")
            (loop.iter_dir(n) / "plan.md").write_text("새 검증 계획", encoding="utf-8")

        def implement(args, goal, n):
            calls.append(("claude", n))
            self.assertFalse((loop.iter_dir(n) / "claude_session.txt").exists())
            self.assertIn("한계 검증부터", loop.intervention_context(n))
            (loop.iter_dir(n) / "claude_report.md").write_text("검증 보고서", encoding="utf-8")

        def review(args, goal, n):
            calls.append(("review", n))
            self.record(n, "review.json", {"verdict": "CONTINUE", "approach_status": "inconclusive"})
            return loop.load_review(n)

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", ["orchestrator.py", "--replan", "한계 검증부터",
                                                             "--max-iters", "1", "--no-telegram"]))
            stack.enter_context(patch.object(loop, "STOP_FILE", self.root / "STOP"))
            stack.enter_context(patch.object(loop, "Human"))
            stack.enter_context(patch.object(loop, "load_goal", return_value=("기존 목표", False)))
            stack.enter_context(patch.object(loop, "code_version", return_value="test"))
            for name in ("ensure_research_repo", "set_stage", "check_stop", "handle_paper",
                         "step_commit", "handle_milestone", "commit_records"):
                stack.enter_context(patch.object(loop, name))
            stack.enter_context(patch.object(loop, "step_checkpoint", return_value="go"))
            stack.enter_context(patch.object(loop, "step_plan", side_effect=plan))
            stack.enter_context(patch.object(loop, "step_claude", side_effect=implement))
            stack.enter_context(patch.object(loop, "step_review", side_effect=review))
            stack.enter_context(patch.object(loop, "HUMAN", None))
            loop.main()
        self.assertEqual(calls, [("plan", 2), ("claude", 2), ("review", 2)])
        self.assertTrue((loop.iter_dir(1) / "superseded.json").exists())
        self.assertTrue((loop.iter_dir(2) / "done.json").exists())


if __name__ == "__main__":
    unittest.main()
