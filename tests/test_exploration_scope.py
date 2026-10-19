"""현행 연구 정책·질문 카드·역사 분리와 호출 전달 검사. 외부 호출 없음."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import orchestrator as loop

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "agent/interventions/archives/20261013_policy_consolidation"
CARD = ("중요한 문제", "현재 근거", "쉬운 해결책", "남은 설명", "다음 결정")


class ExplorationScopeTests(unittest.TestCase):
    def test_archives_preserve_exact_pre_consolidation_bytes(self):
        manifest = json.loads((ARCHIVE / "MANIFEST.json").read_text())
        self.assertEqual(len(manifest["files"]), 5)
        for entry in manifest["files"]:
            with self.subTest(source=entry["source"]):
                path = ROOT / entry["archive"]
                self.assertTrue(path.is_file())
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])

    def test_retired_directions_are_preserved_but_not_live_instructions(self):
        archived = (ARCHIVE / "RESEARCH_FOCUS.md").read_text()
        for marker in ("iter_119 이후 연구 후보 재선택", "iter_118 이후 정보 보존",
                       "iter_116 이후 본비교 복구", "iter_097은 원 계획"):
            self.assertIn(marker, archived)
            self.assertNotIn(marker, loop.research_context())
        self.assertIn("과거 지시는 현재 명령이 아님", loop.research_context())

    def test_question_card_reaches_planner_reviewer_and_current_focus(self):
        for path in ("agent/RESEARCH_POLICY.md", "agent/RESEARCH_FOCUS.md",
                     "agent/prompts/gpt_plan.md", "agent/prompts/gpt_review.md"):
            content = (ROOT / path).read_text()
            for label in CARD:
                self.assertIn(label, content, (path, label))
        review = (ROOT / "agent/prompts/gpt_review.md").read_text()
        self.assertIn("이전 판단 → 추가 증거 → 현재 판단", review)

    def test_data_preflight_precedes_detailed_implementation(self):
        policy = (ROOT / "agent/RESEARCH_POLICY.md").read_text()
        plan = (ROOT / "agent/prompts/gpt_plan.md").read_text()
        for term in ("핵심 자료 조건", "결정적", "read-only", "임상"):
            self.assertIn(term, policy)
            self.assertIn(term, plan)
        self.assertIn("비변경 조회·집계", plan)
        self.assertIn("다운로드·모델 실험은 하지 않는다", plan)
        self.assertIn("짧은 자료 확인과 조건부 실행", plan)
        self.assertIn("조건 성립 전에 대규모 모델 설치", policy)
        self.assertIn("임상 의미나 longitudinal 동일 병변을 추측해 만들지 않는다", policy)

    def test_pilot_is_causal_test_not_final_method_or_gate_bypass(self):
        policy = (ROOT / "agent/RESEARCH_POLICY.md").read_text()
        for term in ("작은 원인 검증", "경쟁 설명", "본격 방법 개발",
                     "method_stage=pilot", "method_stage=full", "validated",
                     "evidence·usage_checks·blocking 없음", "method gate를 우회하지 않는다",
                     "원인·최종 신규성", "독립 확인", "실제 관찰 범위를 넘어 일반화하지 않는다"):
            self.assertIn(term, policy)
        for name in ("gpt_plan", "gpt_review", "claude_engineer"):
            prompt = (ROOT / f"agent/prompts/{name}.md").read_text()
            for title in ("탐색 효율과 실제 투자 선택", "기술 질문·자료·평가의 공동 선택",
                          "탐색용 학습과 연구 질문의 별도 판정"):
                self.assertIn(title, prompt)

    def test_previous_scope_preserves_holds_and_pending_approval_in_archive(self):
        focus = (ROOT / "agent/interventions/archives/20261013_mrrate_switch/RESEARCH_FOCUS.md").read_text()
        for term in ("모델 실험 전에 종료", "승인 대기", "현재 초안 교정 묶음",
                     "CURE 특화 오류 검토", "원 출력의 재채점", "discovery·TOF는 재개하지",
                     "구현 기본 의사는 Claude", "--confirm-each-iter", "보완 적용만으로 재개하지"):
            self.assertIn(term, focus)

    def test_history_index_has_sources_not_auto_execution(self):
        index = (ROOT / "agent/RESEARCH_HISTORY_INDEX.md").read_text()
        for term in ("iter_120/review.md", "iter_119/review.md", "iter_115/review.md",
                     "iter_097/review.md", "iter_048/review.md", "iter_012/review.md",
                     "자동 실행 목록", "이후 원 기록을 우선"):
            self.assertIn(term, index)

    def test_context_reload_routes_without_reading_archives(self):
        args = argparse.Namespace(engineer="claude", gpus="0,1", claude_timeout=0)
        with tempfile.TemporaryDirectory() as directory, patch.object(loop, "AGENT_DIR", Path(directory)):
            root = Path(directory)
            focus = root / "RESEARCH_FOCUS.md"
            index = root / "RESEARCH_HISTORY_INDEX.md"
            focus.write_text("첫 질문")
            index.write_text("첫 원문 위치")
            archive = root / "interventions/archives"
            archive.mkdir(parents=True)
            (archive / "old.md").write_text("종료한 GPU 실험을 다시 실행")
            original_read = loop.read

            def checked_read(path, *args, **kwargs):
                self.assertNotIn("archives", Path(path).parts)
                return original_read(path, *args, **kwargs)

            with patch.object(loop, "read", side_effect=checked_read):
                first = loop.resource_context(args)
                focus.write_text("갱신 질문")
                index.write_text("갱신 원문 위치")
                second = loop.resource_context(args)
            self.assertIn("첫 질문", first)
            self.assertIn("갱신 질문", second)
            self.assertIn("갱신 원문 위치", second)
            self.assertNotIn("종료한 GPU 실험을 다시 실행", second)

    def test_all_backends_receive_live_context_not_archive_payload(self):
        for backend in ("claude", "codex"):
            args = argparse.Namespace(engineer=backend, gpus="0,1", claude_timeout=0)
            context = loop.resource_context(args)
            for path in ("agent/RESEARCH_POLICY.md", "agent/RESEARCH_FOCUS.md",
                         "agent/RESEARCH_HISTORY_INDEX.md"):
                self.assertIn((ROOT / path).read_text().strip(), context)
            self.assertNotIn((ARCHIVE / "RESEARCH_FOCUS.md").read_text().strip(), context)
            self.assertIn("이후 사용자 승인", context)

    def test_missing_optional_focus_and_index_are_backward_compatible(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(loop, "AGENT_DIR", Path(directory)):
            context = loop.research_context()
            self.assertIn("별도 초점 없음", context)
            self.assertIn("별도 이력 색인 없음", context)

    def test_missing_required_policy_stops_before_model_call(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(loop, "RESEARCH_POLICY_FILE", Path(directory) / "missing.md"):
            with self.assertRaises(loop.AgentError):
                loop.research_context()

    def test_current_policy_is_smaller_without_truncating_source_files(self):
        before = sum(len((ARCHIVE / name).read_text()) for name in ("RESEARCH_POLICY.md", "RESEARCH_FOCUS.md"))
        after = sum(len((ROOT / "agent" / name).read_text()) for name in
                    ("RESEARCH_POLICY.md", "RESEARCH_FOCUS.md", "RESEARCH_HISTORY_INDEX.md"))
        self.assertLess(after, before / 2)
        policy = (ROOT / "agent/RESEARCH_POLICY.md").read_text()
        for term in ("가설 판정과 코드 보존은 별개", "단계별 표본·학습·평가 규모",
                     "사용자 논문 추천", "blocking_issues", "checkpoints/", "reuse_assets",
                     "별도 사용자", "--handoff-engineer"):
            # 별도 권한의 문구는 설치 정책에 보존한다.
            combined = policy + (ROOT / "agent/RESOURCE_POLICY.md").read_text()
            self.assertIn(term, combined)

    def test_engineer_keeps_prespecified_gate_and_truthful_timestamps(self):
        prompt = (ROOT / "agent/prompts/claude_engineer.md").read_text()
        for term in ("사건 수 문턱·비율 조건을 임의 추가하지 않는다", "실제 시점",
                     "생성 이후 작성한 평가기를 사전 잠금으로 보고하지 않는다"):
            self.assertIn(term, prompt)

    def test_progress_reporting_uses_existing_summary_renderer(self):
        from presentation import iteration_result
        text = "실행 복구만 완료 — 연구 판단은 그대로"
        self.assertIn(text, (ROOT / "agent/REPORTING_STYLE.md").read_text())
        message = iteration_result(97, {
            "verdict": "CONTINUE", "approach_status": "execution_failed", "valid_experiment": False,
            "one_line_summary": "재개 가능", "next_task": "원 비교 완료",
            "review_markdown": "## 알림 요약\n- 결과: checkpoint 보존\n- 의미: " + text,
        })
        self.assertIn(text, message)


if __name__ == "__main__":
    unittest.main()
