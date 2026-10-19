"""전략 지침과 다음 호출 반영을 검증한다. 모델·GPU·외부 통신은 실행하지 않는다."""

import argparse
import contextlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import orchestrator as loop


ROOT = Path(__file__).resolve().parents[1]


class ResearchStrategyTests(unittest.TestCase):
    def test_permanent_policy_and_question_card_have_no_expired_commands(self):
        policy = (ROOT / "agent/RESEARCH_POLICY.md").read_text()
        for text in ("관찰 계승과 수렴 점검", "새 후보 탐색", "매 리뷰", "추가 모델 호출",
                     "반복 횟수만으로 종료", "next_task 권고", "판별력이 있는 확대",
                     "중요한 문제", "현재 근거", "쉬운 해결책", "남은 설명", "다음 결정"):
            self.assertIn(text, policy)
        for name in ("gpt_plan", "gpt_review", "claude_engineer"):
            prompt = (ROOT / f"agent/prompts/{name}.md").read_text()
            for expired in ("iter_014 이후 첫 새 계획", "현재 iter_039", "iter_080 이후의 실제 투자 선택"):
                self.assertNotIn(expired, prompt)
        self.assertIn("RESEARCH_HISTORY_INDEX.md", (ROOT / "agent/RESEARCH_FOCUS.md").read_text())

    def test_cross_model_and_evaluation_guardrails_remain(self):
        policy = (ROOT / "agent/RESEARCH_POLICY.md").read_text()
        for text in ("여러 모델", "공식 사용법", "개발/test", "강한 단순 대조",
                     "중요한 관찰의 범위 확인용", "모델 특이/공통 현상 후보/미검증",
                     "100% oracle", "동작 확인", "가능성 탐색"):
            combined = policy + (ROOT / "agent/RESEARCH_FOCUS.md").read_text()
            self.assertIn(text, combined)
        plan = (ROOT / "agent/prompts/gpt_plan.md").read_text()
        review = (ROOT / "agent/prompts/gpt_review.md").read_text()
        self.assertIn("경쟁 가설을 먼저 고르고 데이터/과제를 선택", plan)
        self.assertIn("새 요구를 소급 blocker로 추가하지 않는다", review)

    def test_diagnostic_guardrails_and_bounded_reassessment(self):
        policy = (ROOT / "agent/RESEARCH_POLICY.md").read_text()
        for text in ("검출+규칙 baseline", "원인 분리용", "JSON 형식 적응", "임상적으로 정상",
                     "모든 검출기를 이기거나", "별도 전략 에이전트", "method_stage=pilot",
                     "method_stage=full", "진단 수단", "음성 자체가 신규 기여는 아니다"):
            self.assertIn(text, policy)

    def test_gpt_next_call_reloads_strategy_policy_without_restart(self):
        args = argparse.Namespace(gpus="0,1", gpt_timeout=30, claude_timeout=0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "RESEARCH_POLICY.md"
            output = root / "raw.json"
            policy.write_text("기존 연구 정책", encoding="utf-8")
            prompts = []

            def run(cmd, *unused, **kwargs):
                self.assertEqual(cmd[-1], "-")
                prompts.append(kwargs["stdin_text"])
                output.write_text("{}", encoding="utf-8")

            with patch.object(loop, "RESEARCH_POLICY_FILE", policy), \
                    patch.object(loop, "run_streaming", side_effect=run):
                loop.run_codex(args, "리뷰", output, root / "review.log", "normal")
                policy.write_text((ROOT / "agent/RESEARCH_POLICY.md").read_text(), encoding="utf-8")
                loop.run_codex(args, "계획", output, root / "plan.log", "deep")
            self.assertNotIn("연구 질문과 다음 투자 판단", prompts[0])
            self.assertIn("연구 질문과 다음 투자 판단", prompts[1])
            self.assertIn("핵심 자료 조건 먼저", prompts[1])

    def test_plan_and_review_load_updated_role_prompts_at_stage_entry(self):
        class Captured(Exception):
            pass

        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            root = Path(directory)
            stack.enter_context(patch.object(loop, "iter_dir", return_value=root))
            stack.enter_context(patch.object(loop, "load_review", return_value=None))
            stack.enter_context(patch.object(loop, "load_plan", return_value={}))
            stack.enter_context(patch.object(loop, "goal_start", return_value=0))
            stack.enter_context(patch.object(loop, "current_branch", return_value="test"))
            stack.enter_context(patch.object(loop, "code_assets_text", return_value=""))
            stack.enter_context(patch.object(loop, "limitations_text", return_value=""))
            stack.enter_context(patch.object(loop, "intervention_context", return_value=""))
            stack.enter_context(patch.object(loop, "approach_ledger", return_value={}))
            stack.enter_context(patch.object(loop, "record_event"))
            stack.enter_context(patch.object(loop, "review_tier", return_value="normal"))
            stack.enter_context(patch.object(loop, "set_stage"))
            stack.enter_context(patch.object(loop, "with_retries", side_effect=lambda name, call: call()))
            call = stack.enter_context(patch.object(loop, "run_codex", side_effect=Captured))
            args = argparse.Namespace(max_think_rounds=4)
            for stage, n, expected in ((loop.step_plan, 15, "연구 질문 중심 계획"),
                                       (loop.step_review, 14, "deep_medium/deep_high")):
                with self.assertRaises(Captured):
                    stage(args, "기존 연구 목표", n)
                prompt = call.call_args.args[1]
                self.assertIn("# Strategy Check / 연구 방향 판단", prompt)
                self.assertIn(expected, prompt)
                if stage == loop.step_plan:
                    self.assertIn("method pilot은 현재 목표의 유효 리뷰", prompt)
                    self.assertIn("method full/confirmatory는 validated", prompt)
                    self.assertNotIn("방법 개발은 현재 목표에서 validated인 한계 주장과 연결해야 한다", prompt)

    def test_schemas_remain_valid_with_existing_verdicts(self):
        schemas = {}
        for name in ("plan", "review"):
            schemas[name] = json.loads((ROOT / f"agent/prompts/{name}_schema.json").read_text())
            self.assertEqual(set(schemas[name]["required"]), set(schemas[name]["properties"]))
            self.assertFalse(schemas[name]["additionalProperties"])
        self.assertEqual(schemas["review"]["properties"]["verdict"]["enum"],
                         ["CONTINUE", "DONE", "NEEDS_HUMAN"])
        self.assertEqual(schemas["plan"]["properties"]["decision"]["enum"],
                         ["proceed", "ask_human"])


if __name__ == "__main__":
    unittest.main()
