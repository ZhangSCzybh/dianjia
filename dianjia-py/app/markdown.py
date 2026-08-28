from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    raw, body = parts[1], parts[2].lstrip("\n")
    data: dict[str, Any] = {}
    current_list: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_list:
            data.setdefault(current_list, []).append(line[4:].strip().strip("'\""))
            continue
        match = re.match(r"^([^:#][^:]*):(?:\s*)(.*)$", line)
        if not match:
            continue
        key, value = match.group(1).strip(), match.group(2).strip()
        if value:
            if value.startswith("[") and value.endswith("]"):
                data[key] = [x.strip().strip("'\"") for x in value[1:-1].split(",") if x.strip()]
            else:
                data[key] = value.strip("'\"")
            current_list = None
        else:
            data[key] = []
            current_list = key
    return data, body


def dump_frontmatter(meta: dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    lines += ["---", "", body.rstrip(), ""]
    return "\n".join(lines)


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value, flags=re.UNICODE).strip("-")
    return value.lower() or "memory"
