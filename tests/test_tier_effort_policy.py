"""사용자가 지정한 effort와 리뷰 연결을 검증한다. 실제 모델 호출은 없다."""

import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import codex_engineer
import orchestrator as loop


class TierEffortPolicyTests(unittest.TestCase):
    def test_requested_matrix_and_unchanged_models(self):
        expected = {
            "gpt": {"deep": ("gpt-6-astra", "high"),
                    "normal": ("gpt-6-astra", "low"), "light": ("gpt-6-astra", "low")},
            "codex_engineer": {"creative": ("gpt-6-astra", "high"),
                               "heavy": ("gpt-6-astra", "medium"),
                               "standard": ("gpt-6-astra", "low"),
                               "light": ("gpt-6-astra", "low")},
            "claude": {"creative": ("opus", "high"), "heavy": ("opus", "low"),
                       "standard": ("sonnet", "medium"), "light": ("sonnet", "medium")},
        }
        for agent, tiers in expected.items():
            for tier, (model, effort) in tiers.items():
                with self.subTest(agent=agent, tier=tier):
                    self.assertEqual(loop.tier_spec(agent, tier), {"model": model, "effort": effort})

    def test_review_mapping_and_explicit_override(self):
        args = argparse.Namespace(gpt_tier=None)
        for tier, effort in {"standard": "low", "heavy": "low", "light": "low", "creative": "high"}.items():
            with self.subTest(tier=tier), patch.object(loop, "tiers_used", return_value={"claude": tier}):
                self.assertEqual(loop.tier_spec("gpt", loop.review_tier(args, 1))["effort"], effort)
                self.assertEqual(loop.review_tier(argparse.Namespace(gpt_tier="deep"), 1), "deep")

    def test_codex_engineer_command_effort(self):
        for tier, effort in {"standard": "low", "heavy": "medium", "creative": "high", "light": "low"}.items():
            for resume in (None, "saved-session"):
                with self.subTest(tier=tier, resume=resume):
                    cmd = codex_engineer.command(loop.tier_spec("codex_engineer", tier), resume)
                    self.assertIn(f'model_reasoning_effort="{effort}"', cmd)

    def test_planner_and_claude_commands_use_current_effort(self):
        args = argparse.Namespace(gpus=None, gpt_timeout=30, claude_timeout=0)
        with tempfile.TemporaryDirectory() as tmp, patch.object(loop, "resource_context", return_value=""):
            root = Path(tmp)
            output = root / "output.json"

            def run_gpt(cmd, *unused, **kwargs):
                self.assertIn('model_reasoning_effort="low"', cmd)
                output.write_text("{}", encoding="utf-8")

            with patch.object(loop, "run_streaming", side_effect=run_gpt):
                loop.run_codex(args, "계획", output, root / "gpt.log", "normal")

            def run_claude(cmd, log, timeout, env, on_line, **kwargs):
                self.assertEqual(cmd[cmd.index("--effort") + 1], "low")
                self.assertEqual(cmd[cmd.index("--model") + 1], "opus")
                on_line('{"type":"result","result":"완료","is_error":false}')

            with patch.object(loop, "run_streaming", side_effect=run_claude):
                loop.run_claude(args, "구현", root / "claude.log", "heavy", resume_id="saved-session")


if __name__ == "__main__":
    unittest.main()
