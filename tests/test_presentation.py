"""외부 호출 없이 표시 한도·판정 구분·기계 판독 형식 보존을 검증한다."""

import copy
import unittest

import orchestrator as loop
from presentation import STATUS_LABELS, excerpt, iteration_result, notice, units


class PresentationTests(unittest.TestCase):
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

    def test_all_critical_caveats_preserved_without_mutation(self):
        review = {"verdict": "CONTINUE", "approach_status": "inconclusive",
                  "one_line_summary": "실험 실행", "goal_progress": "아직 개선 입증 못함",
                  "failure_scope": "모델 한계로 일반화 불가", "blocking_issues": ["표본 부족"],
                  "reuse_issues": ["경계값 수정 필요"], "next_task": "표본 추가"}
        original = copy.deepcopy(review)
        result = iteration_result(9, review)
        for value in ("모델 한계로 일반화 불가", "표본 부족", "경계값 수정 필요", "아직 개선 입증 못함"):
            self.assertIn(value, result)
        self.assertEqual(review, original)

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
