import io
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from app.config import Settings
from app.markdown import parse_frontmatter
from app.models import MemoryDecision
from app.services import MemoryService


class StubResponse:
    def __init__(self, payload, status=200):
        self.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload


class SystemOneClientTests(unittest.TestCase):
    def test_blank_optional_configuration_uses_defaults(self):
        from app.ai.typesafe import SystemOneClient

        with patch.dict("os.environ", {"TYPESAFE_BASE_URL": "", "TYPESAFE_MODEL": ""}, clear=False):
            client = SystemOneClient(api_key=" key ")

        self.assertEqual(client.api_key, "key")
        self.assertEqual(client.base_url, "https://api.typesafe.ai/v1")
        self.assertEqual(client.model, "jev-latest")

    def test_evaluate_posts_authenticated_structured_request(self):
        from app.ai.typesafe import SystemOneClient

        captured = {}

        def opener(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return StubResponse({
                "model": "jev-1.13.0",
                "answers": {"urgent": {"type": "noul", "noul": 0.9}},
                "usage": {"input_tokens": 10, "output_tokens": 2},
            })

        client = SystemOneClient(
            api_key="secret-key",
            base_url="https://example.test/v1/",
            model="jev-test",
            opener=opener,
        )
        response = client.evaluate(
            state={"ticket": "urgent"},
            questions={"urgent": {"type": "noul", "instructions": "Is it urgent?"}},
        )

        request = captured["request"]
        body = json.loads(request.data.decode())
        self.assertEqual(request.full_url, "https://example.test/v1/systemone")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-key")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(body["model"], "jev-test")
        self.assertEqual(body["state"], {"ticket": "urgent"})
        self.assertEqual(response["model"], "jev-1.13.0")
        self.assertEqual(captured["timeout"], 30)

    def test_retryable_status_honors_retry_after(self):
        from app.ai.typesafe import SystemOneClient

        attempts = []
        delays = []
        headers = Message()
        headers["Retry-After"] = "2"

        def opener(request, timeout):
            attempts.append(request)
            if len(attempts) == 1:
                raise HTTPError(request.full_url, 429, "rate limited", headers, io.BytesIO(b"slow down"))
            return StubResponse({"model": "jev-1.13.0", "answers": {}, "usage": {}})

        client = SystemOneClient(api_key="key", opener=opener, sleep=delays.append, max_attempts=2)
        client.evaluate(state="state", questions={})

        self.assertEqual(len(attempts), 2)
        self.assertEqual(delays, [2.0])

    def test_validation_error_is_not_retried_or_leaked(self):
        from app.ai.typesafe import SystemOneClient, TypeSafeError

        attempts = []
        headers = Message()

        def opener(request, timeout):
            attempts.append(request)
            raise HTTPError(request.full_url, 422, "invalid", headers, io.BytesIO(b"secret-key and private state"))

        client = SystemOneClient(api_key="secret-key", opener=opener, max_attempts=3)
        with self.assertRaises(TypeSafeError) as raised:
            client.evaluate(state="private state", questions={})

        self.assertEqual(len(attempts), 1)
        self.assertEqual(raised.exception.status, 422)
        self.assertNotIn("secret-key", str(raised.exception))
        self.assertNotIn("private state", str(raised.exception))

    def test_invalid_json_response_is_rejected(self):
        from app.ai.typesafe import SystemOneClient, TypeSafeError

        client = SystemOneClient(api_key="key", opener=lambda request, timeout: StubResponse(b"not-json"))
        with self.assertRaisesRegex(TypeSafeError, "JSON"):
            client.evaluate(state="state", questions={})


class FakeSystemOneClient:
    enabled = True

    def __init__(self, response):
        self.response = response
        self.calls = []

    def evaluate(self, *, state, questions):
        self.calls.append({"state": state, "questions": questions})
        return self.response


class JevMemoryJudgeTests(unittest.TestCase):
    def test_maps_update_choice_to_known_target(self):
        from app.memory_judge import JevMemoryJudge

        client = FakeSystemOneClient({
            "model": "jev-1.13.0",
            "answers": {
                "action": {"type": "choice", "choice": "update", "confidence": 0.84, "probabilities": {"update": 0.9, "create": 0.1}},
                "target": {"type": "choice", "choice": "memory-1", "confidence": 0.91, "probabilities": {"memory-1": 0.96, "none": 0.04}},
                "merge_0": {"type": "noul", "noul": 0.8},
            },
            "usage": {"input_tokens": 100, "output_tokens": 10},
        })
        judge = JevMemoryJudge(client)
        result = judge.decide(
            self.candidate(total_score=18),
            [{"id": "memory-1", "title": "库存校验", "category": "Testing", "content": "旧规则"}],
        )

        self.assertEqual(result.decision.action, "update")
        self.assertEqual(result.decision.target_memory_id, "memory-1")
        self.assertEqual(result.decision.total_score, 18)
        self.assertEqual(result.metadata["provider"], "typesafe")
        self.assertEqual(result.metadata["model"], "jev-1.13.0")
        self.assertEqual(result.metadata["action_probabilities"]["update"], 0.9)
        questions = client.calls[0]["questions"]
        self.assertEqual(questions["action"]["type"], "choice")
        self.assertIn("target", questions)
        self.assertIn("merge_0", questions)

    def test_low_score_create_is_downgraded(self):
        from app.memory_judge import JevMemoryJudge

        client = FakeSystemOneClient({
            "model": "jev-1.13.0",
            "answers": {
                "action": {"type": "choice", "choice": "create", "confidence": 0.9, "probabilities": {"create": 0.9, "candidate": 0.1}},
            },
            "usage": {},
        })
        result = JevMemoryJudge(client).decide(self.candidate(total_score=8), [])

        self.assertEqual(result.decision.action, "candidate")
        self.assertIsNone(result.decision.target_memory_id)
        self.assertIn("低于长期记忆阈值", result.decision.reason)

    def test_merge_without_an_additional_memory_is_downgraded(self):
        from app.memory_judge import JevMemoryJudge

        client = FakeSystemOneClient({
            "model": "jev-1.13.0",
            "answers": {
                "action": {"type": "choice", "choice": "merge", "confidence": 0.8, "probabilities": {"merge": 0.8, "candidate": 0.2}},
                "target": {"type": "choice", "choice": "memory-1", "confidence": 0.8, "probabilities": {"memory-1": 0.8, "none": 0.2}},
                "merge_0": {"type": "noul", "noul": 1.0},
            },
            "usage": {},
        })
        result = JevMemoryJudge(client).decide(
            self.candidate(total_score=18),
            [{"id": "memory-1", "title": "库存校验", "category": "Testing", "content": "旧规则"}],
        )

        self.assertEqual(result.decision.action, "candidate")
        self.assertIn("额外合并对象", result.decision.reason)

    def test_merge_maps_confirmed_additional_memories(self):
        from app.memory_judge import JevMemoryJudge

        client = FakeSystemOneClient({
            "model": "jev-1.13.0",
            "answers": {
                "action": {"type": "choice", "choice": "merge", "confidence": 0.86, "probabilities": {"merge": 0.86, "candidate": 0.14}},
                "target": {"type": "choice", "choice": "memory-1", "confidence": 0.9, "probabilities": {"memory-1": 0.9, "memory-2": 0.08, "none": 0.02}},
                "merge_0": {"type": "noul", "noul": 1.0},
                "merge_1": {"type": "noul", "noul": 0.88},
            },
            "usage": {},
        })
        existing = [
            {"id": "memory-1", "title": "库存校验", "category": "Testing", "content": "主规则"},
            {"id": "memory-2", "title": "库存核对", "category": "Testing", "content": "重复规则"},
        ]
        result = JevMemoryJudge(client).decide(self.candidate(total_score=18), existing)

        self.assertEqual(result.decision.action, "merge")
        self.assertEqual(result.decision.target_memory_id, "memory-1")
        self.assertEqual(result.decision.merge_memory_ids, ["memory-1", "memory-2"])

    @staticmethod
    def candidate(total_score=18):
        return {
            "title": "库存变更校验规则",
            "category": "Testing",
            "summary": "库存变化后需要核对账实一致。",
            "content": "库存发生变化后必须校验账面库存与实际库存一致。",
            "score": {"reusability": 4, "importance": 4, "uniqueness": 3, "stability": 4, "personal_relevance": 3},
            "total_score": total_score,
        }


class MemoryServiceTypeSafeTests(unittest.TestCase):
    def make_service(self, root):
        service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
        self.addCleanup(service.conn.close)
        return service

    def test_default_selector_does_not_construct_typesafe_judge(self):
        class DisabledAI:
            enabled = False

        with tempfile.TemporaryDirectory() as tmp:
            service = self.make_service(Path(tmp))
            candidate = JevMemoryJudgeTests.candidate()
            with patch.dict("os.environ", {"DIANJIA_MEMORY_JUDGE": "llm"}, clear=False), patch("app.services.JevMemoryJudge") as jev, patch("app.services.AIClient", return_value=DisabledAI()):
                service._judge_candidate(candidate)

            jev.assert_not_called()
            self.assertEqual(service._last_judge_mode, "local")

    def test_typesafe_mode_records_metadata(self):
        from app.memory_judge import MemoryJudgeResult

        class Judge:
            def decide(self, candidate, existing):
                return MemoryJudgeResult(
                    MemoryDecision("create", "Jev selected create", None, 0.9, candidate["total_score"]),
                    {"provider": "typesafe", "model": "jev-1.13.0", "action_probabilities": {"create": 0.9}},
                )

        with tempfile.TemporaryDirectory() as tmp:
            service = self.make_service(Path(tmp))
            candidate = JevMemoryJudgeTests.candidate()
            with patch.dict("os.environ", {"DIANJIA_MEMORY_JUDGE": "typesafe"}, clear=False), patch("app.services.JevMemoryJudge", return_value=Judge()):
                decision = service._judge_candidate(candidate)

            self.assertEqual(decision.action, "create")
            self.assertEqual(service._last_judge_mode, "typesafe")
            self.assertEqual(service._last_judge_metadata["model"], "jev-1.13.0")

    def test_process_audits_typesafe_metadata_and_counts_mode(self):
        from app.memory_judge import MemoryJudgeResult

        class Judge:
            def decide(self, candidate, existing):
                return MemoryJudgeResult(
                    MemoryDecision("create", "Jev selected create", None, 0.9, candidate["total_score"]),
                    {"provider": "typesafe", "model": "jev-1.13.0", "action_probabilities": {"create": 0.9}},
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self.make_service(root)
            candidate = {**JevMemoryJudgeTests.candidate(), "source_date": "2026-09-22", "source_ids": []}
            candidate_file = root / "candidate.json"
            candidate_file.write_text(json.dumps([candidate], ensure_ascii=False), encoding="utf-8")
            with patch.dict("os.environ", {"DIANJIA_MEMORY_JUDGE": "typesafe"}, clear=False), patch("app.services.JevMemoryJudge", return_value=Judge()):
                outcomes = service.process(candidate_file)

            audit = service.conn.execute("SELECT payload FROM memory_actions ORDER BY id DESC LIMIT 1").fetchone()
            payload = json.loads(audit["payload"])
            self.assertEqual(outcomes[0].mode, "typesafe")
            self.assertIn("Jev Judge", outcomes[0].cli_text())
            self.assertEqual(payload["judge"]["model"], "jev-1.13.0")
            self.assertEqual(service.pipeline_report()["judge"], {"typesafe": 1, "ai": 0, "local": 0})

    def test_merge_keeps_secondary_markdown_but_archives_its_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self.make_service(root)
            base = {**JevMemoryJudgeTests.candidate(), "source_date": "2026-09-22", "source_ids": []}
            primary_id = service._create_memory({**base, "title": "库存校验主规则"})
            secondary_id = service._create_memory({**base, "title": "库存核对重复规则"})
            secondary_path = root / "kb" / service.conn.execute("SELECT path FROM memories WHERE id = ?", (secondary_id,)).fetchone()["path"]
            decision = MemoryDecision("merge", "merge", primary_id, 0.9, 18, {}, [primary_id, secondary_id])

            service._update_memory(primary_id, base, decision, merge=True)
            service.rebuild_index()

            row = service.conn.execute("SELECT status FROM memories WHERE id = ?", (secondary_id,)).fetchone()
            metadata, _ = parse_frontmatter(secondary_path.read_text(encoding="utf-8"))
            self.assertTrue(secondary_path.exists())
            self.assertEqual(row["status"], "archived")
            self.assertEqual(metadata["status"], "archived")

    def test_typesafe_failure_falls_back_to_existing_ai_judge(self):
        class FailingJudge:
            def decide(self, candidate, existing):
                raise RuntimeError("temporary TypeSafe failure")

        class ExistingAI:
            enabled = True

            def ask(self, messages):
                return json.dumps({"action": "create", "reason": "existing AI", "confidence": 0.8})

        with tempfile.TemporaryDirectory() as tmp:
            service = self.make_service(Path(tmp))
            candidate = JevMemoryJudgeTests.candidate()
            with patch.dict("os.environ", {"DIANJIA_MEMORY_JUDGE": "typesafe"}, clear=False), patch("app.services.JevMemoryJudge", return_value=FailingJudge()), patch("app.services.AIClient", return_value=ExistingAI()):
                decision = service._judge_candidate(candidate)

            self.assertEqual(decision.action, "create")
            self.assertEqual(service._last_judge_mode, "ai")

    def test_typesafe_and_ai_failure_falls_back_to_local_rules(self):
        class FailingJudge:
            def decide(self, candidate, existing):
                raise RuntimeError("temporary TypeSafe failure")

        class DisabledAI:
            enabled = False

        with tempfile.TemporaryDirectory() as tmp:
            service = self.make_service(Path(tmp))
            candidate = JevMemoryJudgeTests.candidate()
            with patch.dict("os.environ", {"DIANJIA_MEMORY_JUDGE": "typesafe"}, clear=False), patch("app.services.JevMemoryJudge", return_value=FailingJudge()), patch("app.services.AIClient", return_value=DisabledAI()):
                decision = service._judge_candidate(candidate)

            self.assertEqual(decision.action, "create")
            self.assertEqual(service._last_judge_mode, "local")


if __name__ == "__main__":
    unittest.main()
