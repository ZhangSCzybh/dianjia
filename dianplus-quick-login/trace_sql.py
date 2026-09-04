"""Fetch the row-query SQL statement associated with a Dianplus trace ID."""

from __future__ import annotations

import argparse
import json
import re
import sys
from http.cookiejar import Cookie
from pathlib import Path
from typing import Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from login import DEFAULT_LOGIN_URL, LoginError, cookie_header, is_authenticated, load_dotenv, login


DEFAULT_TRACE_URL = "https://devops.dianplus.cn/rs/djlog/trace/getTrace.do"
QUERY_MARKER = "行查询语句"
SQL_START = re.compile(
    r"\b(?:SELECT|WITH|INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE)\b",
    re.IGNORECASE,
)
SAFE_TRACE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class TraceError(RuntimeError):
    """Raised when a trace cannot produce a row-query SQL statement."""


def build_trace_request(url: str, trace_id: str, cookies: Iterable[Cookie]) -> Request:
    """Build the authenticated form request accepted by the Trace endpoint."""
    if not trace_id.strip():
        raise TraceError("traceId cannot be empty")
    return Request(
        url,
        data=urlencode({"traceId": trace_id}).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": cookie_header(cookies),
        },
    )


def fetch_trace_payload(url: str, trace_id: str, cookies: Iterable[Cookie]) -> object:
    """Fetch and decode the JSON response for a trace ID."""
    try:
        with urlopen(build_trace_request(url, trace_id, cookies), timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise TraceError(f"Trace endpoint returned HTTP {error.code}") from error
    except URLError as error:
        raise TraceError(f"Could not reach Trace endpoint: {error.reason}") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TraceError("Trace endpoint did not return valid JSON") from error


def extract_trace_sql(payload: object) -> str:
    """Extract SQL after the row-query marker, excluding trace metadata."""
    try:
        details = payload["resultObject"][0]["children"][0]["details"]  # type: ignore[index]
    except (KeyError, IndexError, TypeError) as error:
        raise TraceError("Trace response does not contain resultObject[0].children[0].details") from error

    if not isinstance(details, str):
        raise TraceError("Trace response details is not text")

    marker_offset = details.find(QUERY_MARKER)
    if marker_offset < 0:
        raise TraceError(f"Trace details does not contain {QUERY_MARKER}")

    query_block = re.split(r"\r?\n\]", details[marker_offset + len(QUERY_MARKER) :], maxsplit=1)[0]
    statement_start = SQL_START.search(query_block)
    if not statement_start:
        raise TraceError(f"No SQL follows {QUERY_MARKER}")
    return query_block[statement_start.start() :].strip()


def default_output_path(trace_id: str) -> Path:
    """Build a per-trace output path without allowing path traversal."""
    if not SAFE_TRACE_ID.fullmatch(trace_id):
        raise TraceError("traceId contains characters unsafe for a filename")
    return Path("trace-sql") / f"{trace_id}.sql"


def write_sql(sql: str, path: Path) -> None:
    """Persist a statement in an owner-only text file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{sql.rstrip()}\n", encoding="utf-8")
    path.chmod(0o600)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print the row-query SQL statement for a Dianplus trace ID."
    )
    parser.add_argument("trace_id", help="Trace ID returned by Dianplus DevOps logs")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--output",
        type=Path,
        help="file that receives the extracted SQL; defaults to trace-sql/<traceId>.sql",
    )
    args = parser.parse_args(argv)

    try:
        values = load_dotenv(args.env_file)
    except (OSError, ValueError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    required = ("DIANPLUS_USERNAME", "DIANPLUS_PASSWORD")
    missing = [name for name in required if not values.get(name)]
    if missing:
        print(f"Configuration error: missing {', '.join(missing)}", file=sys.stderr)
        return 2

    login_url = values.get("DIANPLUS_LOGIN_URL", DEFAULT_LOGIN_URL)
    trace_url = values.get("DIANPLUS_TRACE_URL", DEFAULT_TRACE_URL)
    try:
        final_url, cookies = login(
            login_url,
            values["DIANPLUS_USERNAME"],
            values["DIANPLUS_PASSWORD"],
        )
        if not is_authenticated(final_url, login_url, cookies):
            raise LoginError("Login did not produce a session cookie or leave the login page")
        sql = extract_trace_sql(fetch_trace_payload(trace_url, args.trace_id, cookies))
        output_path = args.output or default_output_path(args.trace_id)
        write_sql(sql, output_path)
        print(sql)
        print(f"SQL saved to {output_path}", file=sys.stderr)
    except (LoginError, TraceError, OSError) as error:
        print(f"Trace query failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
