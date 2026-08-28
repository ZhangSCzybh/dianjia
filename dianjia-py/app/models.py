from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class Source:
    source_id: str
    source_type: str
    title: str
    content: str
    source_date: str
    origin_path: str | None
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    @classmethod
    def create(cls, content: str, title: str = "conversation", source_type: str = "text", source_date: str | None = None, origin_path: str | None = None, metadata: dict[str, Any] | None = None) -> "Source":
        now = datetime.now().isoformat(timespec="seconds")
        return cls(str(uuid.uuid4()), source_type, title, content, source_date or date.today().isoformat(), origin_path, hashlib.sha256(content.encode("utf-8")).hexdigest(), metadata or {}, now)

    def to_dict(self) -> dict[str, Any]:
        return {"source_id": self.source_id, "source_type": self.source_type, "title": self.title, "content": self.content, "source_date": self.source_date, "origin_path": self.origin_path, "content_hash": self.content_hash, "metadata": self.metadata, "created_at": self.created_at}


@dataclass
class MemoryDecision:
    action: str
    reason: str
    target_memory_id: str | None = None
    confidence: float = 0.0
    total_score: int = 0
    changes: dict[str, Any] = field(default_factory=dict)
    merge_memory_ids: list[str] = field(default_factory=list)

    ALLOWED_ACTIONS = {"create", "update", "merge", "candidate", "discard", "conflict"}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryDecision":
        action = str(payload.get("action", "candidate")).lower()
        if action not in cls.ALLOWED_ACTIONS:
            raise ValueError(f"invalid memory action: {action}")
        target = payload.get("target_memory_id")
        confidence = float(payload.get("confidence", 0.0))
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        score = payload.get("score", {})
        total = int(payload.get("total_score", sum(int(score.get(k, 0)) for k in ("reusability", "importance", "uniqueness", "stability", "personal_relevance"))))
        if not 0 <= total <= 25:
            raise ValueError("total_score must be between 0 and 25")
        merge_ids = payload.get("merge_memory_ids", [])
        if isinstance(merge_ids, str):
            merge_ids = [merge_ids]
        return cls(action, str(payload.get("reason", "")), str(target) if target else None, confidence, total, payload.get("changes") or {}, [str(x) for x in merge_ids])

