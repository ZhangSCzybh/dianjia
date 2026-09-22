from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ..config import _load_dotenv


class TypeSafeError(RuntimeError):
    """A sanitized TypeSafe API failure suitable for the fallback chain."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


class SystemOneClient:
    """Small standard-library client for TypeSafe's System One endpoint."""

    RETRYABLE_STATUSES = {429, 529}

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        *,
        timeout: int = 30,
        max_attempts: int = 3,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] | None = None,
    ):
        _load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        configured_key = api_key if api_key is not None else os.getenv("TYPESAFE_API_KEY")
        self.api_key = (configured_key or "").strip() or None
        self.base_url = (base_url or os.getenv("TYPESAFE_BASE_URL") or "https://api.typesafe.ai/v1").strip().rstrip("/")
        self.model = (model or os.getenv("TYPESAFE_MODEL") or "jev-latest").strip()
        self.timeout = max(1, int(timeout))
        self.max_attempts = max(1, int(max_attempts))
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep or time.sleep

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def evaluate(self, *, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise TypeSafeError("TYPESAFE_API_KEY is not configured")
        endpoint = self.base_url if self.base_url.endswith("/systemone") else f"{self.base_url}/systemone"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps({"state": state, "model": self.model, "questions": questions}, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "dianjia-memory/0.1",
            },
            method="POST",
        )
        for attempt in range(self.max_attempts):
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    raw = response.read()
                break
            except urllib.error.HTTPError as exc:
                status = exc.code
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                exc.close()
                if status in self.RETRYABLE_STATUSES and attempt + 1 < self.max_attempts:
                    self._sleep(self._retry_delay(retry_after, attempt))
                    continue
                raise TypeSafeError(f"TypeSafe API returned HTTP {status}", status=status) from exc
            except urllib.error.URLError as exc:
                raise TypeSafeError(f"Unable to connect to TypeSafe API: {exc.reason}") from exc
            except (TimeoutError, ConnectionError, OSError) as exc:
                raise TypeSafeError(f"TypeSafe API connection failed: {type(exc).__name__}") from exc
        else:  # pragma: no cover - the loop either succeeds or raises
            raise TypeSafeError("TypeSafe API retry budget exhausted")

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TypeSafeError("TypeSafe API returned invalid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("model"), str) or not isinstance(payload.get("answers"), dict):
            raise TypeSafeError("TypeSafe API returned an invalid response shape")
        usage = payload.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise TypeSafeError("TypeSafe API returned invalid usage metadata")
        return {"model": payload["model"], "answers": payload["answers"], "usage": usage or {}}

    @staticmethod
    def _retry_delay(retry_after: str | None, attempt: int) -> float:
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), 30.0))
            except ValueError:
                pass
        return min(float(2**attempt), 8.0)
