"""Authenticate with Dianplus DevOps and persist reusable session cookies."""

from __future__ import annotations

import argparse
import json
import sys
from http.cookiejar import CookieJar
from http.cookiejar import Cookie
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlencode, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


DEFAULT_LOGIN_URL = "https://devops.dianplus.cn/login"


class LoginError(RuntimeError):
    """Raised when the endpoint does not establish an authenticated session."""


def load_dotenv(path: Path) -> dict[str, str]:
    """Load simple KEY=VALUE assignments without modifying process environment."""
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"Invalid dotenv assignment in {path}: {raw_line!r}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def build_login_request(url: str, username: str, password: str) -> Request:
    """Build the form-encoded request expected by the Dianplus login endpoint."""
    data = urlencode({"username": username, "password": password}).encode("utf-8")
    return Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def cookie_header(cookies: Iterable[Cookie]) -> str:
    """Format cookies as the value accepted by an HTTP Cookie request header."""
    return "; ".join(f"{cookie.name}={cookie.value}" for cookie in cookies)


def is_authenticated(final_url: str, login_url: str, cookies: Iterable[Cookie]) -> bool:
    """Recognize the session contract observed from the Dianplus login endpoint."""
    final = urlsplit(final_url)
    login = urlsplit(login_url)
    is_login_page = (final.scheme, final.netloc, final.path.rstrip("/")) == (
        login.scheme,
        login.netloc,
        login.path.rstrip("/"),
    )
    return not is_login_page and any(cookie.name == "JSESSIONID" for cookie in cookies)


def write_outputs(cookies: Iterable[Cookie], output_dir: Path) -> None:
    """Write reusable cookie artifacts with owner-only permissions."""
    materialized = list(cookies)
    header = cookie_header(materialized)
    if not header:
        raise ValueError("Cannot write an empty cookie header")

    output_dir.mkdir(parents=True, exist_ok=True)
    header_path = output_dir / "session.cookies.txt"
    json_path = output_dir / "session.cookies.json"
    payload = {
        "cookie_header": header,
        "cookies": [
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "secure": cookie.secure,
                "expires": cookie.expires,
                "http_only": cookie.has_nonstandard_attr("HttpOnly"),
            }
            for cookie in materialized
        ],
    }

    header_path.write_text(f"{header}\n", encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    header_path.chmod(0o600)
    json_path.chmod(0o600)


def login(url: str, username: str, password: str, timeout: float = 20) -> tuple[str, list[Cookie]]:
    """Submit the login form and return its final destination and session cookies."""
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    try:
        with opener.open(build_login_request(url, username, password), timeout=timeout) as response:
            final_url = response.geturl()
    except HTTPError as error:
        raise LoginError(f"Login endpoint returned HTTP {error.code}") from error
    except URLError as error:
        raise LoginError(f"Could not reach login endpoint: {error.reason}") from error
    return final_url, list(jar)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Log in to Dianplus DevOps and save reusable session cookies."
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output-dir", type=Path, default=Path("."))
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
    try:
        final_url, cookies = login(
            login_url,
            values["DIANPLUS_USERNAME"],
            values["DIANPLUS_PASSWORD"],
        )
        if not is_authenticated(final_url, login_url, cookies):
            raise LoginError("Login did not produce a session cookie or leave the login page")
        write_outputs(cookies, args.output_dir)
    except (LoginError, OSError, ValueError) as error:
        print(f"Login failed: {error}", file=sys.stderr)
        return 1

    print(f"Session cookies saved to {args.output_dir / 'session.cookies.txt'}")
    print(f"Session metadata saved to {args.output_dir / 'session.cookies.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
