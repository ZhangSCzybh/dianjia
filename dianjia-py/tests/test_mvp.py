import tempfile
import unittest
import json
import http.client
from unittest.mock import patch
from pathlib import Path

from app.config import Settings
from app.services import MemoryService
from app.markdown import dump_frontmatter, parse_frontmatter
from app.migration import migrate_legacy_memories


class MvpTest(unittest.TestCase):
    def test_ai_connection_drop_is_recoverable(self):
        from app.ai.client import AIClient

        client = AIClient(api_key="test-key", base_url="https://example.test/v1", model="test")
        with patch("urllib.request.urlopen", side_effect=http.client.RemoteDisconnected("closed")):
            with self.assertRaisesRegex(RuntimeError, "AI API 连接中断"):
                client.ask([])

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
