"""외부 호출 없이 표시 한도·판정 구분·기계 판독 형식 보존을 검증한다."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import orchestrator as loop
from presentation import (STATUS_LABELS, excerpt, iteration_result, notice, result_highlight, units,
                          summary_section, research_context, plan_ready, stage_notice, transition_text)


class PresentationTests(unittest.TestCase):
    def context_plan(self, dataset="척추 MRI(SPIDER)", change="이어감"):
        return {"plan_markdown": f"""# 요약

## 알림 맥락
- 연구: 디스크 판독의 위치 전이
- 데이터: {dataset}
- 모델: MedGemma 1.5 · LoRA 학습
- 과제: 디스크 손상 등급을 답하기
- 가설: 일부 위치에서 배운 판독이 다른 위치에도 전이될 수 있다
- 질문: 배우지 않은 위치에서도 손상 등급을 판독하는가?
- 변경: {change}
- 연결: 기존 질문은 유지하고 실행 문제만 복구한다.
- 작업: 저장 후 재개가 정확한지 확인한 뒤 본학습 비교를 끝낸다.

## 상세
- 데이터: 여기에 쓴 값은 알림 필드가 아님
""", "research_question": "상세 연구 질문", "plan_summary": "상세 작업", "continuation_reason": ""}

    def test_context_section_is_scoped_and_display_only(self):
        plan = self.context_plan()
        before = copy.deepcopy(plan)
        self.assertEqual(research_context(plan)["데이터"], "척추 MRI(SPIDER)")
        self.assertEqual(summary_section("## Other\n- 연구: 무관", "알림 맥락"), {})
        plan_ready(77, plan, engineer="Claude")
        self.assertEqual(plan, before)

    def test_dataset_change_is_visible_with_previous_iteration(self):
        old = self.context_plan("무릎 MRI(OAI)")
        new = self.context_plan(change="방향 전환")
        result = plan_ready(75, new, old, engineer="Claude")
        self.assertIn("🔀", result)
        self.assertIn("무릎 MRI(OAI) → 척추 MRI(SPIDER)", result)
        self.assertIn("iter_074 → iter_075", result)
        self.assertIn("배우지 않은 위치", result)
        self.assertNotIn("계획대로 자동 진행", result)
        self.assertIn("실제 학습 시작·완료를 뜻하지 않습니다", result)

    def test_recovery_is_not_presented_as_new_direction_or_result(self):
        result = plan_ready(77, self.context_plan(change="실행 복구"), self.context_plan())
        self.assertIn("🔧", result)
        self.assertIn("실행 복구", result)
        self.assertNotIn("방향 전환", result)
        self.assertNotIn("💡", result)
        self.assertNotIn("데이터:", transition_text(77, self.context_plan(), self.context_plan()))

    def test_legacy_plan_does_not_invent_dataset_or_hypothesis(self):
        result = plan_ready(9, {"plan_summary": "저장 상태 확인", "research_question": "위치 판독 가능성"})
        self.assertIn("저장 상태 확인", result)
        self.assertIn("위치 판독 가능성", result)
        self.assertNotIn("SPIDER", result)
        self.assertNotIn("방향 전환", result)

    def test_plan_and_review_stages_are_not_experiment_completion(self):
        planning = stage_notice(78, "GPT 계획", previous=self.context_plan(),
                                previous_review={"one_line_summary": "재개 검사가 실패했다"})
        self.assertIn("직전 연구의 질문", planning)
        self.assertIn("새 과제는 아직 확정 전", planning)
        self.assertIn("재개 검사가 실패했다", planning)
        reviewing = stage_notice(77, "GPT 리뷰", self.context_plan())
        self.assertIn("결과 검증 중", reviewing)
        self.assertIn("최종 판정 전", reviewing)

    def test_execution_failure_keeps_context_and_is_not_negative_hypothesis(self):
        review = {"approach_status": "execution_failed", "valid_experiment": False,
                  "one_line_summary": "내부 요약", "next_task": "원래 계획",
                  "review_markdown": """## 알림 요약
