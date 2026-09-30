"""투자 판단과 환경 구성 권한의 전달을 검증한다. 설치·외부 호출은 하지 않는다."""

import argparse
import json
from pathlib import Path
import unittest

import orchestrator as loop


ROOT = Path(__file__).resolve().parents[1]


class ConvergencePolicyTests(unittest.TestCase):
    def test_environment_permissions_remove_blanket_install_ban(self):
        permissions = json.loads((ROOT / "agent/claude_settings.json").read_text())["permissions"]
        for rule in ("Bash(pip *)", "Bash(conda *)"):
            self.assertNotIn(rule, permissions["deny"])
        for rule in ("Bash(python *)", "Bash(conda create *)", "Bash(conda run *)"):
            self.assertIn(rule, permissions["allow"])
        for rule in ("Bash(sudo *)", "Bash(rm *)", "Bash(git reset *)", "Bash(git push *)"):
            self.assertIn(rule, permissions["deny"])

    def test_permissions_are_scoped_by_environment_policy(self):
        agents = (ROOT / "AGENTS.md").read_text()
        self.assertNotIn("`conda activate`, `pip install`은 하지 않는다", agents)
        resource = (ROOT / "agent/RESOURCE_POLICY.md").read_text()
        for text in ("별도 사용자 승인 없이", "read-only", "제자리에서 변경하지 않는다",
                     "research/results/environments/<name>", "작은 실제 입력", "학습 데이터 중복",
                     "시스템/드라이버 변경·sudo", "재승인 대기로 돌리지 않는다"):
            self.assertIn(text, resource)

    def test_current_run_and_scientific_gates_are_preserved(self):
        policy = (ROOT / "agent/RESEARCH_POLICY.md").read_text().split(
            "## 진단의 수렴과 비교군 확보", 1)[1].split("## 사용자 논문 추천", 1)[0]
        for text in ("현재 iter_043은 원 계획", "superseded 처리하지 않는다", "과거 판정",
                     "blocking_issues를 지우거나 gate를 우회하지 않는다", "한정 재측정",
                     "직접 joint SFT", "MedGrounder", "보류하고 중요한 다른 질문",
                     "종료 조건", "기계적으로 강제하지 않고"):
            self.assertIn(text, policy)

    def test_next_call_receives_both_updates_and_roles_reference_them(self):
        context = loop.resource_context(argparse.Namespace(gpus="0,1", claude_timeout=0))
        self.assertIn("실험 환경 구성 권한 — 2026-10-01", context)
        self.assertIn("진단의 수렴과 비교군 확보 — 2026-10-01", context)
        for name in ("gpt_plan", "gpt_review"):
            prompt = (ROOT / f"agent/prompts/{name}.md").read_text()
            self.assertIn("진단의 수렴과 비교군 확보", prompt)
            self.assertIn("iter_043", prompt)
        engineer = (ROOT / "agent/prompts/claude_engineer.md").read_text()
        self.assertIn("격리 환경 생성·버전 조정", engineer)


if __name__ == "__main__":
    unittest.main()
