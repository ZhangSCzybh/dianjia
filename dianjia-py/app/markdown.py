from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        return {}, text
    raw_lines, body_lines = lines[1:end], lines[end + 1:]
    data: dict[str, Any] = {}
    current_list: str | None = None
    block_key: str | None = None
    block_lines: list[str] = []
    for line in raw_lines:
        if block_key and (line.startswith("  ") or not line.strip()):
            block_lines.append(line[2:] if line.startswith("  ") else "")
            continue
        if block_key:
            data[block_key] = "\n".join(block_lines).rstrip()
            block_key, block_lines = None, []
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
            if value in {"|", ">"}:
                block_key = key
                block_lines = []
            elif value.startswith("[") and value.endswith("]"):
                data[key] = [x.strip().strip("'\"") for x in value[1:-1].split(",") if x.strip()]
            else:
                data[key] = value.strip("'\"")
            current_list = None
        else:
            data[key] = []
            current_list = key
    if block_key:
        data[block_key] = "\n".join(block_lines).rstrip()
    return data, "\n".join(body_lines).lstrip("\n")


def dump_frontmatter(meta: dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        elif isinstance(value, str) and "\n" in value:
            lines.append(f"{key}: |")
            lines.extend(f"  {item}" for item in value.splitlines())
        else:
            lines.append(f"{key}: {value}")
    lines += ["---", "", body.rstrip(), ""]
    return "\n".join(lines)


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value, flags=re.UNICODE).strip("-")
    return value.lower() or "memory"
