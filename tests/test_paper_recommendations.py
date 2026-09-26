"""논문 추천 정책과 목록 저장→Telegram 전달을 외부 통신 없이 검증한다."""

import contextlib
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import orchestrator as loop
from notifier import Human


class PaperRecommendationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.papers = self.root / "PAPERS.md"
        self.runs = self.root / "runs"
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        # 입력 스레드와 실제 Telegram 연결은 시작하지 않는다.
        human = Human.__new__(Human)
        human.telegram = True
        human.chat_id = "test-chat"
        human.warned = False
        self.api = stack.enter_context(patch.object(human, "_api", return_value={"ok": True}))
        for name, value in {"PAPERS_FILE": self.papers, "RUNS_DIR": self.runs,
                            "LOG_FILE": self.root / "log.md", "HUMAN": human}.items():
            stack.enter_context(patch.object(loop, name, value))
        self.opens = stack.enter_context(patch.object(loop, "url_opens", return_value=True))
        self.review = {
            "approach_status": "improve", "valid_experiment": True,
            "paper_recommendation": {
                "recommend": True, "title": "검증용 논문", "authors_year": "Test et al., 2026",
                "url": "https://example.invalid/paper",
                "current_work": "고정 표본 200명에서 대조군 대비 F1 +0.04. 근거: results/metrics.json",
                "why": "오류 감소가 재현돼 후속 검증 가치가 있다. 외부 데이터 일반화는 미검증이다.",
                "what_to_read": "Section 3과 Figure 2: 공간 학습과 비교군 설계 확인",
            },
        }

    def test_recommendation_saved_and_sent_with_evidence_limits_and_reading(self):
        before = copy.deepcopy(self.review)
        loop.handle_paper(14, self.review)
        stored = self.papers.read_text()
        self.api.assert_called_once()
        method, params = self.api.call_args.args
        self.assertEqual(method, "sendMessage")
        self.assertEqual(params["chat_id"], "test-chat")
        for key in ("title", "url", "current_work", "why", "what_to_read"):
            value = self.review["paper_recommendation"][key]
            self.assertIn(value, stored)
            self.assertIn(value, params["text"])
        self.assertIn("agent/PAPERS.md", params["text"])
        event = json.loads((self.runs / "iter_014/events.jsonl").read_text())
        self.assertEqual(event["stage"], "paper")
        self.assertEqual(self.review, before)

    def test_declined_recommendation_does_not_send_or_create_list(self):
        self.review["paper_recommendation"]["recommend"] = False
        loop.handle_paper(14, self.review)
        self.assertFalse(self.papers.exists())
        self.api.assert_not_called()
        self.opens.assert_not_called()

    def test_user_recommendation_is_not_sent_twice(self):
        loop.handle_paper(14, self.review)
        original = self.papers.read_text()
        loop.handle_paper(15, self.review)
        self.api.assert_called_once()
        self.assertEqual(self.papers.read_text(), original)
        rejected = json.loads((self.runs / "iter_015/paper_rejected.json").read_text())
        self.assertEqual(rejected["reason"], "이미 추천한 논문")

    def test_abandoned_direction_not_sent(self):
        self.review["approach_status"] = "abandon"
        loop.handle_paper(14, self.review)
        self.api.assert_not_called()
        self.assertFalse(self.papers.exists())

    def test_unverified_link_not_sent(self):
        self.opens.return_value = False
        loop.handle_paper(14, self.review)
        self.api.assert_not_called()
        self.assertFalse(self.papers.exists())

    def test_prompt_requires_empirical_promise_not_merely_expansion(self):
        prompt = (Path(__file__).resolve().parents[1] / "agent/prompts/gpt_review.md").read_text()
        section = prompt.split("paper_recommendation", 1)[1].split("milestone (", 1)[0]
        self.assertIn("유효한 실험", section)
        self.assertIn("보완 확대는 유망성 확인을 대신하지 않는다", section)
        self.assertIn("불확정 결과만", section)
        self.assertIn("사용자가 추천받은 적이 없다면 후보에 포함", section)
        self.assertNotIn("이미 docs에 인용된 논문은 추천하지 않는다", section)
        self.assertIn("보류 이유를 한 문장", section)

    def test_schema_fields_remain_compatible_with_running_sender(self):
        path = Path(__file__).resolve().parents[1] / "agent/prompts/review_schema.json"
        schema = json.loads(path.read_text())["properties"]["paper_recommendation"]
        self.assertEqual(set(schema["required"]), set(self.review["paper_recommendation"]))
        self.assertEqual(set(schema["properties"]), set(self.review["paper_recommendation"]))


if __name__ == "__main__":
    unittest.main()
