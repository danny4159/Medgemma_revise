"""일회용 Git 저장소에서 체크포인트·선별 재사용·사용자 변경 보호를 검사한다."""

import argparse
import json
from unittest.mock import patch
import unittest

import orchestrator as loop
import research_history as history
import test_orchestrator_workflow as fixtures


class HistoryTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    git = fixtures.WorkflowTests.git
    record = fixtures.WorkflowTests.record
    plan = fixtures.WorkflowTests.plan

    def start(self):
        self.plan(1)
        self.d = loop.iter_dir(1)
        history.begin(self.repo, self.d)

    def checkpoint(self, reason="implementation_finished"):
        return history.checkpoint(self.repo, self.d, 1, reason)

    def source(self):
        (self.repo / "loader.py").write_text("VALUE = 42\n")
        self.git("add", "loader.py")
        self.git("commit", "-m", "재사용 출처")
        sha = self.git("rev-parse", "HEAD")
        self.git("checkout", "-b", "approach/new", "HEAD~1")
        return [{"source_commit": sha, "paths": ["loader.py"], "reason": "검증된 데이터 로더 재사용",
                 "required_checks": ["관련 단위 테스트와 입력 provenance 확인"]}]

    def test_checkpoint_survives_failed_review_and_contains_new_files(self):
        self.start()
        (self.repo / "buggy.py").write_text("raise RuntimeError('아직 실패')\n")
        entry = loop.checkpoint_code(1, "implementation_finished", final=True)
        self.assertIn("buggy.py", self.git("ls-tree", "--name-only", entry["sha"]))
        loop.step_commit(1, {"commit_worthy": False, "approach_status": "execution_failed", "reusable_code": False})
        self.assertEqual(self.git("rev-parse", "HEAD"), entry["sha"])
        self.assertIn("buggy.py", (self.d / "changes.patch").read_text())
        self.assertEqual(self.git("diff", "HEAD"), "")
        self.assertIsNone(loop.reusable_commit(1))

    def test_interrupted_resume_and_noop_do_not_duplicate_commits(self):
        self.start()
        (self.repo / "code.py").write_text("VALUE = 1\n")
        first = self.checkpoint("interrupted")
        self.assertEqual(self.checkpoint()["sha"], first["sha"])
        (self.repo / "code.py").write_text("VALUE = 2\n")
        second = self.checkpoint()
        self.assertEqual(self.git("rev-parse", second["sha"] + "^"), first["sha"])
        self.assertEqual(self.git("show", first["ref"] + ":code.py"), "VALUE = 1")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_reverting_to_original_is_preserved_after_partial_checkpoint(self):
        self.start()
        (self.repo / "base.txt").write_text("변경\n")
        first = self.checkpoint("interrupted")
        (self.repo / "base.txt").write_text("기반\n")
        second = self.checkpoint()
        self.assertNotEqual(first["sha"], second["sha"])
        self.assertEqual(self.git("show", "HEAD:base.txt"), "기반")

    def test_preexisting_user_changes_and_index_are_preserved(self):
        (self.repo / "user.py").write_text("USER = True\n")
        self.git("add", "user.py")
        (self.repo / "base.txt").write_text("사용자 수정\n")
        self.start()
        (self.repo / "agent.py").write_text("AGENT = True\n")
        entry = self.checkpoint()
        self.assertEqual(self.git("show", "HEAD:base.txt"), "기반")
        self.assertNotIn("user.py", self.git("ls-tree", "--name-only", "HEAD"))
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "user.py")
        self.assertIn("base.txt", entry["unpreserved_paths"])
        self.assertEqual((self.repo / "base.txt").read_text(), "사용자 수정\n")

    def test_external_staging_is_not_included(self):
        self.start()
        (self.repo / "user.py").write_text("USER = 1\n")
        self.git("add", "user.py")
        (self.repo / "agent.py").write_text("VALUE = 1\n")
        self.checkpoint()
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "user.py")

    def test_secrets_data_large_and_symlinks_are_excluded(self):
        self.start()
        (self.repo / ".env").write_text("KEY=hidden\n")
        (self.repo / "settings.py").write_text("KEY = 'hf_" + "a" * 30 + "'\n")
        (self.repo / "results").mkdir()
        (self.repo / "results" / "data.json").write_text("{}")
        (self.repo / "big.py").write_bytes(b"a" * (history.MAX_BYTES + 1))
        (self.repo / "link.py").symlink_to(self.root / "elsewhere")
        (self.repo / "ok.py").write_text("VALUE = 1\n")
        entry = self.checkpoint()
        self.assertTrue({".env", "settings.py", "big.py"}.issubset(entry["unpreserved_paths"]))
        self.assertEqual(set(self.git("ls-tree", "--name-only", "HEAD").splitlines()), {"base.txt", "ok.py"})
        self.assertTrue((self.repo / ".env").exists())

    def test_transaction_recovers_after_ref_and_index_update(self):
        self.start()
        (self.repo / "new.py").write_text("VALUE = 1\n")
        original = history.save

        def fail(path, value):
            if path.name == "001.json":
                raise OSError("기록 쓰기 중 중단")
            original(path, value)

        with patch.object(history, "save", side_effect=fail):
            with self.assertRaises(OSError):
                self.checkpoint()
        sha = self.git("rev-parse", "HEAD")
        self.assertEqual(self.checkpoint()["sha"], sha)
        self.assertFalse((self.d / "checkpoint_pending.json").exists())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_selective_reuse_preserves_provenance_and_resumed_edits(self):
        assets = self.source()
        self.start()
        manifest = history.prepare_assets(self.repo, self.d, assets)
        self.assertEqual((self.repo / "loader.py").read_text(), "VALUE = 42\n")
        self.assertEqual(manifest["state"], "pending_validation")
        (self.repo / "loader.py").write_text("VALUE = 43\n")
        history.prepare_assets(self.repo, self.d, assets)
        self.assertEqual((self.repo / "loader.py").read_text(), "VALUE = 43\n")
        self.checkpoint()
        self.assertEqual(self.git("show", "HEAD:loader.py"), "VALUE = 43")

    def test_identical_preexisting_restored_file_can_be_explicitly_adopted(self):
        assets = self.source()
        (self.repo / "loader.py").write_text("VALUE = 42\n")
        self.start()
        history.prepare_assets(self.repo, self.d, assets)
        result = self.checkpoint()
        self.assertEqual(self.git("show", "HEAD:loader.py"), "VALUE = 42")
        self.assertNotIn("loader.py", result["unpreserved_paths"])

    def test_conflict_missing_source_and_path_escape_block_without_overwrite(self):
        assets = self.source()
        self.start()
        (self.repo / "loader.py").write_text("USER = 1\n")
        with self.assertRaisesRegex(history.HistoryError, "충돌"):
            history.prepare_assets(self.repo, self.d, assets)
        self.assertEqual((self.repo / "loader.py").read_text(), "USER = 1\n")
        for name in ("missing.py", "../escape.py", "results/data.json", ".git/config", "loader.py/child.py"):
            with self.subTest(name=name), self.assertRaises(history.HistoryError):
                history.resolve_assets(self.repo, [{**assets[0], "paths": [name]}])

    def test_missing_prepared_asset_blocks_instead_of_recreating_it(self):
        assets = self.source()
        self.start()
        history.prepare_assets(self.repo, self.d, assets)
        (self.repo / "loader.py").unlink()
        with self.assertRaisesRegex(history.HistoryError, "누락"):
            history.prepare_assets(self.repo, self.d, assets)

    def test_safe_source_deletion_is_checkpointed(self):
        self.start()
        (self.repo / "base.txt").unlink()
        self.checkpoint()
        self.assertEqual(self.git("ls-tree", "--name-only", "HEAD"), "")

    def test_module_approval_is_independent_of_whole_experiment(self):
        self.start()
        (self.repo / "loader.py").write_text("VALUE = 1\n")
        loop.checkpoint_code(1, "finished", final=True)
        review = {"reusable_code": False, "approach_status": "abandon", "code_assets": [
            {"paths": ["loader.py"], "status": "approved", "reason": "입력 로더만 정상",
             "checks": ["test_loader 통과"]}]}
        loop.validate_code_assets(1, review)
        self.record(1, "review.json", review)
        self.assertIn("입력 로더만 정상", loop.code_assets_text())
        self.assertIsNone(loop.reusable_commit(1))
        review["code_assets"][0]["checks"] = []
        with self.assertRaises(loop.AgentError):
            loop.validate_code_assets(1, review)

    def test_checkpoint_does_not_run_while_agent_active(self):
        self.start()
        with patch.dict(loop.STATE, {"proc": object()}), self.assertRaises(loop.AgentError):
            loop.checkpoint_code(1, "unsafe")

    def test_claude_failure_creates_checkpoint_before_propagating(self):
        self.plan(1)
        args = argparse.Namespace(claude_tier="standard")

        def run(*args, **kwargs):
            (self.repo / "partial.py").write_text("PARTIAL = True\n")
            raise loop.SpendLimitError("한도")

        with patch.object(loop, "run_claude", side_effect=run), self.assertRaises(loop.SpendLimitError):
            loop.step_claude(args, "목표", 1)
        self.assertEqual(self.git("show", "HEAD:partial.py"), "PARTIAL = True")
        self.assertFalse((loop.iter_dir(1) / "claude_report.md").exists())
        self.assertEqual(json.loads((loop.iter_dir(1) / "checkpoint.json").read_text())["reason"], "interrupted")

    def test_success_result_recovery_never_reexecutes_claude(self):
        self.plan(1)
        args = argparse.Namespace(claude_tier="standard")

        def run(*args, **kwargs):
            (self.repo / "new.py").write_text("VALUE = 1\n")
            return {"result": "SELF_CHECK: FAIL\nSUMMARY: 검증 미완료", "permission_denials": []}

        with patch.object(loop, "run_claude", side_effect=run) as model:
            with patch.object(loop, "checkpoint_code", side_effect=loop.AgentError("저장 중 중단")):
                with self.assertRaisesRegex(loop.AgentError, "저장 중 중단"):
                    loop.step_claude(args, "목표", 1)
            self.assertTrue((loop.iter_dir(1) / "claude_result.raw.json").exists())
            self.assertFalse((loop.iter_dir(1) / "claude_report.md").exists())
            loop.step_claude(args, "목표", 1)
            self.assertEqual(model.call_count, 1)
        self.assertTrue((loop.iter_dir(1) / "commit.json").exists())
        self.assertIn("new.py", (loop.iter_dir(1) / "changes.patch").read_text())
        self.assertEqual(self.git("show", "HEAD:new.py"), "VALUE = 1")

    def test_invalid_reuse_blocks_before_branch_switch_and_model_call(self):
        self.plan(1, reuse_assets=[{"source_commit": "0" * 40, "paths": ["missing.py"],
                                   "reason": "누락", "required_checks": ["검증"]}])
        before = self.git("rev-parse", "HEAD")
        with patch.object(loop, "run_claude") as model, self.assertRaises(loop.AgentError):
            loop.step_claude(argparse.Namespace(claude_tier="standard"), "목표", 1)
        model.assert_not_called()
        self.assertEqual(self.git("branch", "--show-current"), "base")
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_review_is_bound_to_checkpoint_and_detects_drift(self):
        self.start()
        (self.repo / "new.py").write_text("VALUE = 1\n")
        loop.checkpoint_code(1, "finished", final=True)
        (self.repo / "new.py").write_text("VALUE = 2\n")
        with patch.object(loop, "run_codex") as reviewer, self.assertRaisesRegex(loop.AgentError, "코드가 변경"):
            loop.step_review(argparse.Namespace(), "목표", 1)
        reviewer.assert_not_called()

    def test_new_branch_can_select_only_module_from_failed_checkpoint(self):
        self.start()
        self.git("checkout", "-b", "approach/old")
        # 실행 전 기준은 현재 작업 브랜치에서 잡는다.
        baseline = history.load(self.d / "code_baseline.json")
        baseline["branch"] = "refs/heads/approach/old"
        history.save(self.d / "code_baseline.json", baseline)
        (self.repo / "good.py").write_text("GOOD = True\n")
        (self.repo / "bad.py").write_text("raise RuntimeError()\n")
        entry = loop.checkpoint_code(1, "finished", final=True)
        self.record(1, "review.json", {"approach_status": "abandon", "reusable_code": False})
        assets = [{"source_commit": entry["sha"], "paths": ["good.py"], "reason": "유용한 모듈만 반입",
                   "required_checks": ["모듈 테스트"]}]
        self.plan(2, approach_id="new", reuse_assets=assets)
        loop.ensure_branch(2)
        history.begin(self.repo, loop.iter_dir(2))
        history.prepare_assets(self.repo, loop.iter_dir(2), assets)
        self.assertTrue((self.repo / "good.py").exists())
        self.assertFalse((self.repo / "bad.py").exists())
        self.assertEqual(self.git("show", entry["sha"] + ":bad.py"), "raise RuntimeError()")

    def test_replan_checkpoints_uncaptured_work_before_superseding(self):
        self.start()
        (self.repo / "partial.py").write_text("VALUE = 1\n")
        loop.queue_replan("진행 방향 보완")
        loop.apply_pending_replan()
        self.assertEqual(self.git("show", "HEAD:partial.py"), "VALUE = 1")
        self.assertTrue((self.d / "checkpoint.json").exists())
        self.assertTrue((self.d / "superseded.json").exists())

    def test_external_commit_blocks_resume_before_implementation(self):
        self.start()
        (self.repo / "user.py").write_text("USER = 1\n")
        self.git("add", "user.py")
        self.git("commit", "-m", "외부 사용자 작업")
        with self.assertRaisesRegex(history.HistoryError, "HEAD"):
            history.begin(self.repo, self.d)

    def test_secret_excluded_from_checkpoint_cannot_enter_stash_on_switch(self):
        self.git("checkout", "-b", "approach/old")
        (self.repo / ".env").write_text("SECRET=private\n")
        (self.repo / "good.py").write_text("GOOD = True\n")
        self.plan(2, approach_id="new")
        with self.assertRaisesRegex(loop.AgentError, "자동 보관에서 제외"):
            loop.ensure_branch(2)
        self.assertEqual(self.git("stash", "list"), "")
        self.assertEqual(self.git("branch", "--show-current"), "approach/old")
        self.assertEqual((self.repo / ".env").read_text(), "SECRET=private\n")


if __name__ == "__main__":
    unittest.main()
