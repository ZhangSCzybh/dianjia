from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from .markdown import dump_frontmatter, parse_frontmatter, slugify


def migrate_legacy_memories(knowledge_root: Path) -> list[Path]:
    """Add structured frontmatter to legacy memory notes without changing bodies."""
    migrated: list[Path] = []
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    archive_root = knowledge_root / "06_Archive" / "migrations" / f"legacy-frontmatter-{stamp}"
    for path in sorted((knowledge_root / "03_Memory").rglob("*.md")):
        original = path.read_text(encoding="utf-8")
        frontmatter, _ = parse_frontmatter(original)
        if frontmatter.get("id"):
            if frontmatter.get("migrated_from") == "legacy_inline_metadata" and frontmatter.get("status") != "active":
                frontmatter["status"] = "active"
                frontmatter["verification_status"] = frontmatter.get("verification_status", "pending")
                path.write_text(dump_frontmatter(frontmatter, parse_frontmatter(original)[1]), encoding="utf-8")
                migrated.append(path)
            continue
        meta = _legacy_metadata(path, original)
        archive_path = archive_root / path.relative_to(knowledge_root)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_text(original, encoding="utf-8")
        path.write_text(dump_frontmatter(meta, original), encoding="utf-8")
        migrated.append(path)
    return migrated


def _legacy_metadata(path: Path, body: str) -> dict:
    title = _find(body, r"^#\s+(.+)$") or path.stem
    memory_id = _find(body, r"memory_id[：:]\s*`?([\w.-]+)") or slugify(path.stem)
    category = _find(body, r"一级分类[：:]\s*([^\n*]+)") or path.parent.parent.name
    subcategory = _find(body, r"二级分类[：:]\s*([^\n*]+)") or path.parent.name
    tags_raw = _find(body, r"标签[：:]\s*([^\n*]+)") or ""
    tags = [item.strip().strip("`") for item in re.split(r"[、,，]", tags_raw) if item.strip()]
    summary = _section(body, "一句话结论") or _section(body, "核心结论") or ""
    source_date = _find(body, r"来源日期[：:]\s*(\d{4}-\d{2}-\d{2})")
    created = _find(body, r"创建时间[：:]\s*(\d{4}-\d{2}-\d{2})") or source_date or date.today().isoformat()
    updated = _find(body, r"更新时间[：:]\s*(\d{4}-\d{2}-\d{2})") or created
    score = int(_find(body, r"总分[：:]?\s*(\d+)") or 0)
    status_text = _find(body, r"状态[：:]\s*([^\n*]+)") or "长期有效"
    verification_status = "pending" if any(word in status_text for word in ("待验证", "待确认", "候选")) else "verified"
    # Notes in 03_Memory are established knowledge records. Keep them searchable
    # and carry uncertainty separately instead of demoting them to candidates.
    return {"id": memory_id, "title": title, "category": category.strip(), "subcategory": subcategory.strip(), "tags": tags, "summary": summary, "status": "active", "verification_status": verification_status, "memory_level": "core_memory" if "core_memory" in body else "long_term", "score": score, "created_at": created, "updated_at": updated, "source_dates": [source_date or created], "migrated_from": "legacy_inline_metadata"}


def _find(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.M)
    return match.group(1).strip() if match else None


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^##\s+{re.escape(heading)}\s*\n+([\s\S]*?)(?=^##\s+|\Z)", text, re.M)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
