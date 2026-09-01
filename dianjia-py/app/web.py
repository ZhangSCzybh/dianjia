from __future__ import annotations

import json
import mimetypes
import threading
import traceback
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import settings
from .services import MemoryService

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
RUN_JOBS: dict[str, dict] = {}
RUN_JOBS_LOCK = threading.Lock()
MAX_WEB_INPUT_CHARS = 100_000


def _run_daily_job(job_id: str, day: str | None) -> None:
    try:
        outcomes = Handler.service.run_daily(day)
    except Exception as exc:
        traceback.print_exc()
        with RUN_JOBS_LOCK:
            RUN_JOBS[job_id] = {"status": "failed", "error": str(exc)}
    else:
        with RUN_JOBS_LOCK:
            RUN_JOBS[job_id] = {"status": "completed", "outcomes": outcomes, "pipeline": Handler.service.pipeline_report()}


class Handler(BaseHTTPRequestHandler):
    service = MemoryService(settings)

    def _send(self, payload, status=HTTPStatus.OK, content_type="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else (json.dumps(payload, ensure_ascii=False).encode("utf-8") if content_type.startswith("application/json") else str(payload).encode("utf-8"))
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._send((WEB_ROOT / "index.html").read_bytes(), content_type="text/html; charset=utf-8")
            elif parsed.path == "/api/status":
                self._send(self.service.status())
            elif parsed.path == "/api/search":
                query = parse_qs(parsed.query).get("q", [""])[0]
                limit = int(parse_qs(parsed.query).get("limit", [10])[0])
                self._send([dict(row) for row in self.service.search(query, limit)] if query else [])
            elif parsed.path.startswith("/api/run-daily/"):
                job_id = parsed.path.rsplit("/", 1)[-1]
                with RUN_JOBS_LOCK:
                    job = RUN_JOBS.get(job_id)
                self._send(job or {"error": "run-daily job not found"}, HTTPStatus.OK if job else HTTPStatus.NOT_FOUND)
            else:
                self._send({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):
        try:
            if self.path == "/api/ingest":
                payload = self._json()
                text = str(payload.get("content", "")).strip()
                if not text:
                    return self._send({"error": "content is required"}, HTTPStatus.BAD_REQUEST)
                if len(text) > MAX_WEB_INPUT_CHARS:
                    return self._send({"error": f"导入内容不能超过 {MAX_WEB_INPUT_CHARS:,} 个字符，当前为 {len(text):,} 个字符"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                path = self.service.ingest_text(text, payload.get("name", "web-input"), payload.get("date"), "web")
                self._send({"path": str(path)})
            elif self.path == "/api/daily":
                payload = self._json()
                self._send({"path": str(self.service.daily(payload.get("date"))), "pipeline": self.service.pipeline_report()})
            elif self.path == "/api/extract":
                payload = self._json()
                self._send({"path": str(self.service.extract(payload.get("date"))), "pipeline": self.service.pipeline_report()})
            elif self.path == "/api/process":
                payload = self._json()
                candidate = payload.get("candidate_file")
                self._send({"outcomes": self.service.process(Path(candidate) if candidate else None), "pipeline": self.service.pipeline_report()})
            elif self.path == "/api/run-daily":
                payload = self._json()
                job_id = uuid.uuid4().hex
                with RUN_JOBS_LOCK:
                    RUN_JOBS[job_id] = {"status": "running"}
                threading.Thread(target=_run_daily_job, args=(job_id, payload.get("date")), daemon=True).start()
                self._send({"job_id": job_id, "status": "running"}, HTTPStatus.ACCEPTED)
            elif self.path == "/api/ask":
                payload = self._json()
                question = str(payload.get("question", "")).strip()
                if not question:
                    return self._send({"error": "question is required"}, HTTPStatus.BAD_REQUEST)
                answer, memories = self.service.ask(question, int(payload.get("limit", 5)))
                self._send({"answer": answer, "memories": memories})
            elif self.path == "/api/rebuild-index":
                self._send({"count": self.service.rebuild_index()})
            else:
                self._send({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format, *args):
        print(f"[web] {self.address_string()} - {format % args}")


def serve(host: str = "127.0.0.1", port: int = 8765):
    Handler.service.init()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Dianjia Web: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Dianjia Web")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
