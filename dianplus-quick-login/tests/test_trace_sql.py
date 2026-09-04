import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.cookiejar import Cookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from urllib.parse import parse_qs

from trace_sql import (
    TraceError,
    build_trace_request,
    default_output_path,
    extract_trace_sql,
    main,
    write_sql,
)


def make_cookie(name: str, value: str) -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain="devops.dianplus.cn",
        domain_specified=True,
        domain_initial_dot=False,
        path="/",
        path_specified=True,
        secure=True,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={"HttpOnly": None},
        rfc2109=False,
    )


class TraceRequestTests(unittest.TestCase):
    def test_build_trace_request_posts_urlencoded_trace_id_and_session_cookie(self):
        request = build_trace_request(
            "https://example.test/trace", "trace id&=1", [make_cookie("JSESSIONID", "abc")]
        )

        self.assertEqual(request.method, "POST")
        self.assertEqual(request.data, b"traceId=trace+id%26%3D1")
        self.assertEqual(request.get_header("Content-type"), "application/x-www-form-urlencoded")
        self.assertEqual(request.get_header("Cookie"), "JSESSIONID=abc")


class TraceExtractionTests(unittest.TestCase):
    def test_extract_trace_sql_returns_only_statement_after_marker(self):
        payload = {
            "resultObject": [
                {
                    "children": [
                        {
                            "details": (
                                "other log\n"
                                "行查询语句: \n"
                                "SELECT id FROM orders WHERE brand_id = 10010\n"
                                "]\n"
                                "following log"
                            )
                        }
                    ]
                }
            ]
        }

        sql = extract_trace_sql(payload)

        self.assertEqual(sql, "SELECT id FROM orders WHERE brand_id = 10010")

    def test_extract_trace_sql_skips_trace_comment_before_statement(self):
        payload = {
            "resultObject": [
                {
                    "children": [
                        {
                            "details": (
                                "行查询语句:\n"
                                "/*traceId:404027-cc80d806-a48a-43af-8945-7f7b8791ff31-1788319108518*/ "
                                "SELECT yearMonthDay, code FROM daily_sales\n"
                                "]\n"
                                "following log"
                            )
                        }
                    ]
                }
            ]
        }

        sql = extract_trace_sql(payload)

        self.assertEqual(sql, "SELECT yearMonthDay, code FROM daily_sales")

    def test_extract_trace_sql_rejects_missing_nested_details(self):
        with self.assertRaisesRegex(TraceError, "resultObject"):
            extract_trace_sql({"resultObject": []})

    def test_extract_trace_sql_rejects_details_without_marker(self):
        payload = {"resultObject": [{"children": [{"details": "no query here"}]}]}

        with self.assertRaisesRegex(TraceError, "行查询语句"):
            extract_trace_sql(payload)


class SqlOutputTests(unittest.TestCase):
    def test_default_output_path_uses_trace_id_without_overwriting_other_queries(self):
        self.assertEqual(
            default_output_path("trace-123"), Path("trace-sql") / "trace-123.sql"
        )

    def test_write_sql_creates_owner_only_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "trace.sql"
            write_sql("SELECT id FROM trace_table", path)

            contents = path.read_text(encoding="utf-8")
            mode = path.stat().st_mode & 0o777

        self.assertEqual(contents, "SELECT id FROM trace_table\n")
        self.assertEqual(mode, 0o600)


class DianplusHandler(BaseHTTPRequestHandler):
    trace_id = None
    cookie_header = None

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
        if self.path == "/login":
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", "JSESSIONID=test-session; Path=/; HttpOnly")
            self.end_headers()
            return
        if self.path == "/trace":
            DianplusHandler.trace_id = parse_qs(body)["traceId"][0]
            DianplusHandler.cookie_header = self.headers.get("Cookie")
            payload = {
                "resultObject": [
                    {
                        "children": [
                            {"details": "行查询语句:\nSELECT id FROM trace_table\n]\nnext log"}
                        ]
                    }
                ]
            }
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        self.send_error(404)

    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass


class TraceCliTests(unittest.TestCase):
    def setUp(self):
        DianplusHandler.trace_id = None
        DianplusHandler.cookie_header = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), DianplusHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_main_logs_in_queries_trace_and_prints_only_sql(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            sql_path = Path(directory) / "retrieved.sql"
            base_url = f"http://127.0.0.1:{self.server.server_port}"
            env_path.write_text(
                "DIANPLUS_USERNAME=alice\n"
                "DIANPLUS_PASSWORD=secret\n"
                f"DIANPLUS_LOGIN_URL={base_url}/login\n"
                f"DIANPLUS_TRACE_URL={base_url}/trace\n",
                encoding="utf-8",
            )
            output = StringIO()
            errors = StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                result = main(
                    [
                        "trace-123",
                        "--env-file",
                        str(env_path),
                        "--output",
                        str(sql_path),
                    ]
                )

            saved_sql = sql_path.read_text(encoding="utf-8")

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "SELECT id FROM trace_table\n")
        self.assertEqual(saved_sql, "SELECT id FROM trace_table\n")
        self.assertIn("SQL saved", errors.getvalue())
        self.assertEqual(DianplusHandler.trace_id, "trace-123")
        self.assertIn("JSESSIONID=test-session", DianplusHandler.cookie_header)

    def test_main_reports_invalid_trace_response_without_sql(self):
        errors = StringIO()
        with redirect_stderr(errors):
            result = main(["trace-123", "--env-file", "/missing/.env"])

        self.assertEqual(result, 2)
        self.assertIn("Configuration error", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
