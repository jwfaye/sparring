"""Browser end-to-end tests: a real `server.py` on a free port, driven by Playwright in headless Chromium.

Every module here carries the `e2e` marker, excluded by default (`addopts` in pyproject.toml), and skips when the
`e2e` extra is not installed. Run the suite with `python -m pytest -q -m e2e tests/e2e`.

The page is opened with `?profile=e2e`: progress lives in a separate localStorage namespace and interview answers
in `data/theory/e2e/`, which is removed when the session ends, so the user's own data is never touched. The server
reads a temporary settings file (`SPARRING_CONFIG`) with `grader.backend = offline` and the free port, so the user's
own `config.json` is never read and no quota is spent whatever it contains; as defense in depth the server also gets
no ANTHROPIC_* or CLAUDE_* variable. The interview test asserts the offline status before submitting.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROFILE = "e2e"
PROFILE_DATA = os.path.join(ROOT, "data", "theory", PROFILE)
START_TIMEOUT = 30
PYODIDE_TIMEOUT = 120_000
DEFAULT_TIMEOUT = 15_000


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(url: str, proc: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server.py exited with code {proc.returncode} before answering /api/health")
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.1)
    raise RuntimeError(f"server.py did not answer /api/health within {START_TIMEOUT} s")


@pytest.fixture(scope="session")
def base_url(tmp_path_factory):
    """Start server.py on a free port (overrides the pytest-base-url fixture used by the `page` context)."""
    shutil.rmtree(PROFILE_DATA, ignore_errors=True)
    port = free_port()
    settings = tmp_path_factory.mktemp("settings") / "config.json"
    settings.write_text(
        json.dumps({"server": {"host": "127.0.0.1", "port": port}, "grader": {"backend": "offline"}}), encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_"))}
    env["SPARRING_CONFIG"] = str(settings)
    env["SPARRING_LOG_LEVEL"] = "WARNING"
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env)
    url = f"http://127.0.0.1:{port}"
    try:
        wait_for_health(url, proc)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        shutil.rmtree(PROFILE_DATA, ignore_errors=True)


@pytest.fixture(scope="session")
def profile() -> str:
    return PROFILE


@pytest.fixture(scope="session")
def pyodide_timeout() -> int:
    """Milliseconds to wait for `Python ready`: the CDN fetch is slow on a cold cache."""
    return PYODIDE_TIMEOUT


@pytest.fixture(scope="session")
def app_url() -> str:
    """The page with the test profile: a separate storage namespace, nothing of the user's own progress."""
    return f"/?profile={PROFILE}"


@pytest.fixture(scope="session", autouse=True)
def expect_timeout():
    """A generous default for every Playwright expectation: CI runners are slower than a laptop."""
    from playwright.sync_api import expect

    expect.set_options(timeout=DEFAULT_TIMEOUT)


class PageLog:
    """Console errors and failed requests recorded on a page, from before navigation."""

    def __init__(self, page) -> None:
        self.console_errors: list[str] = []
        self.failed_requests: list[str] = []
        page.on("console", lambda msg: self.console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: self.console_errors.append(str(err)))
        page.on("requestfailed", lambda req: self.failed_requests.append(f"{req.url}: {req.failure}"))
        page.on(
            "response",
            lambda resp: self.failed_requests.append(f"{resp.url}: HTTP {resp.status}") if resp.status >= 400 else None,
        )


@pytest.fixture(scope="session")
def ready_page(browser, base_url, app_url):
    """One page per session where Pyodide has finished loading: the CDN fetch is the slowest step of the suite."""
    from playwright.sync_api import expect

    context = browser.new_context(base_url=base_url)
    page = context.new_page()
    page.log = PageLog(page)
    page.goto(app_url)
    expect(page.locator("#py-status")).to_have_text("Python ready", timeout=PYODIDE_TIMEOUT)
    yield page
    context.close()
