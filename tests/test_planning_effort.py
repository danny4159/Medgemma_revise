"""계획 effort 분기·재개·리뷰 독립성. 실제 모델·GPU 호출 없음."""

import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import orchestrator as loop
import planning_effort as routing


HIGH_REASON = {"scope": "research_direction", "decision": "현재 track 유지와 전환 중 선택",
               "difficulty": "위치 개선과 공동 처리 손실의 근거 충돌",
               "impact": "다음 방법 개발·학습 투자의 방향이 바뀜"}


class RoutingTests(unittest.TestCase):
    def test_default_legacy_and_explicit(self):
        for tier in (None, "deep", "unknown", "none"):
            self.assertEqual(routing.choose(tier)["tier"], "deep_medium")
        self.assertEqual(routing.choose("deep", explicit=True)["tier"], "deep_high")
        self.assertEqual(routing.choose("deep_high", explicit=True)["tier"], "deep_high")
        for tier in ("normal", "light", "deep_medium"):
            self.assertEqual(routing.choose(tier)["tier"], tier)

    def test_high_requires_scope_and_all_three_reasons(self):
        self.assertEqual(routing.choose("deep_high", HIGH_REASON)["tier"], "deep_high")
        for key in HIGH_REASON:
            reason = {**HIGH_REASON, key: " "}
            self.assertEqual(routing.choose("deep_high", reason)["tier"], "deep_medium")
        for scope in ("bounded_followup", "none"):
            self.assertEqual(routing.choose("deep_high", {**HIGH_REASON, "scope": scope})["tier"], "deep_medium")
        for invalid in (None, "문헌 검토", [], 1):
            self.assertEqual(routing.choose("deep_high", invalid)["tier"], "deep_medium")

    def test_cli_plan_override_does_not_change_review(self):
        with patch("sys.argv", ["orchestrator.py", "--plan-tier", "deep_medium"]):
            args = loop.parse_args()
        self.assertEqual(loop.plan_tier(args, 1), "deep_medium")
        for engineer, tier in (("standard", "normal"), ("heavy", "normal"), ("creative", "deep")):
            with patch.object(loop, "tiers_used", return_value={"claude": engineer}):
                self.assertEqual(loop.review_tier(args, 1), tier)
        args.gpt_tier = "deep"
        self.assertEqual(loop.plan_tier(args, 1), "deep_medium")
        self.assertEqual(loop.review_tier(args, 1), "deep")

    def test_entry_defaults_and_previous_strategic_review(self):
        args = argparse.Namespace(gpt_tier=None)
        with tempfile.TemporaryDirectory() as tmp, patch.object(loop, "iter_dir", return_value=Path(tmp)), \
                patch.object(loop, "goal_start", return_value=1), patch.object(loop, "load_review") as review:
            review.return_value = {"next_plan_tier": "deep_high", "next_plan_reason": HIGH_REASON}
            self.assertEqual(loop.plan_tier(args, 2), "deep_high")
            self.assertEqual(loop.plan_tier(args, 1), "deep_medium")
            (Path(tmp) / "intervention.json").write_text("{}")
            self.assertEqual(loop.plan_tier(args, 2), "deep_medium")

    def test_schema_and_effort_mappings(self):
        for tier, effort in (("deep_medium", "medium"), ("deep_high", "high"), ("deep", "high")):
            self.assertEqual(loop.tier_spec("gpt", tier), {"model": "gpt-6-astra", "effort": effort})
        for name, field in (("plan", "next_think"), ("review", "next_plan")):
            schema = json.loads((loop.PROMPT_DIR / f"{name}_schema.json").read_text())
            self.assertEqual(set(schema["required"]), set(schema["properties"]))
            self.assertIn("deep_medium", schema["properties"][field + "_tier"]["enum"])
            self.assertIn("deep_high", schema["properties"][field + "_tier"]["enum"])
            self.assertNotIn("deep", schema["properties"][field + "_tier"]["enum"])
            reason = schema["properties"][field + "_reason"]
            self.assertEqual(set(reason["required"]), set(HIGH_REASON))


class RoundTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.args = argparse.Namespace(gpt_tier=None, plan_tier=None, max_think_rounds=4)
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        stack.enter_context(patch.object(loop, "iter_dir", return_value=self.root))
        stack.enter_context(patch.object(loop, "load_review", return_value=None))
        stack.enter_context(patch.object(loop, "goal_start", return_value=0))
        stack.enter_context(patch.object(loop, "current_branch", return_value="test"))
        stack.enter_context(patch.object(loop, "gpt_record_context", return_value={
            "history": "이전 결과", "assets": "기존 자산", "limitations": "한계 근거"}))
        stack.enter_context(patch.object(loop, "intervention_context", return_value=""))
        stack.enter_context(patch.object(loop, "with_retries", side_effect=lambda _, call: call()))
        for name in ("set_stage", "record_event", "rebuild_index", "check_stop", "log"):
            stack.enter_context(patch.object(loop, name))

    def response(self, next_tier="none", reason=None):
        return json.dumps({"next_action": "implement" if next_tier == "none" else "think_more",
                           "next_think_tier": next_tier, "next_think_reason": reason or {},
                           "research_notes": "앞선 근거를 보존", "open_questions": ["남은 판단은?"],
                           "plan_summary": "요약", "plan_markdown": "실행 계획"})

    def test_medium_high_medium_handoff_keeps_notes_and_round_budget(self):
        seen = []
        responses = iter([self.response("deep_high", HIGH_REASON), self.response("deep_medium"), self.response()])

        def call(args, prompt, output, log, tier, **kwargs):
            seen.append(tier)
            if len(seen) > 1:
                self.assertIn("앞선 근거를 보존", prompt)
            return next(responses)

        with patch.object(loop, "run_codex", side_effect=call):
            loop.step_plan(self.args, "목표 유지", 2)
        self.assertEqual(seen, ["deep_medium", "deep_high", "deep_medium"])
        records = [json.loads(p.read_text()) for p in sorted((self.root / "think").glob("*.tier.json"))]
        self.assertEqual([r["effort"] for r in records], ["medium", "high", "medium"])
        self.assertEqual(records[1]["reason"], HIGH_REASON)
        self.assertEqual(loop.tiers_used(2)["plan"], "deep_medium")

    def test_high_can_start_directly_without_medium_call(self):
        with patch.object(loop, "load_review", return_value={"next_plan_tier": "deep_high",
                  "next_plan_reason": HIGH_REASON, "verdict": "CONTINUE", "next_task": "전략 판단", "reason": "근거"}), \
                patch.object(loop, "run_codex", return_value=self.response()) as call:
            loop.step_plan(self.args, "목표 유지", 2)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[4], "deep_high")

    def test_incomplete_round_resumes_saved_choice(self):
        with patch.object(loop, "run_codex", side_effect=loop.AgentError("일시 중단")), self.assertRaises(loop.AgentError):
            loop.step_plan(self.args, "목표 유지", 2)
        path = self.root / "think/round_01.tier.json"
        original = path.read_bytes()
        with patch.object(loop, "plan_tier_choice", return_value=routing.choose("deep_high", HIGH_REASON)), \
                patch.object(loop, "run_codex", return_value=self.response()) as call:
            loop.step_plan(self.args, "목표 유지", 2)
        self.assertEqual(call.call_args.args[4], "deep_medium")
        self.assertEqual(path.read_bytes(), original)

    def test_completed_old_round_is_preserved_and_missing_recommendation_defaults_medium(self):
        folder = self.root / "think"
        folder.mkdir()
        path = folder / "round_01.json"
        path.write_text(json.dumps({"research_notes": "예전 high 조사", "open_questions": ["남은 것"]}))
        original = path.read_bytes()
        with patch.object(loop, "run_codex", return_value=self.response()) as call:
            loop.step_plan(self.args, "목표 유지", 2)
        self.assertEqual(call.call_args.args[4], "deep_medium")
        self.assertIn("예전 high 조사", call.call_args.args[1])
        self.assertEqual(path.read_bytes(), original)

    def test_think_more_at_limit_still_requires_human(self):
        self.args.max_think_rounds = 1
        with patch.object(loop, "run_codex", return_value=self.response("deep_high", HIGH_REASON)) as call:
            loop.step_plan(self.args, "목표 유지", 2)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(json.loads((self.root / "plan.json").read_text())["decision"], "ask_human")


if __name__ == "__main__":
    unittest.main()
