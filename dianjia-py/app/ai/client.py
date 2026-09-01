from __future__ import annotations

import json
import http.client
import os
import shutil
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

from ..config import _load_dotenv


class AIClient:
    """Tiny OpenAI-compatible client kept optional for the offline MVP."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        _load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        self.provider = (os.getenv("AI_PROVIDER", "chat_completions") or "chat_completions").strip().lower().replace("-", "_")
        self.api_key = api_key or os.getenv("AI_API_KEY")
        self.base_url = (base_url or os.getenv("AI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.getenv("AI_MODEL", "gpt-5")
        configured_codex = os.getenv("AI_CODEX_BIN", "").strip()
        self.codex_bin = configured_codex or shutil.which("codex") or "/Applications/ChatGPT.app/Contents/Resources/codex"

    @property
    def enabled(self) -> bool:
        if self.provider == "codex_cli":
            return True
        return bool(self.api_key)

    def ask(self, messages: list[dict[str, str]], *, temperature: float = 0.2) -> str:
        if self.provider == "codex_cli":
            return self._ask_codex_cli(messages)
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
        except (http.client.HTTPException, TimeoutError, ConnectionError, OSError) as exc:
            # Some gateways close the socket without returning an HTTP status.
            # Keep the RuntimeError contract so callers can use local fallback.
            raise RuntimeError(f"AI API 连接中断: {exc}") from exc
        return result["choices"][0]["message"]["content"]

    def _ask_codex_cli(self, messages: list[dict[str, str]]) -> str:
        prompt = "\n\n".join(f"{message.get('role', 'user').upper()}:\n{message.get('content', '')}" for message in messages)
        command = [
            self.codex_bin,
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--json",
            "--model",
            self.model,
            "-C",
            str(Path.cwd()),
        ]
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"Codex CLI 不存在：{self.codex_bin}") from exc
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"Codex CLI 调用失败：{exc}") from exc

        text = ""
        for line in completed.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item") if isinstance(event, dict) else None
            if event.get("type") == "item.completed" and isinstance(item, dict) and item.get("type") == "agent_message":
                text = str(item.get("text") or "").strip()
        if completed.returncode != 0:
            detail = completed.stderr.strip() or text or f"exit code {completed.returncode}"
            raise RuntimeError(f"Codex CLI 返回错误：{detail[:500]}")
        if not text:
            raise RuntimeError("Codex CLI 未返回 agent_message")
        return text
