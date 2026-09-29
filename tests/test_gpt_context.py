"""문맥 축소가 출처·반증·필수 검증을 지우지 않는지 검사한다. 모델/GPU 호출 없음."""

import argparse
import contextlib
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gpt_context
import gpt_usage
import orchestrator as loop

ROOT = Path(__file__).resolve().parents[1]


def record(n, approach="a", **review):
    return {"n": n, "plan": {"approach_id": approach, "approach": approach,
                              "plan_summary": "계획 요약"},
            "review": review, "commit": {}, "archive": {}, "superseded": {}, "recovery": False}


class ContextTests(unittest.TestCase):
    def test_failed_followup_keeps_previous_valid_observation_and_scope(self):
        rows = [record(1, valid_experiment=True, approach_status="abandon",
                       one_line_summary="유효한 음성 결과", failure_scope="이 loss 조건만 기각"),
                record(2, approach_status="execution_failed", one_line_summary="실행 미완료",
                       blocking_issues=["완료되지 않음"], reuse_issues=["좌표 오류"],
                       deferred_issues=["선택적 문서 정비"])]
        before = copy.deepcopy(rows)
        text = gpt_context.history_context(rows)
        for value in ("유효한 음성 결과", "이 loss 조건만 기각", "execution_failed",
                      "완료되지 않음", "좌표 오류", "선택적 문서 정비", "iter_001/review.json"):
            self.assertIn(value, text)
        self.assertEqual(rows, before)

    def test_superseded_is_not_failure_and_all_approaches_remain_visible(self):
        rows = [record(i, f"approach-{i}") for i in range(1, 8)]
        rows[-1]["superseded"] = {"successor": 8}
        text = gpt_context.history_context(rows)
        self.assertIn("사용자 보완으로 전환 (실패/완료 아님)", text)
        for i in range(1, 8):
            self.assertIn(f"approach-{i}", text)

    def test_asset_index_preserves_sha_exclusions_archive_and_recovery(self):
        r = record(1, reusable_code=False, code_assets=[
            {"paths": ["module.py"], "status": "needs_fix", "checks": ["검사 원문"]}])
        r.update(commit={"sha": "a" * 40, "unpreserved_paths": ["missing.py"]},
                 archive={"ref": "archive/ref", "stash": "b" * 40}, recovery=True)
        text = gpt_context.asset_context([r])
        for value in ("a" * 40, "missing.py", "needs_fix", "archive/ref", "code_recovery.md", "재사용 승인이 아니다"):
            self.assertIn(value, text)
        self.assertNotIn("검사 원문", text)  # 선택한 review에서 읽는다. 승인으로 축약하지 않는다.

    def test_relevant_claim_is_full_and_unselected_claim_remains_discoverable(self):
        registry = {
            "selected": {"status": "validated", "claim": "제한된 재현", "goal_start": 3,
                         "review_iteration": 9, "evidence": ["actual.json"],
                         "usage_checks": ["정상 입력"], "remaining_questions": ["원인 미확정"]},
            "other": {"status": "rejected", "claim": "기각 범위", "goal_start": 1,
                      "evidence": ["원문에서 확인"]}}
        text = gpt_context.limitation_context(registry, {"selected"})
        for value in ("actual.json", "정상 입력", "원인 미확정", "iter_009/review.json",
                      "other", "rejected", "기각 범위", "goal_start", "LIMITATIONS.json"):
            self.assertIn(value, text)
        self.assertNotIn("원문에서 확인", text)

    def test_prior_thoughts_keep_latest_full_older_summary_questions_and_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for i in (1, 2):
                p = Path(directory) / f"round_{i:02d}.json"
                p.write_text(json.dumps({"plan_summary": f"요약{i}",
                                        "research_notes": f"노트원문{i}" * 100,
                                        "open_questions": [f"질문{i}"]}))
                paths.append(p)
            text = loop.think_section(paths, 3, 4, False)
            self.assertIn("요약1", text)
            self.assertNotIn("노트원문1", text)
            self.assertIn("노트원문2" * 100, text)
            for p in paths:
                self.assertIn(str(p), text)
            self.assertIn("질문1", text)
            self.assertIn("질문2", text)
            self.assertIn("원문 노트를 읽는다", text)
            self.assertIn("마지막 사고 라운드", loop.think_section(paths, 4, 4, True))
            self.assertIn("1라운드", loop.think_section([], 1, 4, False))

    def test_input_bytes_are_attempts_not_token_or_quota_estimates(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "plan_codex.log"
            p.write_text("[input] transport=stdin bytes=2048 sha256=abc\n"
                         "[launch_error] ENOENT\n"
                         "[input] transport=stdin bytes=1024 sha256=def\n"
                         "OpenAI Codex v1\nmodel: gpt-6-astra\nreasoning effort: high\n"
                         "session id: one\ntokens used\n100\n")
            data = gpt_usage.summarize_log(p)
            self.assertEqual(data["input_bytes_per_attempt"], [2048, 1024])
            self.assertEqual(data["session_count"], 1)
            self.assertEqual(data["displayed_tokens"], 100)
            self.assertIn("실행 준비 실패 포함", data["input_bytes_note"])

    def test_plan_review_use_scoped_context_keep_policy_and_intervention(self):
        class Captured(Exception):
            pass

        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            root = Path(directory)
            stack.enter_context(patch.object(loop, "iter_dir", return_value=root))
            stack.enter_context(patch.object(loop, "load_plan", return_value={}))
            stack.enter_context(patch.object(loop, "load_review", return_value=None))
            stack.enter_context(patch.object(loop, "goal_start", return_value=1))
            stack.enter_context(patch.object(loop, "current_branch", return_value="test"))
            stack.enter_context(patch.object(loop, "intervention_context", return_value="사용자 승인 대기 조건 원문"))
            stack.enter_context(patch.object(loop, "gpt_record_context", return_value={
                "history": "SCOPED_HISTORY", "assets": "SCOPED_ASSETS", "limitations": "SCOPED_LIMITATIONS"}))
            stack.enter_context(patch.object(loop, "code_assets_text", side_effect=AssertionError("전체 자산 주입")))
            stack.enter_context(patch.object(loop, "limitations_text", side_effect=AssertionError("전체 한계 주입")))
            stack.enter_context(patch.object(loop, "approach_ledger", return_value={}))
            stack.enter_context(patch.object(loop, "plan_tier", return_value="deep"))
            stack.enter_context(patch.object(loop, "review_tier", return_value="normal"))
            stack.enter_context(patch.object(loop, "set_stage"))
            stack.enter_context(patch.object(loop, "with_retries", side_effect=lambda name, call: call()))
            capture = stack.enter_context(patch.object(loop, "run_codex", side_effect=Captured))
            for stage in (loop.step_plan, loop.step_review):
                with self.assertRaises(Captured):
                    stage(argparse.Namespace(max_think_rounds=4), "변경 없는 연구 목표", 10)
                prompt = capture.call_args.args[1]
                for value in ("SCOPED_HISTORY", "SCOPED_LIMITATIONS", "사용자 승인 대기 조건 원문",
                              "변경 없는 연구 목표", "모델 변경은 추후 판단", "새 원시 결과"):
                    # 새 원시 결과 검증은 리뷰 지침에 있으며 정책에는 새 출력으로 명시된다.
                    if value == "새 원시 결과" and stage == loop.step_plan:
                        value = "새 출력은 새로 검증"
                    self.assertIn(value, prompt)

    def test_models_and_required_review_stay_unchanged(self):
        for tier, effort in (("deep", "high"), ("normal", "medium"), ("light", "low")):
            self.assertEqual(loop.tier_spec("gpt", tier), {"model": "gpt-6-astra", "effort": effort})
        policy = (ROOT / "agent/GPT_USAGE_POLICY.md").read_text()
        for value in ("필수 GPT 리뷰", "독립 수치 재계산", "SHA256", "1라운드", "원본", "영향 범위"):
            self.assertIn(value, policy)


if __name__ == "__main__":
    unittest.main()
