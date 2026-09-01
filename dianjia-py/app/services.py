from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import Settings
from .database import connect
from .markdown import dump_frontmatter, parse_frontmatter, slugify
from .ai.client import AIClient
from .models import MemoryDecision, Source


class MemoryService:
    def __init__(self, settings: Settings):
        self.s = settings
        self.s.knowledge_root.mkdir(parents=True, exist_ok=True)
        self.conn = connect(self.s.db_path)
        self._last_judge_mode = "local"
        self._last_daily_mode = "unknown"
        self._last_extract_mode = "unknown"
        self._last_judge_counts = {"ai": 0, "local": 0}

    def init(self) -> None:
        for directory in ("00_Inbox", "01_Daily", "02_Candidate", "03_Memory", "04_Weekly", "05_Monthly", "06_Archive"):
            (self.s.knowledge_root / directory).mkdir(parents=True, exist_ok=True)
        index = self.s.knowledge_root / "INDEX.md"
        if not index.exists():
            index.write_text("# Dianjia Knowledge Index\n\n## Memory\n\n", encoding="utf-8")

    def ingest(self, source: Path, source_date: str | None = None) -> Path:
        self.init()
        content = source.read_text(encoding="utf-8")
        return self.ingest_text(content, source.stem, source_date, "file", str(source))

    def ingest_text(self, content: str, name: str = "conversation", source_date: str | None = None, source_type: str = "text", origin_path: str | None = None) -> Path:
        """Normalize any input adapter into a Source, then persist it."""
        self.init()
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
        source = Source.create(normalized, name.strip() or "conversation", source_type, source_date, origin_path)
        existing = self.conn.execute("SELECT path FROM sources WHERE content_hash = ?", (source.content_hash,)).fetchone()
        if existing:
            return self.s.knowledge_root / existing["path"]
        day = source.source_date
        target = self.s.knowledge_root / "00_Inbox" / f"{day}--{slugify(source.title)}.md"
        if target.exists():
            # A previous import may have written the file before its SQLite
            # transaction failed. Reuse that orphan instead of duplicating it.
            try:
                if target.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").strip() + "\n" == normalized:
                    pass
                else:
                    target = target.with_name(f"{day}--{slugify(source.title)}-{source.content_hash[:8]}.md")
            except OSError:
                target = target.with_name(f"{day}--{slugify(source.title)}-{source.content_hash[:8]}.md")
        created_file = not target.exists()
        if created_file:
            target.write_text(source.content, encoding="utf-8")
        rel = target.relative_to(self.s.knowledge_root).as_posix()
        try:
            self.conn.execute("INSERT INTO sources(id, source_type, content_hash, path, source_date, created_at, title, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (source.source_id, source.source_type, source.content_hash, rel, source.source_date, source.created_at, source.title, json.dumps(source.metadata, ensure_ascii=False)))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            if created_file:
                target.unlink(missing_ok=True)
            raise
        return target

    def ingest_directory(self, directory: Path, source_date: str | None = None) -> list[Path]:
        """Import all Markdown/TXT files, using YYYY-MM-DD found in each filename."""
        paths = []
        for source in sorted(directory.rglob("*")):
            if source.is_file() and source.suffix.lower() in {".md", ".markdown", ".txt"}:
                match = re.search(r"(20\d{2}-\d{2}-\d{2})", source.name)
                paths.append(self.ingest(source, source_date or (match.group(1) if match else None)))
        return paths

    def run_daily(self, day: str | None = None) -> list[str]:
        """Run the complete offline daily pipeline in one command."""
        self.daily(day)
        candidate = self.extract(day)
        # Re-running the same day is safe: only new or changed Sources enter
        # the memory pipeline.  The daily report/candidate file may still be
        # regenerated, but existing long-term memories are not touched again.
        return self.process(candidate, skip_processed_sources=True)

    def daily(self, day: str | None = None) -> Path:
        self.init()
        day = day or date.today().isoformat()
        rows = self.conn.execute("SELECT id, path FROM sources WHERE source_date = ? ORDER BY path", (day,)).fetchall()
        entries = []
        source_ids = []
        for row in rows:
            path = self.s.knowledge_root / row["path"]
            if path.exists():
                entries.append(path.read_text(encoding="utf-8").strip())
                source_ids.append(row["id"])
        summary = self._daily_summary(day, entries, source_ids)
        body = self._render_daily(summary, entries)
        target = self.s.knowledge_root / "01_Daily" / day[:4] / day[5:7] / f"{day}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dump_frontmatter({"date": day, "type": "daily"}, "\n".join(body)), encoding="utf-8")
        target.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def _daily_summary(self, day: str, entries: list[str], source_ids: list[str]) -> dict[str, Any]:
        fallback = {"date": day, "source_ids": source_ids, "completed": [re.sub(r"^#\s*", "", item.splitlines()[0])[:200] for item in entries if item], "problems": [], "knowledge": [], "projects": [], "tomorrow": ["根据今日记录补充后续行动"]}
        ai = AIClient()
        if not ai.enabled or not entries:
            self._last_daily_mode = "local"
            print("[daily] 使用本地兜底（未配置 AI_API_KEY 或没有记录）", file=sys.stderr)
            return fallback
        try:
            per_record = max(1000, 120000 // max(1, len(entries)))
            records = [self._truncate_for_ai(item, per_record) for item in entries]
            result = self._json_response(ai.ask([{"role": "system", "content": "你是每日总结助手。只输出合法 JSON，字段必须为 date、source_ids、completed、problems、knowledge、projects、tomorrow，所有列表元素使用字符串。"}, {"role": "user", "content": json.dumps({"date": day, "source_ids": source_ids, "records": records}, ensure_ascii=False)}]))
            result["date"], result["source_ids"] = day, source_ids
            self._last_daily_mode = "ai"
            print("[daily] 使用 AI 总结", file=sys.stderr)
            return {key: result.get(key, []) if key not in ("date", "source_ids") else result[key] for key in fallback}
        except (RuntimeError, ValueError, TypeError) as exc:
            self._last_daily_mode = "local"
            print(f"[daily] AI 失败，使用本地兜底：{exc}", file=sys.stderr)
            return fallback

    @staticmethod
    def _render_daily(summary: dict[str, Any], entries: list[str]) -> list[str]:
        body = [f"# {summary['date']} 每日工作总结", "", "## 今日完成事项", ""]
        body.extend(f"{i}. {value}" for i, value in enumerate(summary.get("completed", []), 1)) or body.append("- 暂无导入内容")
        for title, key in (("关键问题与解决方案", "problems"), ("知识沉淀", "knowledge"), ("项目进展", "projects"), ("明天继续关注事项", "tomorrow")):
            body += ["", f"## {title}", ""]
            values = summary.get(key, []) or ["暂无记录"]
            body.extend(f"- {value}" for value in values)
        body += ["", "## 原始记录", ""]
        body.extend(f"### 记录 {i}\n\n{item}" for i, item in enumerate(entries, 1))
        return body

    @staticmethod
    def _truncate_for_ai(text: str, max_chars: int = 120000) -> str:
        """Bound gateway prompts while retaining both the beginning and end."""
        text = str(text or "")
        if len(text) <= max_chars:
            return text
        head = max_chars * 2 // 3
        tail = max_chars - head
        return text[:head] + "\n\n[中间内容因 AI 请求长度限制已省略]\n\n" + text[-tail:]

    def extract(self, day: str | None = None) -> Path:
        day = day or date.today().isoformat()
        daily_path = self.s.knowledge_root / "01_Daily" / day[:4] / day[5:7] / f"{day}.md"
        if not daily_path.exists():
            self.daily(day)
        json_path = daily_path.with_suffix(".json")
        summary = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {}
        _, body = parse_frontmatter(daily_path.read_text(encoding="utf-8"))
        candidates: list[dict[str, Any]] = []
        ai = AIClient()
        ai_extracted = False
        if ai.enabled:
            try:
                prompt_body = self._truncate_for_ai(body)
                payload = self._json_response(ai.ask([{"role": "system", "content": "你是长期记忆提取器。只输出 JSON 数组。按每个独立、可复用的主题合并内容，不要把日报小标题（如支持、推荐组合、项目进展）单独当作记忆；每项必须包含 title、category、subcategory、tags、summary、content、source_date、source_ids、score、total_score。title 要具体描述问题或规则（10-40 字），category 优先使用 SQL、BI、Testing、AI、Projects，无法判断才用 General。只提取稳定且可复用的知识。score 必须是五项 0-5 的整数：reusability 表示未来重复使用价值，importance 表示对业务或项目的影响，uniqueness 表示现有记忆中不重复的程度，stability 表示长期有效性，personal_relevance 表示对用户工作的重要性。临时查询结果、单次执行行数和当天状态通常 stability 不超过 1；可验证的通用规则、字段口径和工具操作规范通常 reusability/importance/stability 至少为 3。total_score 必须严格等于五项 score 之和（0-25），不要自行填写不一致的总分。"}, {"role": "user", "content": json.dumps({"date": day, "summary": summary, "markdown": prompt_body}, ensure_ascii=False)}]))
                candidates = [self._normalize_candidate(item, day, summary.get("source_ids", [])) for item in payload]
                ai_extracted = True
                self._last_extract_mode = "ai"
                print("[extract] 使用 AI 提取候选", file=sys.stderr)
            except (RuntimeError, ValueError, TypeError) as exc:
                self._last_extract_mode = "local"
                print(f"[extract] AI 失败，使用本地兜底：{exc}", file=sys.stderr)
                candidates = []
        else:
            self._last_extract_mode = "local"
            print("[extract] 使用本地兜底（未配置 AI_API_KEY）", file=sys.stderr)
        if ai_extracted:
            return self._write_candidates(day, candidates)
        candidates = self._fallback_candidates(body, day, summary.get("source_ids", []))
        return self._write_candidates(day, candidates)

    @classmethod
    def _fallback_candidates(cls, body: str, day: str, source_ids: list[str]) -> list[dict[str, Any]]:
        """Extract one coherent candidate per source when AI extraction is unavailable."""
        records = re.findall(r"^###\s+记录\s+\d+\s*$([\s\S]*?)(?=^###\s+记录\s+\d+\s*$|\Z)", body, re.M)
        if not records:
            records = [body]
        candidates = []
        for raw in records:
            content = cls._clean_transcript(raw)
            if len(content.strip()) < 20:
                continue
            title = cls._fallback_title(content)
            category, subcategory, tags = cls._classify_content(content)
            candidate = {"title": title, "category": category, "subcategory": subcategory, "tags": tags, "summary": cls._fallback_summary(content), "content": content[:16000], "score": {"reusability": 3, "importance": 3, "uniqueness": 3, "stability": 3, "personal_relevance": 3}}
            candidates.append(cls._normalize_candidate(candidate, day, source_ids))
        return candidates

    @staticmethod
    def _clean_transcript(text: str) -> str:
        text = re.sub(r"</?(?:details|summary)(?:\s[^>]*)?>", "", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
        text = re.sub(r"^\s*Ran \d+ commands?\s*$", "", text, flags=re.M | re.I)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _fallback_title(content: str) -> str:
        generic = {"支持", "不支持或存在风险", "推荐组合", "解决方案", "知识沉淀", "项目进展"}
        headings = [re.sub(r"^#+\s*", "", line).strip() for line in content.splitlines() if re.match(r"^#{1,3}\s+", line)]
        title = next((item for item in headings if item and item not in generic and not re.match(r"^\d+[.、]\s*", item)), "")
        if not title:
            first = next((line.strip(" -*") for line in content.splitlines() if line.strip()), "历史对话知识")
            title = first[:80]
        if "clickhouse" in content.lower() and "技能" in title:
            return "ClickHouse 查询技能与只读查询规范"
        return title[:100]

    @staticmethod
    def _fallback_summary(content: str) -> str:
        paragraphs = [re.sub(r"^#+\s*", "", p).strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
        summary = next((p for p in paragraphs if not p.startswith(("[$", "Ran "))), paragraphs[0] if paragraphs else "")
        return re.sub(r"\s+", " ", summary)[:240]

    @staticmethod
    def _classify_content(content: str) -> tuple[str, str, list[str]]:
        rules = {
            "SQL": ("查询与数据", ["clickhouse", "sql", "select", "join", "数据库", "数据表", "字段", "唯一键", "去重键"]),
            "BI": ("指标计算", ["报表", "指标", "同比", "环比", "维度", "粒度", "看板", "销售", "利润"]),
            "Testing": ("测试方法", ["测试", "校验", "对账", "验证", "断言", "用例"]),
            "AI": ("AI应用", ["ai", "skill", "知识库", "rag", "模型", "提示词"]),
            "Projects": ("项目", ["项目", "需求", "功能", "接口", "上线", "开发"]),
        }
        lowered = content.lower()
        scored = [(sum(lowered.count(term.lower()) for term in terms), category, subcategory, terms) for category, (subcategory, terms) in rules.items()]
        score, category, subcategory, terms = max(scored, key=lambda item: (item[0], -list(rules).index(item[1])))
        if score == 0:
            return "General", "", []
        tags = [term for term in terms if term.lower() in lowered][:8]
        return category, subcategory, tags

    def _write_candidates(self, day: str, candidates: list[dict[str, Any]]) -> Path:
        target = self.s.knowledge_root / "02_Candidate" / f"{day}-candidates.json"
        target.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    @staticmethod
    def _json_response(text: str) -> Any:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)
        return json.loads(cleaned)

    @staticmethod
    def _normalize_candidate(item: dict[str, Any], day: str, source_ids: list[str]) -> dict[str, Any]:
        if not isinstance(item, dict) or not str(item.get("title", "")).strip() or not str(item.get("content", "")).strip():
            raise ValueError("candidate title/content is required")
        content = str(item["content"]).strip()
        title = str(item["title"]).strip()
        if title in {"支持", "不支持或存在风险", "推荐组合", "解决方案", "知识沉淀", "项目进展"} or len(title) < 4:
            title = MemoryService._fallback_title(content)
        category = str(item.get("category") or "General")
        if category not in {"SQL", "BI", "Testing", "AI", "Projects", "General"}:
            category = "General"
        subcategory = item.get("subcategory")
        if category == "General":
            inferred, inferred_subcategory, inferred_tags = MemoryService._classify_content(content)
            if inferred != "General":
                category, subcategory = inferred, subcategory or inferred_subcategory
                if not item.get("tags"):
                    item = {**item, "tags": inferred_tags}
        score = item.get("score") if isinstance(item.get("score"), dict) else {}
        score = {key: max(0, min(5, int(score.get(key, 0)))) for key in ("reusability", "importance", "uniqueness", "stability", "personal_relevance")}
        # Treat the five dimensions as the source of truth.  AI occasionally
        # returns a stale or invented total_score (for example, five zeros and
        # total_score=1); recomputing prevents inconsistent routing decisions.
        total_score = sum(score.values())
        return {"title": title, "category": category, "subcategory": subcategory, "tags": [str(x) for x in (item.get("tags") or [])], "summary": str(item.get("summary") or content[:240]), "content": content, "source_date": day, "source_ids": [str(x) for x in (item.get("source_ids") or source_ids)], "score": score, "total_score": total_score}

    def search(self, keyword: str, limit: int = 10):
        """Search active memory metadata and Markdown bodies.

        Full metric-index memories keep technical codes and explanations in the
        body, so metadata-only SQL search would make those rows undiscoverable.
        """
        needle = str(keyword or "").strip().lower()
        if not needle:
            return []
        rows = self.conn.execute("SELECT * FROM memories WHERE status = 'active' ORDER BY updated_at DESC, title").fetchall()
        matches = []
        for row in rows:
            path = self.s.knowledge_root / row["path"]
            body = path.read_text(encoding="utf-8", errors="replace").lower() if path.exists() else ""
            fields = " ".join(str(row[key] or "") for key in ("title", "tags", "category", "summary"))
            if needle in fields.lower() or needle in body:
                matches.append(row)
                if len(matches) >= max(1, int(limit)):
                    break
        return matches

    def retrieve_context(self, query: str, limit: int = 5, max_chars: int = 12000) -> list[dict[str, Any]]:
        """Retrieve at most five ranked memory excerpts for a RAG prompt.

        The local hashed-vector embedding keeps the MVP dependency-free. A cosine
        score ranks semantic/phrase overlap, while metadata matches provide a small
        boost for exact titles, tags, and categories.
        """
        limit = max(1, min(int(limit), 5))
        terms = self._query_terms(query)
        query_vector = self._embedding(query)
        rows = self.conn.execute("SELECT * FROM memories WHERE status = 'active'").fetchall()
        ranked: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            path = self.s.knowledge_root / row["path"]
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            fields = {
                "title": str(row["title"] or ""),
                "category": str(row["category"] or ""),
                "tags": str(row["tags"] or ""),
                "summary": str(row["summary"] or ""),
            }
            searchable = " ".join([fields["title"], fields["category"], fields["tags"], fields["summary"], body])
            ascii_terms = [term for term in terms if re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", term)]
            searchable_lower = searchable.lower()
            # Hash vectors can collide. Keep exact identifier terms (DRP, SQL,
            # model names, table names) as a hard filter to prevent false hits.
            if ascii_terms and not all(term in searchable_lower for term in ascii_terms):
                continue
            if not self._matches_topic(query, searchable_lower):
                continue
            embedding_score = self._cosine(query_vector, self._embedding(searchable))
            lexical_score = 0.0
            for term in terms:
                if term in fields["title"]:
                    lexical_score += 10
                if term in fields["tags"]:
                    lexical_score += 5
                if term in fields["category"] or term in fields["summary"]:
                    lexical_score += 3
                lexical_score += min(4, body.lower().count(term.lower()))
            score = embedding_score * 100 + lexical_score
            # Require either a meaningful vector match or a strong metadata match;
            # incidental one-word body hits should not enter the RAG context.
            if embedding_score >= 0.08 or lexical_score >= 5:
                ranked.append((score, {"id": row["id"], "title": row["title"], "category": row["category"], "path": row["path"], "score": round(score, 2), "embedding_score": round(embedding_score, 4), "content": body.strip(), "metadata": meta}))
        ranked.sort(key=lambda item: (-item[0], item[1]["title"]))
        results, used = [], 0
        for _, item in ranked[:limit]:
            remaining = max_chars - used
            if remaining <= 0:
                break
            item["content"] = item["content"][:remaining]
            used += len(item["content"])
            results.append(item)
        return results

    @staticmethod
    def _embedding(text: str, dimensions: int = 384) -> list[float]:
        """Create a deterministic hashed n-gram vector for local embedding search."""
        vector = [0.0] * dimensions
        lowered = text.lower()
        features = re.findall(r"[a-z0-9][a-z0-9_.-]*|[\u4e00-\u9fff]", lowered)
        features.extend(lowered[i:i + 2] for i in range(len(lowered) - 1) if "\u4e00" <= lowered[i] <= "\u9fff" and "\u4e00" <= lowered[i + 1] <= "\u9fff")
        for feature in features:
            index = int(hashlib.sha256(feature.encode("utf-8")).hexdigest()[:8], 16) % dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right))

    @staticmethod
    def _matches_topic(query: str, searchable: str) -> bool:
        """Apply query-derived topic anchors before approximate ranking.

        Anchors are inferred from the query itself, so new business topics do not
        require a code change. CJK bigrams handle unspaced Chinese terms; ASCII
        identifiers remain exact filters.
        """
        query_lower = query.lower()
        searchable = searchable.lower()
        ascii_terms = [term for term in re.findall(r"[a-z0-9][a-z0-9_.-]*", query_lower) if len(term) > 1]
        if ascii_terms and not all(term in searchable for term in ascii_terms):
            return False
        stop_chars = set("我有吗呢的问题相关之前如何怎么处理一下请问和与或这是那什么哪些告诉总结过")
        cjk_sequences = re.findall(r"[\u4e00-\u9fff]+", query_lower)
        anchors: list[str] = []
        for sequence in cjk_sequences:
            if len(sequence) == 1:
                continue
            anchors.extend(sequence[i:i + 2] for i in range(len(sequence) - 1))
        anchors = [anchor for anchor in dict.fromkeys(anchors) if not any(char in stop_chars for char in anchor)]
        # At least one distinctive Chinese phrase must be present. This removes
        # unrelated documents while still allowing synonym-rich related notes.
        return not anchors or any(anchor in searchable for anchor in anchors)

    @staticmethod
    def _query_terms(query: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", query.strip().lower())
        stopwords = {"我", "之前", "有", "吗", "呢", "的", "了", "是", "如何", "怎么", "处理", "相关", "问题", "有没有", "哪些", "一下", "请问", "和", "与", "或", "吗"}
        terms = [part for part in re.findall(r"[a-z0-9][a-z0-9_.-]*|[\u4e00-\u9fff]+", normalized) if part not in stopwords and len(part) > 1]
        # Chinese questions often have no spaces; use meaningful character bigrams,
        # excluding generic question words that otherwise match every note.
        generic_chars = set("我有吗呢的问题相关之前如何怎么处理一下请问和与或")
        for sequence in re.findall(r"[\u4e00-\u9fff]+", normalized):
            if len(sequence) > 2:
                terms.extend(pair for pair in (sequence[i:i + 2] for i in range(len(sequence) - 1)) if pair not in stopwords and not any(char in generic_chars for char in pair))
        return list(dict.fromkeys(terms)) or [normalized]

    def build_context(self, query: str, limit: int = 5, max_chars: int = 12000) -> tuple[str, list[dict[str, Any]]]:
        memories = self.retrieve_context(query, min(limit, 5), max_chars)
        if not memories:
            return "（知识库中没有检索到相关记忆）", []
        sections = []
        for i, memory in enumerate(memories, 1):
            sections.append(f"【历史记忆 {i}】\n标题：{memory['title']}\n分类：{memory['category']}\n相关性：{memory['score']}\n来源：{memory['path']}\n\n{memory['content']}")
        return "\n\n---\n\n".join(sections), memories

    def ask(self, query: str, limit: int = 5, client: AIClient | None = None) -> tuple[str, list[dict[str, Any]]]:
        context, memories = self.build_context(query, limit)
        ai = client or AIClient()
        if not ai.enabled:
            print("[ask] 使用本地检索（未配置 AI_API_KEY）", file=sys.stderr)
            return f"未配置 AI_API_KEY，以下是检索到的知识库上下文：\n\n{context}", memories
        try:
            answer = ai.ask([{"role": "system", "content": "你是个人知识助手。优先依据历史记忆回答；历史内容不足时明确说明。不要把推测写成历史事实。"}, {"role": "user", "content": f"历史知识：\n{context}\n\n用户问题：{query}"}])
            print("[ask] 使用 AI 回答", file=sys.stderr)
        except RuntimeError as exc:
            print(f"[ask] AI 失败，返回本地检索上下文：{exc}", file=sys.stderr)
            answer = f"AI 调用失败（{exc}）。以下是已检索到的知识库上下文：\n\n{context}"
        return answer, memories

    def show(self, memory_id: str) -> str:
        row = self.conn.execute("SELECT path FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if not row:
            raise KeyError(f"memory not found: {memory_id}")
        path = self.s.knowledge_root / row["path"]
        if not path.exists():
            raise FileNotFoundError(path)
        return path.read_text(encoding="utf-8")

    def process(self, candidate_file: Path | None = None, *, skip_processed_sources: bool = False) -> list[str]:
        self.init()
        if candidate_file is None:
            files = sorted((self.s.knowledge_root / "02_Candidate").glob("*-candidates.json"))
            candidate_file = files[-1] if files else self.extract()
        elif not candidate_file.exists():
            candidate_file = self.s.knowledge_root / "02_Candidate" / candidate_file
        candidates = json.loads(candidate_file.read_text(encoding="utf-8"))
        outcomes = []
        judge_ai_count = 0
        judge_local_count = 0
        skipped_count = 0

        # Take a snapshot before processing.  A source can produce more than
        # one candidate; marking it processed after the first candidate must
        # not cause the remaining candidates from this run to be skipped.
        eligible_source_ids: set[str] | None = None
        if skip_processed_sources:
            source_ids = {str(source_id) for candidate in candidates for source_id in (candidate.get("source_ids") or [])}
            eligible_source_ids = {source_id for source_id in source_ids if self._source_needs_processing(source_id)}

        for candidate in candidates:
            candidate_source_ids = [str(source_id) for source_id in (candidate.get("source_ids") or [])]
            if eligible_source_ids is not None and candidate_source_ids and not any(source_id in eligible_source_ids for source_id in candidate_source_ids):
                skipped_count += 1
                continue
            decision = self._judge_candidate(candidate)
            if self._last_judge_mode == "ai":
                judge_ai_count += 1
            else:
                judge_local_count += 1
            action = decision.action
            memory_id = decision.target_memory_id
            if action == "create":
                memory_id = self._create_memory(candidate)
            elif action in {"update", "merge"}:
                if not memory_id or not self.conn.execute("SELECT 1 FROM memories WHERE id = ?", (memory_id,)).fetchone():
                    action, memory_id = "candidate", None
                else:
                    self._update_memory(memory_id, candidate, decision, merge=(action == "merge"))
            elif action == "conflict":
                self._save_special_candidate(candidate, "conflicts")
            elif action == "candidate":
                self._save_special_candidate(candidate, "pending")
            elif action == "discard":
                pass
            audit_payload = {"candidate": candidate, "decision": {"action": decision.action, "target_memory_id": decision.target_memory_id, "confidence": decision.confidence, "total_score": decision.total_score, "changes": decision.changes, "merge_memory_ids": decision.merge_memory_ids}}
            self.conn.execute("INSERT INTO memory_actions(memory_id, action, reason, payload, created_at) VALUES (?, ?, ?, ?, ?)", (memory_id, action, decision.reason, json.dumps(audit_payload, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")))
            if memory_id and candidate_source_ids:
                for source_id in candidate_source_ids:
                    # Older databases do not have a uniqueness constraint on
                    # memory_sources, so guard the relation explicitly.
                    self.conn.execute("""INSERT INTO memory_sources(memory_id, source_date, source_type, source_path, created_at)
                        SELECT ?, source_date, source_type, path, ? FROM sources
                        WHERE id = ? AND NOT EXISTS (
                            SELECT 1 FROM memory_sources ms
                            WHERE ms.memory_id = ? AND ms.source_path = sources.path
                        )""", (memory_id, datetime.now().isoformat(timespec="seconds"), source_id, memory_id))
            if candidate_source_ids:
                self._mark_sources_processed(candidate_source_ids, action, candidate)
            self.conn.commit()
            outcomes.append(f"{action}: {candidate['title']}")
        if candidates:
            print(f"[judge] AI 决策 {judge_ai_count} 条，本地规则 {judge_local_count} 条", file=sys.stderr)
        self._last_judge_counts = {"ai": judge_ai_count, "local": judge_local_count}
        if skipped_count:
            print(f"[process] 跳过 {skipped_count} 条未变化候选（Source 已处理）", file=sys.stderr)
        self.rebuild_index()
        return outcomes

    def pipeline_report(self) -> dict[str, Any]:
        """Return the execution mode of the most recent pipeline stages."""
        return {
            "daily": self._last_daily_mode,
            "extract": self._last_extract_mode,
            "judge": dict(self._last_judge_counts),
        }

    @staticmethod
    def _normalized_hash(content: str) -> str:
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _source_needs_processing(self, source_id: str) -> bool:
        """Return whether a Source is new or changed since its last pipeline run."""
        row = self.conn.execute("SELECT path, content_hash, processed_at, pipeline_status FROM sources WHERE id = ?", (source_id,)).fetchone()
        if not row or not row["processed_at"] or row["pipeline_status"] not in {"processed", "review"}:
            return True
        path = self.s.knowledge_root / row["path"]
        if not path.exists():
            # The source content is still represented by the imported hash.
            return False
        try:
            current_hash = self._normalized_hash(path.read_text(encoding="utf-8"))
        except OSError:
            return True
        return current_hash != row["content_hash"]

    def _mark_sources_processed(self, source_ids: list[str], action: str, candidate: dict[str, Any]) -> None:
        status = "review" if action in {"candidate", "conflict"} else "processed"
        candidate_hash = hashlib.sha256(json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        now = datetime.now().isoformat(timespec="seconds")
        for source_id in source_ids:
            self.conn.execute("UPDATE sources SET processed_at = ?, pipeline_status = ?, last_candidate_hash = ? WHERE id = ?", (now, status, candidate_hash, source_id))

    def _judge_candidate(self, candidate: dict[str, Any]) -> MemoryDecision:
        existing = self.retrieve_context(candidate["title"], limit=5)
        ai = AIClient()
        if ai.enabled:
            try:
                payload = self._json_response(ai.ask([{"role": "system", "content": "你是 Memory Judge。只输出合法 JSON。action 必须是 create/update/merge/candidate/discard/conflict。AI 只能给决策，不能写文件。"}, {"role": "user", "content": json.dumps({"candidate": candidate, "existing": [{"id": m["id"], "title": m["title"], "category": m["category"], "content": m["content"]} for m in existing]}, ensure_ascii=False)}]))
                decision = MemoryDecision.from_dict(payload)
                if decision.action in {"update", "merge"} and not decision.target_memory_id:
                    raise ValueError("update/merge requires target_memory_id")
                # Candidate extraction already normalizes and validates the
                # five score dimensions. Judge is responsible for the action,
                # not a second independent score; use the Candidate total so a
                # missing Judge total_score cannot become an accidental zero.
                candidate_total = int(candidate.get("total_score", sum(candidate.get("score", {}).values())))
                if decision.total_score != candidate_total:
                    decision = MemoryDecision(
                        decision.action,
                        decision.reason,
                        decision.target_memory_id,
                        decision.confidence,
                        candidate_total,
                        decision.changes,
                        decision.merge_memory_ids,
                    )
                if decision.action == "create" and candidate_total < 12:
                    decision = MemoryDecision(
                        "candidate",
                        f"AI 新建决策总分 {candidate_total} 低于长期记忆阈值 12，转为待复核候选",
                        None,
                        decision.confidence,
                        candidate_total,
                        decision.changes,
                        decision.merge_memory_ids,
                    )
                self._last_judge_mode = "ai"
                return decision
            except (RuntimeError, ValueError, TypeError, json.JSONDecodeError):
                pass
        self._last_judge_mode = "local"
        if existing and self._similar(existing[0]["title"], candidate["title"]):
            return MemoryDecision("update", "发现相似长期记忆，追加候选内容", existing[0]["id"], 0.65, candidate.get("total_score", 0))
        if candidate.get("total_score", sum(candidate.get("score", {}).values())) < 12:
            return MemoryDecision("candidate", "候选记忆评分不足，保留待确认", None, 0.7, candidate.get("total_score", 0))
        return MemoryDecision("create", "未发现相似记忆且候选具有复用价值", None, 0.65, candidate.get("total_score", 0))

    def _create_memory(self, candidate: dict[str, Any]) -> str:
        memory_id = f"{slugify(candidate['title'])}-{uuid.uuid4().hex[:8]}"
        rel = Path("03_Memory") / candidate.get("category", "General") / f"{memory_id}.md"
        target = self.s.knowledge_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        now = candidate["source_date"]
        meta = {"id": memory_id, "title": candidate["title"], "category": candidate.get("category", "General"), "subcategory": candidate.get("subcategory") or "", "tags": candidate.get("tags", []), "summary": candidate.get("summary", ""), "status": "active", "memory_level": "long_term", "score": candidate.get("total_score", sum(candidate.get("score", {}).values())), "created_at": now, "updated_at": now, "source_dates": [now]}
        target.write_text(dump_frontmatter(meta, f"# {candidate['title']}\n\n{candidate['content']}"), encoding="utf-8")
        self._upsert_meta(meta, rel.as_posix(), now)
        return memory_id

    def _update_memory(self, memory_id: str, candidate: dict[str, Any], decision: MemoryDecision, merge: bool = False) -> None:
        row = self.conn.execute("SELECT path FROM memories WHERE id = ?", (memory_id,)).fetchone()
        path = self.s.knowledge_root / row["path"]
        self._archive_version(memory_id, path)
        meta, old_body = parse_frontmatter(path.read_text(encoding="utf-8"))
        changes = decision.changes
        new_content = str(changes.get("content") or candidate["content"]).strip()
        if changes.get("summary"):
            meta["summary"] = str(changes["summary"])
        if changes.get("tags_to_add"):
            meta["tags"] = list(dict.fromkeys((meta.get("tags") or []) + [str(x) for x in changes["tags_to_add"]]))
        meta["updated_at"] = candidate["source_date"]
        source_dates = meta.get("source_dates") or []
        meta["source_dates"] = list(dict.fromkeys(source_dates + [candidate["source_date"]]))
        path.write_text(dump_frontmatter(meta, old_body.rstrip() + f"\n\n## 更新 {candidate['source_date']}\n\n{new_content}"), encoding="utf-8")
        self._upsert_meta(meta, row["path"], candidate["source_date"])
        for merged_id in decision.merge_memory_ids:
            if merged_id != memory_id:
                self.conn.execute("UPDATE memories SET status = 'archived', updated_at = ? WHERE id = ?", (candidate["source_date"], merged_id))
                self.conn.execute("INSERT OR IGNORE INTO memory_relations(source_memory_id,target_memory_id,relation_type,created_at) VALUES(?,?,?,?)", (memory_id, merged_id, "merged_from", datetime.now().isoformat(timespec="seconds")))

    def _archive_version(self, memory_id: str, path: Path) -> Path:
        archive_dir = self.s.knowledge_root / "06_Archive" / "versions" / memory_id
        archive_dir.mkdir(parents=True, exist_ok=True)
        versions = sorted(archive_dir.glob("v*.md"))
        target = archive_dir / f"v{len(versions) + 1}-{datetime.now().strftime('%Y%m%d%H%M%S')}.md"
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        return target

    def _save_special_candidate(self, candidate: dict[str, Any], kind: str) -> Path:
        target = self.s.knowledge_root / "02_Candidate" / f"{kind}-{candidate['source_date']}-{slugify(candidate['title'])}.json"
        target.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    @staticmethod
    def _similar(a: str, b: str) -> bool:
        aa, bb = set(a.lower()), set(b.lower())
        return bool(aa and bb and len(aa & bb) / max(1, len(aa | bb)) >= 0.45)

    def _upsert_meta(self, meta: dict[str, Any], rel: str, now: str) -> None:
        subcategory = meta.get("subcategory", "")
        if isinstance(subcategory, list):
            subcategory = ", ".join(str(x) for x in subcategory)
        self.conn.execute("INSERT INTO memories(id,title,category,subcategory,tags,summary,path,score,memory_level,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,category=excluded.category,subcategory=excluded.subcategory,tags=excluded.tags,summary=excluded.summary,path=excluded.path,score=excluded.score,memory_level=excluded.memory_level,status=excluded.status,updated_at=excluded.updated_at", (meta["id"], meta.get("title", meta["id"]), meta.get("category", "General"), subcategory, json.dumps(meta.get("tags", []), ensure_ascii=False), meta.get("summary", ""), rel, int(meta.get("score") or 0), meta.get("memory_level", "long_term"), meta.get("status", "active"), meta.get("created_at", now), meta.get("updated_at", now)))
        self.conn.commit()

    def rebuild_index(self) -> int:
        count = 0
        for path in (self.s.knowledge_root / "03_Memory").rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            if not meta.get("id"):
                # Legacy Dianjia notes predate frontmatter; index their inline metadata.
                title_match = re.search(r"^#\s+(.+)$", body, re.M)
                id_match = re.search(r"memory_id[：:]\s*`?([\w.-]+)", body, re.I)
                category_match = re.search(r"一级分类[：:]\s*([^\n*]+)", body)
                meta = {"id": id_match.group(1) if id_match else slugify(path.stem), "title": title_match.group(1).strip() if title_match else path.stem, "category": category_match.group(1).strip() if category_match else path.parent.name, "summary": "", "tags": [], "status": "active", "memory_level": "long_term", "created_at": date.today().isoformat(), "updated_at": date.today().isoformat(), "score": 0}
            self._upsert_meta(meta, path.relative_to(self.s.knowledge_root).as_posix(), meta.get("updated_at", date.today().isoformat()))
            count += 1
        self._write_index()
        return count

    def _write_index(self) -> None:
        grouped: dict[str, list[tuple[str, str]]] = {}
        for row in self.conn.execute("SELECT title, category, path FROM memories WHERE status = 'active' ORDER BY category, title"):
            grouped.setdefault(row["category"], []).append((row["title"], row["path"]))
        lines = ["# Dianjia Knowledge Index", "", "Automatically generated from active Markdown memories.", ""]
        for category, items in grouped.items():
            lines += [f"## {category}", ""]
            lines.extend(f"- [{title}]({path})" for title, path in items)
            lines.append("")
        (self.s.knowledge_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")

    def status(self) -> dict[str, int]:
        return {"sources": self.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0], "memories": self.conn.execute("SELECT COUNT(*) FROM memories WHERE status='active'").fetchone()[0], "actions": self.conn.execute("SELECT COUNT(*) FROM memory_actions").fetchone()[0]}
