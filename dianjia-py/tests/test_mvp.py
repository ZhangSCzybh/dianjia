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

        class FakeOutcome:
            action = "candidate"
            title = "库存状态规则"
            reason = "规则适用范围尚待确认"
            mode = "ai"
            memory_id = None

            @property
            def summary(self):
                return f"{self.action}: {self.title}"

            def to_dict(self):
                return {"action": self.action, "title": self.title, "reason": self.reason, "mode": self.mode, "memory_id": self.memory_id}

        class FakeService:
            def run_daily(self, day):
                return [FakeOutcome()]

            def pipeline_report(self):
                return {"daily": "ai", "extract": "local", "judge": {"ai": 1, "local": 2}}

        with patch.object(Handler, "service", FakeService()):
            _run_daily_job("test-job", "2026-08-31")
        with RUN_JOBS_LOCK:
            job = RUN_JOBS.pop("test-job")
        self.assertEqual(job["pipeline"]["daily"], "ai")
        self.assertEqual(job["pipeline"]["judge"]["local"], 2)
        self.assertEqual(job["outcomes"], ["candidate: 库存状态规则"])
        self.assertEqual(job["decisions"][0]["reason"], "规则适用范围尚待确认")

    def test_web_page_renders_judge_reason_for_each_decision(self):
        page = (Path(__file__).resolve().parents[1] / "web/index.html").read_text(encoding="utf-8")

        self.assertIn("renderDecisions", page)
        self.assertIn("decision.reason", page)

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
            self.assertTrue(outcomes and outcomes[0].summary.startswith("create:"))
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

    def test_category_catalog_includes_defaults_and_existing_memory_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
            service.init()
            (root / "kb/03_Memory/数据治理").mkdir(parents=True)

            catalog = service._category_catalog()

            self.assertTrue({"SQL", "BI", "Testing", "AI", "Projects", "General"}.issubset(catalog))
            self.assertIn("数据治理", catalog)

    def test_category_catalog_includes_active_sqlite_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
            service.conn.execute("INSERT INTO memories(id,title,category,subcategory,tags,summary,path,score,memory_level,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("supply-chain", "供应链规则", "供应链", "", "[]", "", "03_Memory/供应链/rule.md", 15, "long_term", "active", "2026-09-01", "2026-09-01"))
            service.conn.commit()

            self.assertIn("供应链", service._category_catalog())

    def test_candidate_normalization_keeps_safe_new_ai_category(self):
        candidate = MemoryService._normalize_candidate({
            "title": "跨系统字段口径治理规则",
            "category": "数据治理",
            "subcategory": "字段口径",
            "category_action": "new",
            "category_reason": "现有分类无法准确覆盖字段标准定义",
            "category_confidence": 0.88,
            "content": "跨系统字段必须定义统一业务口径、负责人和变更记录。",
            "score": {"reusability": 4, "importance": 4, "uniqueness": 3, "stability": 4, "personal_relevance": 4},
        }, "2026-09-01", ["source-1"], category_catalog=["SQL", "BI", "Testing", "AI", "Projects", "General"])

        self.assertEqual(candidate["category"], "数据治理")
        self.assertEqual(candidate["category_action"], "new")
        self.assertEqual(candidate["category_confidence"], 0.88)

    def test_candidate_normalization_falls_back_when_ai_category_is_unsafe(self):
        candidate = MemoryService._normalize_candidate({
            "title": "普通记录",
            "category": "../06_Archive",
            "category_action": "new",
            "content": "这是一段不包含任何预设分类关键词的普通记录内容。",
        }, "2026-09-01", ["source-1"], category_catalog=["SQL", "BI", "Testing", "AI", "Projects", "General"])

        self.assertEqual(candidate["category"], "General")
        self.assertEqual(candidate["category_action"], "local_fallback")

    def test_create_memory_rejects_unsafe_category_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))

            for category in ("", ".", "../06_Archive", "SQL/危险目录", "SQL\\危险目录", "分类\t名称", "分类\n名称", "分类\x7f名称", "分类\u200b名称", "x" * 41):
                with self.subTest(category=repr(category)), self.assertRaisesRegex(ValueError, "invalid category"):
                    service._create_memory({
                        "title": "不安全分类测试",
                        "category": category,
                        "content": "不能用分类名跳出长期记忆目录。",
                        "source_date": "2026-09-01",
                        "score": {},
                    })

    def test_safe_new_category_is_persisted_and_indexed_when_memory_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
            candidate = MemoryService._normalize_candidate({
                "title": "统一字段口径的治理流程",
                "category": "数据治理",
                "category_action": "new",
                "category_confidence": 0.9,
                "content": "字段口径必须维护负责人、变更记录和跨系统一致性校验。",
                "score": {"reusability": 4, "importance": 4, "uniqueness": 3, "stability": 4, "personal_relevance": 4},
            }, "2026-09-01", ["source-1"], category_catalog=["SQL", "BI", "Testing", "AI", "Projects", "General"])

            memory_id = service._create_memory(candidate)
            service.rebuild_index()

            self.assertTrue((root / "kb/03_Memory/数据治理" / f"{memory_id}.md").exists())
            row = service.conn.execute("SELECT category FROM memories WHERE id = ?", (memory_id,)).fetchone()
            self.assertEqual(row["category"], "数据治理")

    def test_process_accepts_legacy_candidate_without_category_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
            candidate_file = root / "legacy-candidates.json"
            candidate_file.write_text(json.dumps([{
                "title": "旧候选 SQL 规则",
                "category": "SQL",
                "subcategory": "查询与数据",
                "tags": ["SQL", "ClickHouse"],
                "summary": "使用完整日期字段进行 ClickHouse 查询筛选。",
                "content": "ClickHouse 查询必须使用完整日期字段进行筛选。",
                "source_date": "2026-09-01",
                "source_ids": [],
                "score": {"reusability": 3, "importance": 3, "uniqueness": 3, "stability": 3, "personal_relevance": 3},
                "total_score": 15,
            }], ensure_ascii=False), encoding="utf-8")

            outcomes = service.process(candidate_file)

            self.assertEqual([outcome.summary for outcome in outcomes], ["create: 旧候选 SQL 规则"])

    def test_process_outcome_includes_local_judge_reason_and_cli_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
            candidate_file = root / "candidates.json"
            candidate_file.write_text(json.dumps([{
                "title": "可复用库存校验规则",
                "category": "Testing",
                "subcategory": "测试方法",
                "tags": ["库存", "校验"],
                "summary": "库存校验规则。",
                "content": "库存变更后必须校验账面库存与实际库存一致。",
                "source_date": "2026-09-01",
                "source_ids": [],
                "score": {"reusability": 3, "importance": 3, "uniqueness": 3, "stability": 3, "personal_relevance": 3},
                "total_score": 15,
            }], ensure_ascii=False), encoding="utf-8")

            outcome = service.process(candidate_file)[0]

            self.assertEqual(outcome.action, "create")
            self.assertEqual(outcome.mode, "local")
            self.assertEqual(outcome.reason, "未发现相似记忆且候选具有复用价值")
            self.assertIn("本地规则 理由：未发现相似记忆且候选具有复用价值", outcome.cli_text())

    def test_missing_ai_update_target_is_saved_as_pending_with_final_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
            candidate_file = root / "candidates.json"
            candidate_file.write_text(json.dumps([{
                "title": "缺失目标的库存规则",
                "category": "Workflow",
                "subcategory": "状态流转",
                "tags": [],
                "summary": "库存规则。",
                "content": "提交和冲销会改变库存状态。",
                "source_date": "2026-09-01",
                "source_ids": [],
                "score": {"reusability": 3, "importance": 3, "uniqueness": 3, "stability": 3, "personal_relevance": 3},
                "total_score": 15,
            }], ensure_ascii=False), encoding="utf-8")

            class MissingTargetClient:
                enabled = True

                def ask(self, messages):
                    return json.dumps({"action": "update", "target_memory_id": "missing-memory", "reason": "应更新已有记忆", "confidence": 0.9})

            with patch("app.services.AIClient", return_value=MissingTargetClient()):
                outcome = service.process(candidate_file)[0]

            self.assertEqual(outcome.action, "candidate")
            self.assertIsNone(outcome.memory_id)
            self.assertIn("目标记忆不存在", outcome.reason)
            self.assertTrue(list((root / "kb/02_Candidate").glob("pending-2026-09-01-*.json")))

    def test_non_mutating_ai_actions_discard_target_memory_id(self):
        for action in ("candidate", "conflict", "discard"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
                candidate_file = root / "candidates.json"
                candidate_file.write_text(json.dumps([{
                    "title": f"{action} 的库存规则",
                    "category": "Workflow",
                    "subcategory": "状态流转",
                    "tags": [],
                    "summary": "库存规则。",
                    "content": "提交和冲销会改变库存状态。",
                    "source_date": "2026-09-01",
                    "source_ids": [],
                    "score": {"reusability": 3, "importance": 3, "uniqueness": 3, "stability": 3, "personal_relevance": 3},
                    "total_score": 15,
                }], ensure_ascii=False), encoding="utf-8")

                class NonMutatingClient:
                    enabled = True

                    def ask(self, messages):
                        return json.dumps({"action": action, "target_memory_id": "unrelated-memory", "reason": "需要人工处理", "confidence": 0.9})

                with patch("app.services.AIClient", return_value=NonMutatingClient()):
                    outcome = service.process(candidate_file)[0]

                audit = service.conn.execute("SELECT memory_id, payload FROM memory_actions ORDER BY id DESC LIMIT 1").fetchone()
                self.assertIsNone(outcome.memory_id)
                self.assertIsNone(audit["memory_id"])
                self.assertIsNone(json.loads(audit["payload"])["decision"]["target_memory_id"])

    def test_extract_prompt_includes_existing_dynamic_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = MemoryService(Settings(root, root / "kb", root / "data", root / "data/db.sqlite"))
            service.init()
            (root / "kb/03_Memory/数据治理").mkdir(parents=True)
            day = "2026-09-01"
            daily_path = root / "kb/01_Daily/2026/09/2026-09-01.md"
            daily_path.parent.mkdir(parents=True)
            daily_path.write_text(dump_frontmatter({"date": day, "type": "daily"}, "# 每日总结\n\n### 记录 1\n\n字段口径需要统一。"), encoding="utf-8")
            daily_path.with_suffix(".json").write_text(json.dumps({"date": day, "source_ids": []}, ensure_ascii=False), encoding="utf-8")

            class CaptureClient:
                enabled = True

                def __init__(self):
                    self.messages = []

                def ask(self, messages):
                    self.messages = messages
                    return "[]"

            client = CaptureClient()
            with patch("app.services.AIClient", return_value=client):
                service.extract(day)

            self.assertIn("数据治理", client.messages[0]["content"])

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
