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
    def test_shared_policies_survive_research_branch_changes(self):
        policy = (ROOT / "agent/RESEARCH_POLICY.md").read_text()
        self.assertIn("research/ 브랜치 전환·복귀로 공통 정책을 되돌리거나", policy)
        self.assertIn("검토·테스트 후 별도 관리 커밋으로 보존", policy)
        self.assertIn("실행 중인 상위 작업 폴더의 브랜치는 바꾸지 않는다", policy)
        self.assertIn("상위 저장소 push로 백업됐다고 보고하지 않는다", policy)

    def test_policy_separates_investment_from_experiment_verdict(self):
        policy = (ROOT / "agent/RESEARCH_POLICY.md").read_text()
        for text in ("현재 방법의 개선 / 원인·능력 전이 진단 / 다른 연구 질문으로 전환",
                     "improve/success는 같은 접근법의 자동 연장 명령이 아니다",
                     "양성 / 음성 / 불확정", "실행 유효성 / 성능 개선 /",
                     "가설 지지 / 신규 기여 가능성", "특정 진단을 새 최종 목표로 고정하지 않는다"):
            self.assertIn(text, policy)

    def test_current_run_preserved_and_first_followup_reassesses(self):
        policy = (ROOT / "agent/RESEARCH_POLICY.md").read_text()
        section = policy.split("### 현재 실험과의 적용 경계", 1)[1].split("## 목표에 연결되는 실험", 1)[0]
        for text in ("조건부 후속 비교", "새 요구를 소급해", "next_plan_tier=deep",
                     "iter_014 이후 첫 새 계획", "GOAL과 과거 계획·리뷰를 덮어쓰지 않는다",
                     "superseded 처리하는 지시가 아니다"):
            self.assertIn(text, section)
        engineer = (ROOT / "agent/prompts/claude_engineer.md").read_text()
        self.assertIn("전략 재검토는 GPT 계획·리뷰에서 한다", engineer)
        self.assertIn("원래 계획한 조건부 후속 비교와 평가까지 유지", engineer)

    def test_prompts_remove_automatic_continuation_and_keep_existing_fields(self):
        plan = (ROOT / "agent/prompts/gpt_plan.md").read_text()
        review = (ROOT / "agent/prompts/gpt_review.md").read_text()
        self.assertNotIn("판정이 improve면 같은 approach 이름으로 개선을 이어간다", plan)
        for prompt in (plan, review):
            self.assertIn("# Strategy Check / 연구 방향 판단", prompt)
            self.assertIn("GOAL 범위 안", prompt)
        self.assertIn("iter_014 이후 첫 새 계획", plan)
        self.assertIn("next_plan_tier=deep", review)
        self.assertIn("next_task", review)
        self.assertIn("one_line_summary", review)

    def test_diagnostic_guardrails_and_bounded_reassessment(self):
        policy = (ROOT / "agent/RESEARCH_POLICY.md").read_text()
        for text in ("검출+규칙 baseline", "원인 분리용", "JSON 형식 적응", "임상적으로 정상",
                     "모든 검출기를 이기거나", "이전 판단의 출처", "별도 에이전트 호출"):
            # 출처 표기는 계획 프롬프트에도 허용한다.
            combined = policy + (ROOT / "agent/prompts/gpt_plan.md").read_text()
            self.assertIn(text, combined)

    def test_gpt_next_call_reloads_strategy_policy_without_restart(self):
        args = argparse.Namespace(gpus="0,1", gpt_timeout=30, claude_timeout=0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "RESEARCH_POLICY.md"
            output = root / "raw.json"
            policy.write_text("기존 연구 정책", encoding="utf-8")
            prompts = []

            def run(cmd, *unused, **kwargs):
                prompts.append(cmd[-1])
                output.write_text("{}", encoding="utf-8")

            with patch.object(loop, "RESEARCH_POLICY_FILE", policy), \
                    patch.object(loop, "run_streaming", side_effect=run):
                loop.run_codex(args, "리뷰", output, root / "review.log", "normal")
                policy.write_text((ROOT / "agent/RESEARCH_POLICY.md").read_text(), encoding="utf-8")
                loop.run_codex(args, "계획", output, root / "plan.log", "deep")
            self.assertNotIn("연구 질문과 다음 투자 판단", prompts[0])
            self.assertIn("연구 질문과 다음 투자 판단", prompts[1])
            self.assertIn("iter_014 이후 첫 새 계획", prompts[1])

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
            stack.enter_context(patch.object(loop, "plan_tier", return_value="deep"))
            stack.enter_context(patch.object(loop, "review_tier", return_value="normal"))
            stack.enter_context(patch.object(loop, "set_stage"))
            stack.enter_context(patch.object(loop, "with_retries", side_effect=lambda name, call: call()))
            call = stack.enter_context(patch.object(loop, "run_codex", side_effect=Captured))
            args = argparse.Namespace(max_think_rounds=4)
            for stage, n, expected in ((loop.step_plan, 15, "iter_014 이후 첫 새 계획"),
                                       (loop.step_review, 14, "next_plan_tier=deep")):
                with self.assertRaises(Captured):
                    stage(args, "기존 연구 목표", n)
                prompt = call.call_args.args[1]
                self.assertIn("# Strategy Check / 연구 방향 판단", prompt)
                self.assertIn(expected, prompt)

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
