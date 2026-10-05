"""문헌 탐색 흐름/격리/재개 계약. 모델·GPU·Telegram 호출 없음."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from discovery.contracts import AXES, CRITIC, EXPLORE, candidate_valid, nomination_problems, validate
from discovery.core import rebuild, replay_notifications, run_round, validate_exploration
from discovery.runtime import (Channel, Codex, classify_error, command, lock, read_json,
                               save, separate_telegram, CallError)
import discovery_orchestrator as cli


def source(sid="paper", kind="paper"):
    return dict(id=sid, url="https://example.org/" + sid, title="검증용 출처", kind=kind,
                primary=True, access="full_text", publication_date="2026-01-01", checked_at="2026-10-05",
                locator="section 3", claim="검증용 주장", limitations="테스트 데이터이며 실제 연구 근거 아님")


def candidate(cid="medical-example", status="nominate"):
    return dict(id=cid, problem_key=cid, title="테스트 문제", status=status, summary="요약", problem="미해결 질문",
                medical_origin="의료 특성", users_and_workflow="사용 업무", generalization="일반화 조건",
                strongest_objection="이미 해결됐을 가능성", uncertainty="실험 전", reopen_reason="",
                next_questions=["무엇이 남았나"], assessments=[dict(key=k, judgment="plausible", reason="조건부 근거",
                source_ids=["paper", "demand"]) for k in AXES], sources=[source(), source("demand", "deployment")],
                closest_work=[dict(source_id="paper", solves="기존 해결", leaves_open="남은 조건")], report_markdown="# 후보\n테스트")


def exploration(candidates=None):
    return dict(question="이번 질문", why_this_question="가치", search_queries=["실제 검색 문구"], what_changed="새 근거",
                evidence_added=True, next_action="continue", next_question="다른 문제는?", focus_id="",
                selection_reason="판단 이유", candidates=candidates or [], report_markdown="# 조사\n테스트")


def critic(verdict="recommend"):
    return dict(verdict=verdict, reason="근거 검토", next_question="남은 질문", blocking_issues=[],
                criteria=[dict(key=k, passed=True, reason="문헌상 충족") for k in AXES],
                source_checks=[dict(source_id=k, verified=True, supports_claim=True, notes="원문 위치 재확인")
                               for k in ("paper", "demand")], additional_sources=[], report_markdown="# 반론 검토\n테스트")


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_contract_and_path_safety(self):
        validate(exploration([candidate()]), EXPLORE)
        validate(critic(), CRITIC)
        bad = candidate("../../outside")
        with self.assertRaises(ValueError):
            candidate_valid(bad)
        bad = candidate()
        bad["sources"][0]["url"] = "file:///tmp/private"
        with self.assertRaises(ValueError):
            candidate_valid(bad)

    def test_no_implementation_no_inherited_config(self):
        cmd = command("codex", self.root, self.root / "o", self.root / "s")
        for value in ('gpt-6-astra', 'model_reasoning_effort="high"', 'web_search="live"',
                      'read-only', 'features.shell_tool=false', 'features.unified_exec=false',
                      'project_doc_max_bytes=0', '--ignore-user-config', 'forced_login_method="chatgpt"'):
            self.assertIn(value, cmd)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", cmd)

    def test_unknown_and_abstract_only_cannot_nominate(self):
        c = candidate()
        self.assertEqual(nomination_problems(c), [])
        c["sources"][0]["access"] = "abstract"
        self.assertTrue(nomination_problems(c))
        c = candidate()
        c["assessments"][0]["judgment"] = "unknown"
        self.assertTrue(nomination_problems(c))

    def test_duplicate_and_reopening(self):
        old = candidate(status="held")
        state = rebuild(self.root)
        state["candidates"][old["id"]] = old
        with self.assertRaisesRegex(ValueError, "재검토"):
            validate_exploration(exploration([candidate()]), state)
        new = candidate("different-name")
        new["problem_key"] = old["problem_key"]
        with self.assertRaisesRegex(ValueError, "중복"):
            validate_exploration(exploration([new]), state)

    def test_recommend_then_continue_without_experiment(self):
        model = Mock()
        model.call.side_effect = [exploration([candidate()]), critic()]
        channel = Channel(self.root)
        state = run_round(self.root, rebuild(self.root), model, channel)
        self.assertEqual(model.call.call_count, 2)
        self.assertEqual(state["candidates"]["medical-example"]["status"], "recommended")
        self.assertFalse(state["paused"])
        self.assertTrue((self.root / "INDEX.md").exists())
        self.assertIn("문헌상 유망", (self.root / "INDEX.md").read_text())
        count = len(list((self.root / "outbox").glob("*.json")))
        replay_notifications(self.root, channel)
        self.assertEqual(len(list((self.root / "outbox").glob("*.json"))), count)

    def test_bad_nomination_does_not_pay_for_critic(self):
        c = candidate()
        c["sources"][1]["primary"] = False
        model = Mock()
        model.call.return_value = exploration([c])
        state = run_round(self.root, rebuild(self.root), model, Channel(self.root))
        self.assertEqual(model.call.call_count, 1)
        self.assertEqual(state["candidates"][c["id"]]["status"], "investigating")

    def test_critic_failure_blocks_recommendation(self):
        review = critic()
        review["source_checks"][0]["verified"] = False
        model = Mock()
        model.call.side_effect = [exploration([candidate()]), review]
        state = run_round(self.root, rebuild(self.root), model, Channel(self.root))
        self.assertEqual(state["candidates"]["medical-example"]["status"], "held")
        self.assertFalse(list((self.root / "outbox").glob("candidate-*.json")))

    def test_critic_deepen_drives_next_question(self):
        model = Mock()
        model.call.side_effect = [exploration([candidate()]), critic("deepen")]
        state = run_round(self.root, rebuild(self.root), model, Channel(self.root))
        self.assertEqual(state["focus_id"], "medical-example")
        self.assertEqual(state["next_question"], "남은 질문")

    def test_state_replay_and_stall(self):
        model = Mock()
        result = exploration()
        result["evidence_added"] = False
        model.call.return_value = result
        state = rebuild(self.root)
        for _ in range(3):
            state = run_round(self.root, state, model, Channel(self.root))
        self.assertEqual(rebuild(self.root)["stalled"], 3)
        self.assertEqual(rebuild(self.root)["round"], 3)

    def test_cached_call_never_relaunches(self):
        folder = self.root / "call"
        save(folder / "answer.json", exploration())
        model = Codex(self.root)
        with patch.object(model, "_once") as once:
            self.assertEqual(model.call(folder, "new prompt", EXPLORE), exploration())
            once.assert_not_called()

    def test_telegram_never_falls_back_or_reuses_old_bot(self):
        old, new = self.root / "old.env", self.root / "new.env"
        save(old, "TELEGRAM_BOT_TOKEN=old-token\nTELEGRAM_CHAT_ID=1\n")
        self.assertIsNone(separate_telegram(new, old))
        save(new, "TELEGRAM_BOT_TOKEN=old-token\nTELEGRAM_CHAT_ID=2\n")
        with self.assertRaises(ValueError):
            separate_telegram(new, old)
        save(new, "TELEGRAM_BOT_TOKEN=new-token\nTELEGRAM_CHAT_ID=1\n")
        self.assertEqual(separate_telegram(new, old), new)

    def test_outbox_failure_is_retained(self):
        channel = Channel(self.root)
        channel.human = Mock(telegram=True)
        channel.human._api.side_effect = TimeoutError()
        channel.send("event", "hello")
        self.assertFalse(read_json(self.root / "outbox/event.json")["delivered"])
        channel.human._api.side_effect = None
        channel.human._api.return_value = {"ok": True}
        channel.flush()
        self.assertTrue(read_json(self.root / "outbox/event.json")["delivered"])

    def test_single_writer_lock(self):
        with lock(self.root / ".lock"):
            with self.assertRaises(RuntimeError):
                with lock(self.root / ".lock"):
                    pass

    def test_default_status_no_model_and_controls(self):
        with patch.object(cli, "status", return_value="status"), patch.object(cli, "Codex") as model:
            self.assertEqual(cli.main([]), 0)
            model.assert_not_called()
        self.assertEqual(cli.parse_args(["--run"]).max_rounds, 0)
        self.assertIn("마친 뒤", cli.stop(self.root))
        self.assertTrue((self.root / "STOP").exists())

    def test_error_classification_no_paid_fallback(self):
        self.assertEqual(classify_error("usage limit exceeded"), "limit")
        self.assertEqual(classify_error("monthly spend limit"), "blocked")
        self.assertEqual(classify_error("401 unauthorized"), "blocked")
        self.assertEqual(classify_error("ERROR: Reconnecting"), "transient")

    def test_stop_does_not_skip_current_round_critic(self):
        cli.stop(self.root)
        model = Codex(self.root)
        with patch.object(model, "_once", return_value=critic()) as once:
            self.assertEqual(model.call(self.root / "critic", "prompt", CRITIC), critic())
            once.assert_called_once()

    def test_stop_during_limit_does_not_start_retry(self):
        cli.stop(self.root)
        model = Codex(self.root)
        with patch.object(model, "_once", side_effect=CallError("limit", "usage limit")) as once:
            with self.assertRaises(InterruptedError):
                model.call(self.root / "explore", "prompt", EXPLORE)
            once.assert_called_once()

    def test_crash_after_explore_reuses_completed_call(self):
        model = Codex(self.root)
        calls = []

        def fake(attempt, folder, prompt):
            calls.append(folder.name)
            if folder.name == "explore":
                return exploration([candidate()])
            raise CallError("error", "simulated crash")

        with patch.object(model, "_once", side_effect=fake):
            with self.assertRaises(CallError):
                run_round(self.root, rebuild(self.root), model, Channel(self.root))
        self.assertEqual(rebuild(self.root)["round"], 0)
        with patch.object(model, "_once", return_value=critic()) as retry:
            state = run_round(self.root, rebuild(self.root), model, Channel(self.root))
            retry.assert_called_once()
            self.assertEqual(retry.call_args.args[1].name, "critic")
        self.assertEqual(state["round"], 1)

    def test_run_max_rounds_and_stop_boundary(self):
        original_model = Mock()
        original_model.preflight.return_value = "test CLI"
        original_model.call.return_value = exploration()
        with patch.object(cli, "ROOT", self.root), patch.object(cli, "Codex", return_value=original_model):
            self.assertEqual(cli.main(["--run", "--max-rounds", "1", "--no-telegram"]), 0)
        self.assertEqual(rebuild(self.root)["round"], 1)
        self.assertEqual(original_model.call.call_count, 1)

    def test_default_cli_never_reads_experiment_goal(self):
        from discovery.core import base_prompt
        prompt = base_prompt("explore")
        self.assertIn("의료 데이터의 특성", prompt)
        self.assertNotIn("현재 MRI 근거 사용 연구 묶음", prompt)
        self.assertNotIn("iter_080", prompt)


if __name__ == "__main__":
    unittest.main()