- 결과: 일반 분류기는 학습했지만 VLM 학습은 실행 오류로 미완료다.
- 의미: 위치 전이가 가능한지는 아직 모른다.
- 후속: 재개 오류를 고친 뒤 같은 비교를 끝낼 것을 제안한다.
"""}
        before = copy.deepcopy(review)
        result = iteration_result(77, review, self.context_plan())
        for expected in ("⚠️", "가설 판단 전", "척추 MRI", "위치 전이", "다음 계획에 제안", "재개 오류"):
            self.assertIn(expected, result)
        self.assertNotIn("💡", result)
        self.assertEqual(review, before)

    def test_setup_success_is_not_reported_as_scientific_result(self):
        result = iteration_result(74, {"approach_status": "success", "valid_experiment": False})
        self.assertIn("준비·코드 검증 결과", result)
        self.assertNotIn("중요한 결과", result)

    def test_short_notice_preserves_numbers_and_caveats(self):
        evidence = "baseline 0.71 → 0.73, n=40. 작은 표본이라 개선 확정 불가."
        result = notice("결과", [("근거", evidence), ("다음", "독립 평가")],
                        reference="agent/runs/iter_009/review.md", actions="ok → 계속\nq → 종료")
        self.assertIn(evidence, result)
        self.assertNotIn("축약", result)
        self.assertLess(result.index(evidence), result.index("답장 방법"))

    def test_long_unicode_notice_retains_commands_and_reference(self):
        actions = "ok 또는 1\n2, 3…\nf 지시내용\np 지시내용\nt creative|heavy|standard|light\nr full|skip\na\nq"
        reference = "agent/runs/iter_009/plan.md"
        for count in (1, 2, 4):
            with self.subTest(fields=count):
                result = notice("🙋 계획 확인", [(f"항목 {n}", "실험🧪 " * 5000) for n in range(count)],
                                reference=reference, actions=actions)
                self.assertLessEqual(units(result), 3200)
                self.assertIn(actions, result)
                self.assertIn(reference, result)
                self.assertIn("[축약]", result)
                self.assertIn("중요한 결정 전 원문을 확인하세요", result)

    def test_statuses_do_not_imply_goal_completion(self):
        for status, label in STATUS_LABELS.items():
            with self.subTest(status=status):
                result = iteration_result(9, {"verdict": "CONTINUE", "approach_status": status,
                                              "one_line_summary": "검증 결과", "next_task": "후속 확인"})
                self.assertIn(label, result)
                self.assertNotIn("연구 목표 달성", result)
                self.assertIn("후속 확인", result)

    def test_skipped_review_is_explicit_and_points_to_actual_report(self):
        result = iteration_result(9, {"skipped": True, "verdict": "CONTINUE"})
        self.assertIn("GPT 리뷰 미실시", result)
        self.assertIn("claude_report.md", result)
        self.assertNotIn("/review.md", result)

    def test_done_is_goal_completion(self):
        self.assertIn("연구 목표 달성", iteration_result(9, {"verdict": "DONE"}))

    def test_conclusion_caveats_preserved_and_code_details_left_in_original(self):
        review = {"verdict": "CONTINUE", "approach_status": "inconclusive",
                  "one_line_summary": "실험 실행", "goal_progress": "아직 개선 입증 못함",
                  "failure_scope": "모델 한계로 일반화 불가", "blocking_issues": ["표본 부족"],
                  "reuse_issues": ["경계값 수정 필요"], "next_task": "표본 추가"}
        original = copy.deepcopy(review)
        result = iteration_result(9, review)
        for value in ("모델 한계로 일반화 불가", "표본 부족", "재사용 전 코드 보완 1건"):
            self.assertIn(value, result)
        self.assertEqual(review, original)

    def test_routine_alert_is_compact_without_changing_source(self):
        review = {"verdict": "CONTINUE", "approach_status": "inconclusive",
                  "one_line_summary": "n=48에서 개선은 불확정. " * 100,
                  "goal_progress": "상세 논의 " * 1000, "failure_scope": "현재 표본에 한정",
                  "reuse_issues": [f"구현 보완 {i}" for i in range(30)],
                  "next_task": "독립 표본으로 확인한다. " * 200}
        before = copy.deepcopy(review)
        result = iteration_result(26, review)
        self.assertLessEqual(units(result), 1000)
        self.assertIn("판단 보류", result)
        self.assertIn("현재 표본에 한정", result)
        self.assertIn("재사용 전 코드 보완 30건", result)
        self.assertNotIn("상세 논의", result)
        self.assertIn("review.md", result)
        self.assertEqual(review, before)

    def test_meaningful_negative_observation_can_be_highlighted_without_success_claim(self):
        review = {"verdict": "CONTINUE", "approach_status": "inconclusive", "valid_experiment": True,
                  "milestone": {"is_milestone": True, "title": "박스 점수와 질문 활용이 다르게 움직임"},
                  "one_line_summary": "개발 48명에서 관찰. 원인·일반화는 미확인.",
                  "failure_scope": "개발 자료만 평가", "next_task": "독립 자료로 확인"}
        result = iteration_result(26, review)
        self.assertIn("💡🔎", result)
        self.assertIn("박스 점수와 질문 활용", result)
        self.assertIn("판단 보류", result)
        self.assertIn("미확인", result)
        self.assertNotIn("연구 목표 달성", result)

    def test_invalid_unreviewed_or_blocked_results_never_get_discovery_badge(self):
        base = {"verdict": "CONTINUE", "approach_status": "success", "valid_experiment": True,
                "milestone": {"is_milestone": True, "title": "발견 주장"}}
        for update in ({"valid_experiment": False}, {"valid_experiment": None}, {"skipped": True},
                       {"blocking_issues": ["정답 연결 오류"]}, {"approach_status": "execution_failed"}):
            review = {**base, **update}
            self.assertEqual(result_highlight(review), "")
            self.assertNotIn("💡", iteration_result(26, review))
        self.assertNotIn("💡", iteration_result(26, {"approach_status": "success", "valid_experiment": True}))

    def test_decision_request_keeps_short_permissions_and_all_reply_commands(self):
        question = "유료 접근 권한이 필요합니다. 비용 승인 없이 실행하지 않습니다."
        commands = "1 승인된 자료 사용\n2 후보 보류\np 지시 → 재계획\nq 종료"
        result = notice("🙋 결정 필요", [("질문", question), ("대안", "1 자료 제공\n2 보류")],
                        reference="agent/runs/iter_026/plan.md", actions=commands)
        self.assertIn(question, result)
        self.assertIn(commands, result)

    def test_milestone_story_is_preserved_without_a_duplicate_notification(self):
        story = "고민과 근거·음성 결과 및 미확인 범위를 상세히 보존한다.\n" * 30
        review = {"verdict": "CONTINUE", "approach_status": "inconclusive", "valid_experiment": True,
                  "milestone": {"is_milestone": True, "title": "중요한 음성 관찰", "story": story}}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(loop, "JOURNEY_FILE", Path(directory) / 'JOURNEY.md'), \
                patch.object(loop, "load_plan", return_value={}), \
                patch.object(loop, "approach_ledger", return_value={}), \
                patch.object(loop, "record_event"), patch.object(loop, "rebuild_index"), \
                patch.object(loop, "notify") as notify:
            loop.handle_milestone(26, review)
            self.assertIn(story.strip(), loop.JOURNEY_FILE.read_text())
            notify.assert_not_called()
            self.assertIn("💡🔎", iteration_result(26, review))

    def test_excerpt_respects_utf16_and_marks_truncation(self):
        self.assertEqual(excerpt("정확한 수치 0.123", 100), "정확한 수치 0.123")
        self.assertLessEqual(units(excerpt("🧪" * 100, 50)), 50)
        self.assertTrue(excerpt("🧪" * 100, 50).endswith("[축약]"))

    def test_missing_optional_values_do_not_render_none(self):
        result = iteration_result(9, {"blocking_issues": None, "reuse_issues": None})
        self.assertNotIn("None", result)
        self.assertIn("판정 확인 필요", result)

    def test_human_summary_does_not_change_machine_trailers(self):
        for status in ("PASS", "FAIL"):
            report = f"# 요약\n\n- 핵심: 실제 실행 결과를 요약함.\n\n# 상세\n\n검증 근거\n\nSELF_CHECK: {status}\nSUMMARY: 검증 범위 확인 필요\n"
            self.assertEqual(loop.parse_trailer(report, "SELF_CHECK"), status)
            self.assertEqual(loop.parse_trailer(report, "SUMMARY"), "검증 범위 확인 필요")


if __name__ == "__main__":
    unittest.main()
