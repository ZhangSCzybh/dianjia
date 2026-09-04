# Dianplus Cookie Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build a standard-library CLI that exchanges Dianplus credentials for reusable authenticated session cookies.

**Architecture:** `login.py` contains environment parsing, request construction, response validation, and output serialization in separately testable functions. The CLI composes those functions around `urllib.request` and `http.cookiejar.CookieJar`; secret configuration and session outputs remain outside version control.

**Tech Stack:** Python 3 standard library (`argparse`, `http.cookiejar`, `json`, `urllib`).

**Spec:** `docs/superpowers/specs/2026-09-02-dianplus-cookie-login-design.md`

## Global Constraints

- Use no third-party runtime dependencies.
- Read `DIANPLUS_USERNAME`, `DIANPLUS_PASSWORD`, and optional `DIANPLUS_LOGIN_URL` from `.env`.
- Never log a password or cookie value.
- Persist cookie values only in Git-ignored session output files.

---

### Task 1: Define and Test Protocol Helpers

**Files:**
- Create: `tests/test_login.py`
- Create: `login.py`

**Interfaces:**
- Produces: `load_dotenv(path: Path) -> dict[str, str]`, `build_login_request(url: str, username: str, password: str) -> Request`, `is_authenticated(final_url: str, login_url: str, cookies: Iterable[Cookie]) -> bool`, `cookie_header(cookies: Iterable[Cookie]) -> str`.

- [x] **Step 1: Write the failing tests**

```python
def test_build_login_request_urlencodes_expected_fields():
    request = build_login_request("https://example.test/login", "alice", "p&=")
    assert request.method == "POST"
    assert request.data == b"username=alice&password=p%26%3D"

def test_cookie_header_keeps_cookie_names_and_values():
    assert cookie_header([make_cookie("JSESSIONID", "abc")]) == "JSESSIONID=abc"
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_login -v`

Expected: FAIL because `login` does not exist.

- [x] **Step 3: Implement minimal helper functions**

```python
def build_login_request(url, username, password):
    data = urlencode({"username": username, "password": password}).encode()
    return Request(url, data=data, method="POST")

def cookie_header(cookies):
    return "; ".join(f"{cookie.name}={cookie.value}" for cookie in cookies)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_login -v`

Expected: PASS.

### Task 2: Add Login Execution and Safe Artifacts

**Files:**
- Modify: `login.py`
- Modify: `tests/test_login.py`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `README.md`

**Interfaces:**
- Consumes: helper functions from Task 1.
- Produces: `login(url: str, username: str, password: str, timeout: float = 20) -> tuple[str, list[Cookie]]`, `write_outputs(cookies: Iterable[Cookie], output_dir: Path) -> None`, and `main(argv: Sequence[str] | None = None) -> int`.

- [x] **Step 1: Write the failing tests**

```python
def test_is_authenticated_rejects_login_page_even_with_cookie():
    assert not is_authenticated("https://example.test/login", "https://example.test/login", [make_cookie("JSESSIONID", "abc")])

def test_write_outputs_creates_reusable_cookie_header(tmp_path):
    write_outputs([make_cookie("JSESSIONID", "abc")], tmp_path)
    assert (tmp_path / "session.cookies.txt").read_text() == "JSESSIONID=abc\\n"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_login -v`

Expected: FAIL because response validation and artifact writing are missing.

- [x] **Step 3: Implement the minimal CLI**

```python
parser = argparse.ArgumentParser()
parser.add_argument("--env-file", type=Path, default=Path(".env"))
parser.add_argument("--output-dir", type=Path, default=Path("."))
```

Open the POST request through a `CookieJar`, require a non-login final URL and a `JSESSIONID`, then write both output files. Add examples and ignore `.env` and `session.cookies.*`.

- [x] **Step 4: Run the complete suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: PASS.

### Task 3: Verify Against the Live Endpoint

**Files:**
- Modify: `.env`

**Interfaces:**
- Consumes: `python3 login.py` and the supplied local credentials.
- Produces: current session artifacts without displaying their values.

- [x] **Step 1: Create local secret configuration**

```dotenv
DIANPLUS_USERNAME=<provided username>
DIANPLUS_PASSWORD=<provided password>
DIANPLUS_LOGIN_URL=https://devops.dianplus.cn/login
```

- [x] **Step 2: Run the CLI**

Run: `python3 login.py`

Expected: a successful status message naming the output paths, but no password or cookie values.

- [x] **Step 3: Verify output structure without revealing values**

Run: `awk -F= '{print $1 "=<redacted>"}' session.cookies.txt`

Expected: `JSESSIONID=<redacted>` and `CURRENT_ROLERELATION_ID=<redacted>`.
