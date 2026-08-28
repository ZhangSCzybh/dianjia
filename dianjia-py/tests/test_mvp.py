import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.services import MemoryService
from app.markdown import dump_frontmatter
from app.migration import migrate_legacy_memories


class MvpTest(unittest.TestCase):
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
