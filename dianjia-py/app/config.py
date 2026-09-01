from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE entries without requiring python-dotenv."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@dataclass(frozen=True)
class Settings:
    project_root: Path
    knowledge_root: Path
    data_root: Path
    db_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(__file__).resolve().parents[1]
        _load_dotenv(root / ".env")
        knowledge = Path(os.getenv("DIANJIA_KNOWLEDGE_ROOT", root.parent / "dianjia")).expanduser()
        data = Path(os.getenv("DIANJIA_DATA_ROOT", root / "data")).expanduser()
        return cls(root, knowledge, data, data / "dianjia.db")


settings = Settings.from_env()
