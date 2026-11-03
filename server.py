#!/usr/bin/env python3
"""Local server of the training app.

Usage: sparring [port] [--host HOST] [--port PORT] [--version]   (installed with pip or pipx)
       python server.py [port] [--host HOST] [--port PORT]      (from a clone)
The host and the port default to the settings file, section "server" (see backend/config.py for the lookup order).

Shipped files and user data (see backend/paths.py): app/ and bank/ are read next to this file in a clone, else from
the installed sparring_data package; answers go to data/ in a clone, else to the per-user data directory
($XDG_DATA_HOME/sparring or ~/.local/share/sparring), SPARRING_DATA_DIR overriding both.

- Serves the static files of app/ (with the cross-origin isolation headers Pyodide's interrupt buffer needs)
- GET /api/exercises  -> merged exercise bank (every bank/exercises/*.json)
- GET /api/qcm        -> merged quiz bank (every bank/qcm/*.json)
- GET /api/theory/questions, /status, /history?profile=  -> interview questions, grader status, answer history
- POST /api/theory/answer {qid, answer, duration, profile, mode} -> saves the answer (and grades it when a grader is available)
- POST /api/theory/grade {id, profile, force?}  -> grades a pending answer (force: re-grade an already graded one)
- POST /api/theory/delete {id, profile} -> deletes an answer
- GET /api/health     -> {"ok": true}

The API has no authentication: it is meant for a loopback address only. Requests whose Host is not local, or that
carry a foreign Origin, or POSTs that are not application/json, are rejected (see SECURITY.md).
"""
import argparse
import glob
import http.server
import importlib.metadata
import ipaddress
import json
import logging
import os
import re
import urllib.parse
from typing import Any

from backend import config, grader, paths, store

log = logging.getLogger("sparring")

APP_DIR = paths.resource_dir("app")
BANK_DIR = paths.resource_dir("bank")

MAX_BODY = 1_000_000
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}
WILDCARD_HOSTS = {"0.0.0.0", "::", ""}
CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net 'unsafe-eval' 'wasm-unsafe-eval'; "
    "style-src 'self' https://cdnjs.cloudflare.com https://fonts.googleapis.com 'unsafe-inline'; "
    "font-src https://fonts.gstatic.com; "
    "connect-src 'self' https://cdn.jsdelivr.net; "
    "img-src 'self' data:; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'; "
    "base-uri 'none'"
)
bind_host = "127.0.0.1"


def is_loopback(host: str) -> bool:
    if host in LOCAL_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def load_bank(kind: str) -> dict[str, Any]:
    """Merge every JSON file of bank/<kind>/.

    A file may hold a list of items, an object {"items": [...]}, or a single item.
    """
    items: list[dict[str, Any]] = []
    files: list[str] = []
    errors: list[str] = []
    for path in sorted(glob.glob(os.path.join(BANK_DIR, kind, "*.json"))):
        name = os.path.relpath(path, os.path.dirname(BANK_DIR))
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        if isinstance(data, list):
            batch = data
        elif isinstance(data, dict):
            batch = data.get("items") or data.get("exercises") or [data]
        else:
            errors.append(f"{name}: unexpected format")
            continue
        for item in batch:
            item.setdefault("_file", name)
        items.extend(batch)
        files.append(name)
    return {"items": items, "files": files, "errors": errors}


def theory_question(qid: str | None) -> dict[str, Any] | None:
    for q in load_bank("theory")["items"]:
        if q.get("id") == qid:
            return q
    return None


