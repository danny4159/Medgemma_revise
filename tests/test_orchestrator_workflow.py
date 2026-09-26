"""일회용 Git 저장소로 연구 판정·코드 보존·재사용을 검사한다. 외부 호출은 하지 않는다."""

import argparse
import contextlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import orchestrator as loop


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "research"
        self.repo.mkdir()
        self.runs = self.root / "agent" / "runs"
        self.runs.mkdir(parents=True)
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        for key, value in {
            "PROJECT_DIR": self.root, "RESEARCH_DIR": self.repo, "RUNS_DIR": self.runs,
            "CODE_ASSETS_FILE": self.root / "agent" / "CODE_ASSETS.md",
            "GOALS_FILE": self.root / "agent" / "GOALS.json",
            "GOAL_FILE": self.root / "agent" / "GOAL.md",
            "LIMITATIONS_FILE": self.root / "agent" / "LIMITATIONS.json",
            "LIMITATIONS_REPORT": self.root / "agent" / "LIMITATIONS.md",
            "RESUME_FILE": self.root / "agent" / "RESUME.md",
            "INTERVENTIONS_DIR": self.root / "agent" / "interventions",
            "LOCK_FILE": self.root / "agent" / ".orchestrator.lock",
        }.items():
            stack.enter_context(patch.object(loop, key, value))
        for name in ("notify", "log", "record_event", "rebuild_index"):
            stack.enter_context(patch.object(loop, name))
        self.git("init", "-b", loop.BASE_BRANCH)
        self.git("config", "user.name", "Workflow Test")
        self.git("config", "user.email", "workflow@example.invalid")
        (self.repo / "base.txt").write_text("기반\n", encoding="utf-8")
        self.git("add", "base.txt")
        self.git("commit", "-m", "기반")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    def record(self, n, filename, value):
        directory = self.runs / f"iter_{n:03d}"
        directory.mkdir(exist_ok=True)
        (directory / filename).write_text(json.dumps(value), encoding="utf-8")

    def plan(self, n, **kwargs):
        self.record(n, "plan.json", {"approach_id": "probe", "approach": "진단", **kwargs})

    def approved(self, n, status="abandon", **kwargs):
        self.record(n, "commit.json", {"sha": self.git("rev-parse", "HEAD")})
        self.record(n, "review.json", {"approach_status": status, "reusable_code": True,
                                       "blocking_issues": [], "reuse_issues": [], **kwargs})

    def test_negative_result_can_be_committed(self):
        self.plan(1)
        loop.history.begin(self.repo, loop.iter_dir(1))
        (self.repo / "useful.py").write_text("VALUE = 1\n", encoding="utf-8")
        loop.checkpoint_code(1, "implementation_finished", final=True)
        loop.step_commit(1, {"approach_status": "abandon", "commit_worthy": True,
                             "commit_message": "유효한 음성 결과의 구현 보존"})
        saved = loop.load_json(loop.iter_dir(1) / "commit.json")
        self.assertEqual(saved["sha"], self.git("rev-parse", "HEAD"))
        self.assertEqual(self.git("show", "HEAD:useful.py"), "VALUE = 1")
        self.assertEqual(self.git("rev-parse", "iter_001"), self.git("rev-parse", "HEAD"))

    def test_new_branch_reuses_approved_negative_result_and_archives_work(self):
        self.git("checkout", "-b", "approach/old")
        (self.repo / "useful.py").write_text("VALUE = 1\n", encoding="utf-8")
        self.git("add", "useful.py")
        self.git("commit", "-m", "재사용 코드")
        self.approved(1)
        self.plan(2, approach_id="new")
        (self.repo / "base.txt").write_text("미검증 수정\n", encoding="utf-8")
        (self.repo / "pending.py").write_text("PENDING = True\n", encoding="utf-8")
        info = loop.ensure_branch(2)
        self.assertEqual(info["branch"], "approach/new")
        self.assertTrue((self.repo / "useful.py").exists())
        self.assertFalse((self.repo / "pending.py").exists())
        self.assertEqual((self.repo / "base.txt").read_text(), "기반\n")
        archive = loop.load_json(loop.iter_dir(2) / "code_archive.json")
        # 일회용 저장소의 stash만 제거하여 영구 ref의 독립 보존을 확인한다.
        self.git("stash", "drop", "stash@{0}")
        self.assertEqual(self.git("show", archive["ref"] + ":base.txt"), "미검증 수정")
        self.assertEqual(self.git("show", archive["ref"] + "^3:pending.py"), "PENDING = True")
        self.assertIn("pending.py", (loop.iter_dir(2) / "stashed.patch").read_text())
        self.assertIn(archive["ref"], loop.CODE_ASSETS_FILE.read_text())

    def test_explicit_base_and_unresolved_reuse_issues(self):
        self.git("checkout", "-b", "approach/old")
        self.approved(1)
        self.plan(2, reuse_iteration=1)
        self.assertEqual(loop.reuse_base(2, "approach/old"), self.git("rev-parse", "HEAD"))
        self.approved(1, reuse_issues=["입력 연결 검증 필요"])
        self.assertIsNone(loop.reusable_commit(1))
        with self.assertRaises(loop.AgentError):
            loop.reuse_base(2, "approach/old")

    def test_invalid_reuse_rejected_before_stashing(self):
        self.git("checkout", "-b", "approach/old")
        self.plan(2, approach_id="new", reuse_iteration=2)
        (self.repo / "pending.py").write_text("PENDING = True\n", encoding="utf-8")
        with self.assertRaises(loop.AgentError):
            loop.ensure_branch(2)
        self.assertTrue((self.repo / "pending.py").exists())
        self.assertEqual(self.git("stash", "list"), "")
        self.assertEqual(self.git("branch", "--show-current"), "approach/old")

    def test_legacy_success_remains_reusable_but_abandon_does_not(self):
        self.record(1, "commit.json", {"sha": self.git("rev-parse", "HEAD")})
        self.record(1, "review.json", {"approach_status": "success"})
        self.assertIsNotNone(loop.reusable_commit(1))
        self.record(1, "review.json", {"approach_status": "abandon"})
        self.assertIsNone(loop.reusable_commit(1))

    def test_only_valid_experiments_count_toward_reassessment(self):
        for n, validity in enumerate([True, False, False, None], 1):
            self.plan(n)
            review = {"approach_status": "improve"}
            if validity is not None:
                review["valid_experiment"] = validity
            self.record(n, "review.json", review)
        entry = loop.approach_ledger(upto=4)["probe"]
        self.assertEqual(entry["attempts"], 4)
        self.assertEqual(entry["valid_experiments"], 1)
        self.assertEqual(entry["unclassified_experiments"], 1)

    def test_reassessment_accepts_reason_and_resets_at_goal_boundary(self):
        for n in range(1, 4):
            self.plan(n)
            self.record(n, "review.json", {"approach_status": "improve", "valid_experiment": True})
        self.plan(4)
        self.assertTrue(loop.plan_concerns(4, loop.load_plan(4)))
        self.plan(4, continuation_reason="새 독립 자료에서 정보 이득 검증 후 중단")
        self.assertEqual(loop.plan_concerns(4, loop.load_plan(4)), [])
        self.plan(4)
        loop.GOALS_FILE.write_text(json.dumps([
            {"start_iter": 1, "goal": "이전 목표"}, {"start_iter": 4, "goal": "새 목표"},
        ]), encoding="utf-8")
        self.assertEqual(loop.plan_concerns(4, loop.load_plan(4)), [])

    def test_reopening_abandoned_design_requires_new_evidence(self):
        self.plan(1)
        self.record(1, "review.json", {"approach_status": "abandon", "valid_experiment": True})
        self.plan(2)
        self.assertTrue(loop.plan_concerns(2, loop.load_plan(2)))
        self.plan(2, continuation_reason="기존 기각 범위 밖의 조건과 새 근거")
        self.assertEqual(loop.plan_concerns(2, loop.load_plan(2)), [])

    def test_scientific_experiments_cannot_skip_review(self):
        self.plan(1, experiment_role="diagnostic", review_mode="skip")
        should_review, _ = loop.review_decision(argparse.Namespace(always_review=False), 1)
        self.assertTrue(should_review)

    def test_review_receives_execution_amendment(self):
        self.plan(1)
        (loop.iter_dir(1) / "execution_amendment.md").write_text("재개 보완 내용", encoding="utf-8")
        with patch.object(loop, "review_tier", return_value="deep"), \
                patch.object(loop, "with_retries", side_effect=lambda name, call: call()), \
                patch.object(loop, "run_codex", side_effect=RuntimeError("검증용 종료")) as run:
            with self.assertRaisesRegex(RuntimeError, "검증용 종료"):
                loop.step_review(argparse.Namespace(), "연구 목표", 1)
        self.assertIn("재개 보완 내용", run.call_args.args[1])


class SchemaTests(unittest.TestCase):
    def test_new_fields_are_required_and_have_legacy_defaults(self):
        for filename, defaults, fields in (
            ("plan_schema.json", loop.PLAN_DEFAULTS,
             ["experiment_role", "research_question", "contribution_path", "baseline_plan",
              "reuse_iteration", "reuse_assets", "continuation_reason", "limitation_ids"]),
            ("review_schema.json", loop.REVIEW_DEFAULTS,
             ["valid_experiment", "reusable_code", "failure_scope", "goal_progress",
              "blocking_issues", "reuse_issues", "deferred_issues", "limitation_updates", "code_assets"]),
        ):
            schema = json.loads((loop.PROMPT_DIR / filename).read_text())
            self.assertEqual(set(schema["required"]), set(schema["properties"]))
            self.assertFalse(schema["additionalProperties"])
            for field in fields:
                self.assertIn(field, schema["required"])
                self.assertIn(field, defaults)
        schema = json.loads((loop.PROMPT_DIR / "review_schema.json").read_text())
        self.assertTrue({"inconclusive", "execution_failed"}.issubset(
            schema["properties"]["approach_status"]["enum"]))


if __name__ == "__main__":
    unittest.main()
