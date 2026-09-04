import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.cookiejar import Cookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path

from login import (
    build_login_request,
    cookie_header,
    is_authenticated,
    load_dotenv,
    main,
    write_outputs,
)


def make_cookie(name: str, value: str, secure: bool = True) -> Cookie:
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
        secure=secure,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={"HttpOnly": None},
        rfc2109=False,
    )


class DotenvTests(unittest.TestCase):
    def test_load_dotenv_reads_assignments_and_ignores_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "# local secrets\n"
                "DIANPLUS_USERNAME=congrong\n"
                "export DIANPLUS_PASSWORD='Aa123456'\n",
                encoding="utf-8",
            )

            values = load_dotenv(path)

        self.assertEqual(values["DIANPLUS_USERNAME"], "congrong")
        self.assertEqual(values["DIANPLUS_PASSWORD"], "Aa123456")


class ProtocolTests(unittest.TestCase):
    def test_build_login_request_urlencodes_expected_fields(self):
        request = build_login_request(
            "https://example.test/login", "alice", "p&= value"
        )

        self.assertEqual(request.method, "POST")
        self.assertEqual(
            request.data, b"username=alice&password=p%26%3D+value"
        )
        self.assertEqual(
            request.get_header("Content-type"),
            "application/x-www-form-urlencoded",
        )

    def test_cookie_header_joins_cookie_names_and_values(self):
        header = cookie_header(
            [make_cookie("JSESSIONID", "abc"), make_cookie("ROLE", "operator")]
        )

        self.assertEqual(header, "JSESSIONID=abc; ROLE=operator")

    def test_is_authenticated_requires_session_cookie_and_non_login_destination(self):
        cookies = [make_cookie("JSESSIONID", "abc")]

        self.assertTrue(
            is_authenticated(
                "https://example.test/", "https://example.test/login", cookies
            )
        )
        self.assertFalse(
            is_authenticated(
                "https://example.test/login", "https://example.test/login", cookies
            )
        )
        self.assertFalse(
            is_authenticated("https://example.test/", "https://example.test/login", [])
        )


class OutputTests(unittest.TestCase):
    def test_write_outputs_creates_reusable_header_and_json(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            write_outputs(
                [make_cookie("JSESSIONID", "abc"), make_cookie("ROLE", "operator")],
                output_dir,
            )

            header = (output_dir / "session.cookies.txt").read_text(encoding="utf-8")
            payload = json.loads(
                (output_dir / "session.cookies.json").read_text(encoding="utf-8")
            )

        self.assertEqual(header, "JSESSIONID=abc; ROLE=operator\n")
        self.assertEqual(payload["cookie_header"], "JSESSIONID=abc; ROLE=operator")
        self.assertEqual(payload["cookies"][0]["name"], "JSESSIONID")
        self.assertTrue(payload["cookies"][0]["secure"])


class LoginHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if self.path != "/login":
            self.send_error(404)
            return
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie", "JSESSIONID=test-session; Path=/; HttpOnly")
        self.send_header("Set-Cookie", "CURRENT_ROLERELATION_ID=role-1; Path=/")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass


class CliTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), LoginHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_main_logs_in_writes_artifacts_and_hides_values_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            env_path = project_dir / ".env"
            env_path.write_text(
                "DIANPLUS_USERNAME=alice\n"
                "DIANPLUS_PASSWORD=secret\n"
                f"DIANPLUS_LOGIN_URL=http://127.0.0.1:{self.server.server_port}/login\n",
                encoding="utf-8",
            )
            output = StringIO()
            with redirect_stdout(output):
                result = main(["--env-file", str(env_path), "--output-dir", str(project_dir)])

            header = (project_dir / "session.cookies.txt").read_text(encoding="utf-8")

        self.assertEqual(result, 0)
        self.assertIn("Session cookies saved", output.getvalue())
        self.assertNotIn("test-session", output.getvalue())
        self.assertIn("JSESSIONID=test-session", header)

    def test_main_reports_missing_required_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("DIANPLUS_USERNAME=alice\n", encoding="utf-8")
            errors = StringIO()
            with redirect_stderr(errors):
                result = main(["--env-file", str(env_path)])

        self.assertEqual(result, 2)
        self.assertIn("DIANPLUS_PASSWORD", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