def valid_id(value: Any) -> str | None:
    return value if isinstance(value, str) and ID_RE.match(value) else None


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=APP_DIR, **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def _request_host(self) -> str:
        host = self.headers.get("Host") or ""
        if host.startswith("["):
            return host.split("]")[0] + "]"
        return host.rsplit(":", 1)[0] if ":" in host else host

    def _api_guard(self) -> str | None:
        """Reason to refuse an API request, or None: foreign Host, foreign Origin, non-JSON POST."""
        host = self._request_host()
        if not is_loopback(host) and (bind_host in WILDCARD_HOSTS or host != bind_host):
            return "Host is not local"
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host')}":
            return "cross-origin request refused"
        if self.command == "POST" and not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return "Content-Type must be application/json"
        return None

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        url = urllib.parse.urlparse(self.path)
        path, qs = url.path, urllib.parse.parse_qs(url.query)
        if not path.startswith("/api/"):
            return super().do_GET()
        refusal = self._api_guard()
        if refusal:
            return self._send_json({"error": refusal}, 403)
        profiles = qs.get("profile")
        profile = profiles[0] if profiles else None
        if path == "/api/exercises":
            return self._send_json(load_bank("exercises"))
        if path == "/api/qcm":
            return self._send_json(load_bank("qcm"))
        if path == "/api/theory/questions":
            return self._send_json(load_bank("theory"))
        if path == "/api/theory/status":
            return self._send_json(grader.status())
        if path == "/api/theory/history":
            return self._send_json({"items": store.list_answers(profile)})
        if path == "/api/health":
            return self._send_json({"ok": True})
        return self._send_json({"error": "unknown endpoint"}, 404)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        refusal = self._api_guard()
        if refusal:
            return self._send_json({"error": refusal}, 403)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._send_json({"error": "invalid Content-Length"}, 400)
        if length < 0 or length > MAX_BODY:
            return self._send_json({"error": "body too large"}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._send_json({"error": "invalid JSON"}, 400)
        if not isinstance(body, dict):
            return self._send_json({"error": "JSON object expected"}, 400)
        profile = body.get("profile") or None
        if profile is not None and valid_id(profile) is None:
            return self._send_json({"error": "invalid profile"}, 400)
        if path == "/api/theory/answer":
            qid = valid_id(body.get("qid"))
            q = theory_question(qid) if qid else None
            if q is None:
                return self._send_json({"error": "unknown question"}, 404)
            answer = str(body.get("answer") or "")
            online = grader.status()["available"] and body.get("mode") != "offline" and bool(q.get("key_points"))
            rec = store.add_answer(q["id"], answer, body.get("duration"), profile, "online" if online else "offline")
            if online:
                try:
                    rec = store.set_grade(rec["id"], grader.grade(q, answer), profile) or rec
                except grader.GraderError as exc:
                    return self._send_json({"record": rec, "error": str(exc)}, 502)
            return self._send_json({"record": rec, "offline": not online})
        if path == "/api/theory/grade":
            answer_id = valid_id(body.get("id"))
            pending = next((a for a in store.list_answers(profile) if a["id"] == answer_id), None)
            if pending is None:
                return self._send_json({"error": "unknown answer"}, 404)
            if pending.get("grade") and body.get("force") is not True:
                return self._send_json({"error": "already graded (send force: true to grade again)"}, 409)
            q = theory_question(pending["qid"])
            if q is None:
                return self._send_json({"error": "unknown question"}, 404)
            if not grader.status()["available"]:
                return self._send_json({"error": grader.status()["reason"]}, 503)
            try:
                rec = store.set_grade(pending["id"], grader.grade(q, pending["answer"]), profile) or pending
            except grader.GraderError as exc:
                return self._send_json({"error": str(exc)}, 502)
            return self._send_json({"record": rec})
        if path == "/api/theory/delete":
            answer_id = valid_id(body.get("id"))
            if answer_id is None:
                return self._send_json({"error": "invalid id"}, 400)
            return self._send_json({"ok": store.delete_answer(answer_id, profile)})
        return self._send_json({"error": "unknown endpoint"}, 404)

    def _send_json(self, obj: Any, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        """Keep the terminal readable: log only errors and API calls."""
        if (isinstance(code, int) and code >= 400) or "/api/" in self.path:
            log.info("%s %s -> %s", self.command, self.path, code)

    def log_error(self, fmt: str, *args: Any) -> None:
        log.warning("%s " + fmt, self.address_string(), *args)

    def log_message(self, fmt: str, *args: Any) -> None:
        log.debug("%s " + fmt, self.address_string(), *args)


def version() -> str:
    """The installed version of the sparring distribution, or "unknown" from a bare clone."""
    try:
        return importlib.metadata.version("sparring")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Command line: an optional positional port (kept for compatibility), --host, --port, --version.

    Args:
        argv: the arguments to parse; None means sys.argv[1:].

    Returns:
        A namespace with `host` (str or None) and `port` (int or None): None means the settings file decides.

    Raises:
        SystemExit: code 2 on a port outside 1-65535 or a positional port that disagrees with --port, code 0 after
            --help or --version, as argparse does.
    """
    parser = argparse.ArgumentParser(description="Sparring: local training server for technical tests and interviews.",
                                     epilog="The host and the port default to the settings file, section 'server'.")
    parser.add_argument("port_arg", metavar="port", nargs="?", type=int, help="port to listen on (same as --port)")
    parser.add_argument("--host", help="address to bind (keep a loopback address: the API has no authentication)")
    parser.add_argument("--port", type=int, help="port to listen on")
    parser.add_argument("--version", action="version", version=f"%(prog)s {version()}")
    args = parser.parse_args(argv)
    if args.port_arg is not None and args.port is not None and args.port_arg != args.port:
        parser.error("the positional port and --port disagree: give the port once")
    if args.port is None:
        args.port = args.port_arg
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error(f"port must be an integer from 1 to 65535 (got {args.port})")
    return args


def settings_from_cwd() -> bool:
    """True when the settings file was picked up from the current directory rather than named or per-user."""
    return not os.environ.get(config.ENV_VAR) and config.PATH != config.user_config_path()


def main(argv: list[str] | None = None) -> None:
    """Entry point of the `sparring` command and of `python server.py`.

    Args:
        argv: the arguments to parse; None means sys.argv[1:].
    """
    global bind_host
    args = parse_args(argv)
    logging.basicConfig(level=os.environ.get("SPARRING_LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    srv = config.section("server")
    port = int(srv["port"]) if args.port is None else args.port
    bind_host = args.host or str(srv["host"])
    server = http.server.ThreadingHTTPServer((bind_host, port), Handler)
    log.info("Settings: %s%s", config.PATH, "" if os.path.isfile(config.PATH) else " (not found, using defaults)")
    log.info("Data directory: %s", store.DATA_DIR)
    for err in config.ERRORS:
        log.warning(err)
    claude_bin = config.section("grader")["claude_bin"]
    if settings_from_cwd() and claude_bin != config.DEFAULTS["grader"]["claude_bin"]:
        log.warning("The settings file of the current directory sets grader.claude_bin = %r, a program the grader "
                    "runs: start sparring from a directory you trust, or name the file with SPARRING_CONFIG", claude_bin)
    if not is_loopback(bind_host):
        log.warning("Server bound to %s: the API has no authentication, anyone on the network can read and delete "
                    "your answers and spend your grading quota", bind_host)
    bank = load_bank("exercises")
    qcm, th = load_bank("qcm"), load_bank("theory")
    log.info("Bank: %d exercise(s), %d quiz question(s), %d interview question(s) (%d with a grid)",
             len(bank["items"]), len(qcm["items"]), len(th["items"]),
             sum(1 for q in th["items"] if q.get("key_points")))
    for err in bank["errors"] + qcm["errors"] + th["errors"]:
        log.warning(err)
    st = grader.status()
    if st["available"]:
        log.info("Online grading: available, %s", st["model"])
    else:
        log.warning("Online grading: offline, %s", st["reason"])
    log.info("Sparring, copyright (c) 2026 Joseph Faye, GNU AGPL v3 or later: see LICENSE")
    log.info("App: http://%s:%d/ (Ctrl+C to stop)", bind_host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()
