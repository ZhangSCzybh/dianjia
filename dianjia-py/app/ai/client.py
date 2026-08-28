from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from pathlib import Path

from ..config import _load_dotenv


class AIClient:
    """Tiny OpenAI-compatible client kept optional for the offline MVP."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        _load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        self.api_key = api_key or os.getenv("AI_API_KEY")
        self.base_url = (base_url or os.getenv("AI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.getenv("AI_MODEL", "gpt-5")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def ask(self, messages: list[dict[str, str]], *, temperature: float = 0.2) -> str:
        if not self.api_key:
            raise RuntimeError("AI_API_KEY is not configured; use the offline heuristic pipeline")
        payload = json.dumps({"model": self.model, "messages": messages, "temperature": temperature}).encode()
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                # Some hosted gateways reject urllib's default Python user-agent.
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0 Safari/537.36 dianjia-memory/0.2",
                "Origin": "https://opencode.ai",
                "Referer": "https://opencode.ai/",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"AI API 返回 HTTP {exc.code}（请求地址：{self.base_url}/chat/completions）：{detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"无法连接 AI API: {exc.reason}") from exc
        return result["choices"][0]["message"]["content"]
