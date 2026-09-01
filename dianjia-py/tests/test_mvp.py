import tempfile
import unittest
import json
import http.client
import os
from unittest.mock import patch
from pathlib import Path

from app.config import Settings
from app.services import MemoryService
from app.markdown import dump_frontmatter, parse_frontmatter
from app.migration import migrate_legacy_memories


class MvpTest(unittest.TestCase):
    def setUp(self):
        self._env_patch = patch.dict(os.environ, {"AI_PROVIDER": "chat_completions", "AI_API_KEY": ""}, clear=False)
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()

    def test_web_ask_flow_shows_loading_feedback_and_prevents_duplicate_submit(self):
        page = (Path(__file__).resolve().parents[1] / "web/index.html").read_text(encoding="utf-8")

        self.assertIn('id="askButton"', page)
        self.assertIn("正在检索历史记忆并组织答案，请稍候…", page)
        self.assertIn("askButton.disabled=true", page)
        self.assertIn("finally { askButton.disabled=false", page)

    def test_ai_connection_drop_is_recoverable(self):
        from app.ai.client import AIClient

        client = AIClient(api_key="test-key", base_url="https://example.test/v1", model="test")
        with patch("urllib.request.urlopen", side_effect=http.client.RemoteDisconnected("closed")):
            with self.assertRaisesRegex(RuntimeError, "AI API 连接中断"):
                client.ask([])

    def test_codex_cli_provider_parses_agent_message_from_jsonl(self):
        from app.ai.client import AIClient

        output = "\n".join([
            json.dumps({"type": "thread.started", "thread_id": "t1"}),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "OK"}}),
            json.dumps({"type": "turn.completed"}),
        ])
        completed = __import__("subprocess").CompletedProcess([], 0, output, "")
        with patch.dict(os.environ, {"AI_PROVIDER": "codex_cli", "AI_CODEX_BIN": "/tmp/codex-test"}, clear=False):
            with patch("app.ai.client.subprocess.run", return_value=completed) as run:
                result = AIClient(model="gpt-5.6-terra").ask([{"role": "user", "content": "Reply OK"}])

        self.assertEqual(result, "OK")
        command = run.call_args.args[0]
        self.assertEqual(command[0], "/tmp/codex-test")
        self.assertIn("--json", command)
        self.assertIn("gpt-5.6-terra", command)

    def test_chat_completions_remains_default_provider(self):
        from app.ai.client import AIClient

        with patch.dict(os.environ, {"AI_PROVIDER": "chat_completions", "AI_API_KEY": "test-key"}, clear=False):
            client = AIClient(base_url="https://example.test/v1")
        self.assertEqual(client.provider, "chat_completions")
        self.assertEqual(client.api_key, "test-key")

    def test_pipeline_report_exposes_stage_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
            report = service.pipeline_report()
            self.assertEqual(report["daily"], "unknown")
            self.assertEqual(report["extract"], "unknown")
            self.assertEqual(report["judge"], {"ai": 0, "local": 0})
            service.conn.close()

    def test_web_run_daily_job_returns_pipeline_report(self):
        from app.web import RUN_JOBS, RUN_JOBS_LOCK, Handler, _run_daily_job

        class FakeService:
            def run_daily(self, day):
                return ["candidate: demo"]

            def pipeline_report(self):
                return {"daily": "ai", "extract": "local", "judge": {"ai": 1, "local": 2}}

        with patch.object(Handler, "service", FakeService()):
            _run_daily_job("test-job", "2026-08-31")
        with RUN_JOBS_LOCK:
            job = RUN_JOBS.pop("test-job")
        self.assertEqual(job["pipeline"]["daily"], "ai")
        self.assertEqual(job["pipeline"]["judge"]["local"], 2)

    def test_ai_prompt_is_bounded(self):
        bounded = MemoryService._truncate_for_ai("x" * 200000)
        self.assertLessEqual(len(bounded), 120100)
        self.assertIn("中间内容因 AI 请求长度限制已省略", bounded)

    def test_ingest_daily_process_and_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.md"
            source.write_text("# SQL 日期查询\n\n使用 toDate 处理日期。\n", encoding="utf-8")
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
            service.ingest(source, "2026-08-27")
            service.daily("2026-08-27")
            candidate = service.extract("2026-08-27")
            outcomes = service.process(candidate)
            self.assertTrue(outcomes and outcomes[0].startswith("create:"))
            self.assertEqual(len(service.search("SQL")), 1)
            class OfflineClient:
                enabled = False

            answer, memories = service.ask("日期查询", limit=3, client=OfflineClient())
            self.assertEqual(len(memories), 1)
            self.assertIn("SQL 日期查询", answer)

    def test_ingest_recovers_orphan_inbox_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
            content = "# 已存在的导入\n\n上次导入时数据库登记失败。\n"
            orphan = root / "kb/00_Inbox/2026-08-28--web-conversation.md"
            orphan.parent.mkdir(parents=True)
            orphan.write_text(content, encoding="utf-8")

            recovered = service.ingest_text(content, "web-conversation", "2026-08-28", "web")

            self.assertEqual(recovered, orphan)
            self.assertEqual(service.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0], 1)
            self.assertEqual(len(list(orphan.parent.glob("*.md"))), 1)

    def test_run_daily_is_idempotent_for_unchanged_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
            source = root / "conversation.md"
            source.write_text("# 库存唯一键处理\n\n使用 SKU 与店铺编码组合键去重。\n", encoding="utf-8")
            service.ingest(source, "2026-08-28")
            service.daily("2026-08-28")
            candidate_file = service.extract("2026-08-28")

            first = service.process(candidate_file, skip_processed_sources=True)
            actions_after_first = service.conn.execute("SELECT COUNT(*) FROM memory_actions").fetchone()[0]
            memories_after_first = service.conn.execute("SELECT COUNT(*) FROM memories WHERE status = 'active'").fetchone()[0]
            second = service.process(candidate_file, skip_processed_sources=True)

            self.assertTrue(first)
            self.assertEqual(second, [])
            self.assertEqual(service.conn.execute("SELECT COUNT(*) FROM memory_actions").fetchone()[0], actions_after_first)
            self.assertEqual(service.conn.execute("SELECT COUNT(*) FROM memories WHERE status = 'active'").fetchone()[0], memories_after_first)

            # Editing the imported Source makes it eligible again.
            source_row = service.conn.execute("SELECT path FROM sources LIMIT 1").fetchone()
            (root / "kb" / source_row["path"]).write_text("# 库存唯一键处理\n\n改为 SKU、店铺编码和日期组合键。\n", encoding="utf-8")
            changed_candidate = {**json.loads(candidate_file.read_text(encoding="utf-8"))[0], "content": "改为 SKU、店铺编码和日期组合键。"}
            candidate_file.write_text(json.dumps([changed_candidate], ensure_ascii=False), encoding="utf-8")
            self.assertTrue(service.process(candidate_file, skip_processed_sources=True))

    def test_fallback_extraction_groups_sections_and_classifies_content(self):
        body = """## 原始记录

### 记录 1

# ClickHouse 同环比查询规则

<details><summary>历史消息</summary>
### 支持
- 年月和年周
</details>
"""
        candidates = MemoryService._fallback_candidates(body, "2026-08-28", ["source-1"])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["category"], "SQL")
        self.assertEqual(candidates[0]["title"], "ClickHouse 同环比查询规则")

    def test_frontmatter_handles_markdown_separators_and_multiline_values(self):
        text = dump_frontmatter({"id": "one", "summary": "第一行\n第二行", "status": "active"}, "正文\n\n---\n\n继续正文")
        meta, body = parse_frontmatter(text)
        self.assertEqual(meta["summary"], "第一行\n第二行")
        self.assertEqual(meta["status"], "active")
        self.assertIn("---", body)

    def test_candidate_normalization_repairs_generic_ai_fields(self):
        candidate = MemoryService._normalize_candidate({
            "title": "支持",
            "category": "General",
            "content": "ClickHouse SQL 查询应使用带年份的 yearWeek，避免同比重复。",
        }, "2026-08-28", ["source-1"])
        self.assertNotEqual(candidate["title"], "支持")
        self.assertEqual(candidate["category"], "SQL")

    def test_candidate_normalization_recomputes_total_score_from_dimensions(self):
        candidate = MemoryService._normalize_candidate({
            "title": "可复用 SQL 规则",
            "category": "SQL",
            "content": "该规则可用于后续 ClickHouse 报表查询。",
            "score": {
                "reusability": 4,
                "importance": 3,
                "uniqueness": 2,
                "stability": 4,
                "personal_relevance": 1,
            },
            "total_score": 1,
        }, "2026-08-31", ["source-1"])
        self.assertEqual(candidate["total_score"], 14)

    def test_low_score_ai_create_is_downgraded_to_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))

            class CreateLowScoreClient:
                enabled = True

                def ask(self, messages):
                    return json.dumps({"action": "create", "reason": "新建", "confidence": 0.9, "total_score": 5})

            candidate = {"title": "一次性查询结果", "category": "BI", "content": "仅记录今天的一次查询。", "total_score": 5, "score": {}}
            with patch("app.services.AIClient", return_value=CreateLowScoreClient()):
                decision = service._judge_candidate(candidate)

            self.assertEqual(decision.action, "candidate")
            self.assertIn("低于长期记忆阈值", decision.reason)

    def test_ai_judge_uses_candidate_total_score_for_create_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))

            class CreateWithoutScoreClient:
                enabled = True

                def ask(self, messages):
                    return json.dumps({"action": "create", "reason": "新建", "confidence": 0.9})

            candidate = {
                "title": "可复用换单规则",
                "category": "BI",
                "content": "该规则可用于后续换单处理。",
                "score": {"reusability": 4, "importance": 4, "uniqueness": 4, "stability": 4, "personal_relevance": 4},
                "total_score": 20,
            }
            with patch("app.services.AIClient", return_value=CreateWithoutScoreClient()):
                decision = service._judge_candidate(candidate)

            self.assertEqual(decision.action, "create")
            self.assertEqual(decision.total_score, 20)

    def test_irrelevant_query_does_not_recall_generic_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
            service.init()
            self.assertEqual(service.retrieve_context("我之前有drp相关的问题吗"), [])

    def test_rag_context_is_capped_at_top_five(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
            service.init()
            for index in range(7):
                rel = Path("03_Memory") / "SQL" / f"sql-{index}.md"
                path = root / "kb" / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(dump_frontmatter({"id": f"sql-{index}", "title": f"SQL 日期查询 {index}", "category": "SQL", "summary": "ClickHouse 日期处理", "status": "active", "created_at": "2026-08-27", "updated_at": "2026-08-27"}, "ClickHouse 日期字段处理 toDate。"), encoding="utf-8")
            service.rebuild_index()
            results = service.retrieve_context("ClickHouse 日期查询", limit=20)
            self.assertEqual(len(results), 5)
            self.assertGreaterEqual(results[0]["score"], results[-1]["score"])

    def test_topic_gate_removes_unrelated_cost_memory(self):
        self.assertFalse(MemoryService._matches_topic("会员相关问题", "商品成本 SKU SPU 成本价"))
        self.assertTrue(MemoryService._matches_topic("会员相关问题", "跨店会员维表 custom_id"))
        # An unseen topic is handled without adding a hard-coded topic list.
        self.assertFalse(MemoryService._matches_topic("DRP 权限问题", "库存同步和成本计算"))
        self.assertTrue(MemoryService._matches_topic("DRP 权限问题", "DRP 权限配置和登录"))

    def test_legacy_migration_adds_frontmatter_and_keeps_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "kb/03_Memory/SQL/legacy.md"
            memory.parent.mkdir(parents=True)
            body = "# 旧知识\n\n## 一句话结论\n\n结论。\n\n## 分类\n\n* 一级分类：SQL\n* 二级分类：排查\n* 标签：SQL、Join\n* memory_id：`legacy-001`\n\n**总分：20**\n"
            memory.write_text(body, encoding="utf-8")
            migrated = migrate_legacy_memories(root / "kb")
            self.assertEqual(migrated, [memory])
            meta, migrated_body = __import__("app.markdown", fromlist=["parse_frontmatter"]).parse_frontmatter(memory.read_text(encoding="utf-8"))
            self.assertEqual(meta["id"], "legacy-001")
            self.assertEqual(meta["tags"], ["SQL", "Join"])
            self.assertEqual(meta["status"], "active")
            self.assertEqual(migrated_body.rstrip(), body.rstrip())
            self.assertTrue(list((root / "kb/06_Archive/migrations").rglob("legacy.md")))


if __name__ == "__main__":
    unittest.main()
