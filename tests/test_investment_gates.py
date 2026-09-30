"""방법 pilot의 제한적 진입, 확대 보호, 큰 질문 이력. 모델/GPU 호출 없음."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import gpt_context
import orchestrator as loop
import test_orchestrator_workflow as fixtures


class InvestmentGateTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    git = fixtures.WorkflowTests.git
    record = fixtures.WorkflowTests.record
    plan = fixtures.WorkflowTests.plan

    def evidence(self, status="observed", **overrides):
        self.plan(1, experiment_role="diagnostic")
        review = {"valid_experiment": True, "blocking_issues": [], "limitation_updates": [{
            "id": "binding", "status": status, "claim": "통제된 공동 처리 손실",
            "evidence": ["원시 출력과 대조"], "usage_checks": ["좌표·형식 확인"],
            "remaining_questions": ["개입 효과"],
        }]}
        review.update(overrides)
        self.record(1, "review.json", review)

    def proposed(self, stage="pilot", role="method"):
        return {"experiment_role": role, "method_stage": stage, "research_track": "joint-grounding",
                "related_iterations": [1], "limitation_ids": ["binding"],
                "research_question": "개입으로 경쟁 설명을 구분하는가?",
                "contribution_path": "기존 방법과 잔여 비용 차이 검증; 신규성 미확정",
                "baseline_plan": "직접 SFT와 동일 데이터·학습량 비교",
                "decision_contract": {
                    "mechanism_hypothesis": "출력 간섭 가설과 단순 인식 부족 대조",
                    "intervention_test": "단일 개입과 같은 비용의 대조",
                    "success_action": "독립 재현 근거 검토 후 full 계획 판단",
                    "failure_action": "해당 개입 투자 종료, 원시 결과 보존",
                    "inconclusive_action": "분산 기준의 추가 표본 판단, 미충족이면 보류",
                    "scope_budget": "개발 subset·1후보·1seed, 실측 처리량 기반",
                    "stop_rule": "1개 개입 대조 후 리뷰; 자동 full 금지",
                }}

    def test_reviewed_observed_permits_pilot_not_full(self):
        self.evidence()
        self.assertEqual(loop.method_gate_errors(2, self.proposed()), [])
        self.assertTrue(loop.method_gate_errors(2, self.proposed("full")))
        self.assertTrue(loop.method_gate_errors(2, self.proposed("full", "confirmatory")))

    def test_candidate_rejected_unknown_and_other_goal_block_pilot(self):
        for status in ("candidate", "rejected"):
            self.evidence(status)
            self.assertTrue(loop.method_gate_errors(2, self.proposed()))
        self.evidence()
        p = self.proposed()
        p["limitation_ids"] = ["unknown"]
        self.assertTrue(loop.method_gate_errors(2, p))
        loop.GOALS_FILE.write_text(json.dumps([{"start_iter": 1, "goal": "old"},
                                             {"start_iter": 2, "goal": "new"}]))
        self.assertTrue(loop.method_gate_errors(2, self.proposed()))

    def test_pilot_requires_valid_review_no_blocking_no_skip(self):
        for overrides in ({"valid_experiment": False}, {"blocking_issues": ["좌표 오류"]}, {"skipped": True}):
            self.evidence(**overrides)
            self.assertTrue(loop.method_gate_errors(2, self.proposed()))
        self.evidence()
        r = loop.load_review(1)
        r["limitation_updates"][0]["usage_checks"] = []
        self.record(1, "review.json", r)
        self.assertTrue(loop.method_gate_errors(2, self.proposed()))

    def test_unreviewed_initial_observed_is_not_pilot_evidence(self):
        self.evidence()
        with patch.object(loop, "limitation_registry", return_value={"binding": {
                "status": "observed", "goal_start": loop.goal_start(2),
                "evidence": ["manual"], "usage_checks": ["manual"]}}):
            self.assertTrue(loop.method_gate_errors(2, self.proposed()))

    def test_contract_and_baseline_not_optional_for_pilot(self):
        self.evidence()
        for key in self.proposed()["decision_contract"]:
            p = self.proposed()
            p["decision_contract"][key] = " "
            self.assertTrue(loop.method_gate_errors(2, p), key)
        for key in ("research_question", "research_track", "baseline_plan", "contribution_path"):
            p = self.proposed()
            p[key] = ""
            self.assertTrue(loop.method_gate_errors(2, p), key)

    def test_role_stage_mismatch_and_bad_links_block(self):
        self.evidence("validated")
        for role, stage in (("diagnostic", "pilot"), ("method", "none"), ("confirmatory", "pilot")):
            self.assertTrue(loop.method_gate_errors(2, self.proposed(stage, role)))
        for links in ([2], [0], [True], [1.0], [999], "1"):
            p = self.proposed()
            p["related_iterations"] = links
            self.assertTrue(loop.method_gate_errors(2, p))

    def test_new_diagnostic_needs_exit_but_old_plan_unchanged(self):
        self.evidence()
        p = self.proposed("none", "diagnostic")
        p["decision_contract"]["mechanism_hypothesis"] = ""
        p["decision_contract"]["intervention_test"] = ""
        self.assertEqual(loop.method_gate_errors(2, p), [])
        p["decision_contract"]["stop_rule"] = ""
        self.assertTrue(loop.method_gate_errors(2, p))
        self.assertEqual(loop.method_gate_errors(2, {"experiment_role": "diagnostic"}), [])
        self.evidence("validated")
        self.assertEqual(loop.method_gate_errors(2, {"experiment_role": "method", "limitation_ids": ["binding"]}), [])
        self.assertEqual(loop.method_gate_errors(2, self.proposed("full")), [])

    def test_pilot_still_requires_full_review_even_override(self):
        self.evidence()
        self.plan(2, **self.proposed(), review_mode="skip")
        import argparse
        self.assertTrue(loop.review_decision(argparse.Namespace(always_review=False), 2)[0])


class InvestmentContextTests(unittest.TestCase):
    def test_track_survives_approach_change_and_invalid_runs(self):
        records = []
        for n in range(1, 4):
            records.append({"n": n, "plan": {"approach_id": f"different-{n}",
                            "experiment_role": "diagnostic", "research_track": "same-question",
                            "related_iterations": list(range(1, n)), "decision_contract": {"stop_rule": "종료 판단"}},
                            "review": {"valid_experiment": n == 1}, "superseded": {}})
        rows = [json.loads(line) for line in gpt_context.history_context(records).splitlines() if line.startswith("{")]
        self.assertEqual(next(r for r in rows if "research_track" in r)["iters"], [1, 2, 3])
        self.assertEqual(rows[0]["strategy_overview"]["diagnostic_setup_streak"], [1, 2, 3])
        self.assertEqual(next(r for r in rows if "research_track" in r)["related_iterations"], [1, 2])

    def test_schema_backward_defaults_and_future_fields(self):
        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / "agent/prompts/plan_schema.json").read_text())
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        self.assertEqual(loop.PLAN_DEFAULTS["method_stage"], "legacy")
        self.assertNotIn("legacy", schema["properties"]["method_stage"]["enum"])
        contract = schema["properties"]["decision_contract"]
        self.assertEqual(set(contract["required"]), set(contract["properties"]))

    def test_next_call_policy_contains_pilot_and_current_run_boundary(self):
        root = Path(__file__).resolve().parents[1]
        policy = (root / "agent/RESEARCH_POLICY.md").read_text()
        for term in ("실행 중인 iter_039", "method_stage=pilot", "method_stage=full", "decision_contract",
                     "research_track", "related_iterations", "횟수만으로 자동 기각하지 않는다"):
            self.assertIn(term, policy)


if __name__ == "__main__":
    unittest.main()
