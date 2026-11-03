"""Application settings: one JSON file merged over the defaults below.

The settings file is the first of:
1. the file named by SPARRING_CONFIG, when the variable is set and non-empty (the browser tests use it to run a server
   on a free port with the grader offline);
2. config.json in the current directory, when it exists (a clone run from its root, as before);
3. $XDG_CONFIG_HOME/sparring/config.json, or ~/.config/sparring/config.json, which is where an installed
   `sparring` command looks; a missing file means the defaults.
Only the API key (ANTHROPIC_API_KEY), SPARRING_CONFIG, SPARRING_DATA_DIR and SPARRING_LOG_LEVEL live in the
environment; every option lives in the file, never in the repository.

Every value is validated. An invalid value keeps its default and adds a message to ERRORS, so the server still
starts and logs the problem; unknown sections and keys are reported the same way.

Section "server":
- host: non-empty string (127.0.0.1 by default; never expose the server as is on a network)
- port: integer from 1 to 65535

Section "grader":
- backend: auto | api | claude-code | offline (case-insensitive)
- model: non-empty string, the grading model
- effort: low | medium | high
- claude_bin: non-empty string, path to the Claude Code CLI
- timeout_seconds: positive integer, maximum duration of one grading call through Claude Code
"""
import json
import os
from typing import Any, Callable

FILE_NAME = "config.json"
APP_NAME = "sparring"
ENV_VAR = "SPARRING_CONFIG"

Section = dict[str, Any]
Config = dict[str, Section]
Validator = Callable[[Any], tuple[Any, str | None]]

DEFAULTS: Config = {
    "server": {"host": "127.0.0.1", "port": 8765},
    "grader": {
        "backend": "auto",
        "model": "claude-opus-5-5",
        "effort": "medium",
        "claude_bin": "claude",
        "timeout_seconds": 240,
    },
}

BACKENDS = ("auto", "api", "claude-code", "offline")
EFFORTS = ("low", "medium", "high")


def _non_empty_string(value: Any) -> tuple[Any, str | None]:
    if isinstance(value, str) and value.strip():
        return value.strip(), None
    return None, "must be a non-empty string"


def _integer(low: int, high: int | None = None) -> Validator:
    bound = f"from {low} to {high}" if high is not None else f">= {low}"

    def check(value: Any) -> tuple[Any, str | None]:
        if isinstance(value, bool) or not isinstance(value, int):
            return None, f"must be an integer {bound}"
        if value < low or (high is not None and value > high):
            return None, f"must be an integer {bound}"
        return value, None

    return check


def _choice(allowed: tuple[str, ...]) -> Validator:
    options = " | ".join(allowed)

    def check(value: Any) -> tuple[Any, str | None]:
        if isinstance(value, str) and value.strip().lower() in allowed:
            return value.strip().lower(), None
        return None, f"must be one of {options}"

    return check


VALIDATORS: dict[str, dict[str, Validator]] = {
    "server": {"host": _non_empty_string, "port": _integer(1, 65535)},
    "grader": {
        "backend": _choice(BACKENDS),
        "model": _non_empty_string,
        "effort": _choice(EFFORTS),
        "claude_bin": _non_empty_string,
        "timeout_seconds": _integer(1),
    },
}


def user_config_path() -> str:
    """The per-user settings file: $XDG_CONFIG_HOME/sparring/config.json, else ~/.config/sparring/config.json."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME, FILE_NAME)


def settings_path() -> str:
    """The settings file: SPARRING_CONFIG when set and non-empty, else ./config.json when present, else the user's.

    `./config.json` is resolved against the current working directory on every call, so the answer depends on where
    the server is started from; the server logs it at startup.
    """
    override = os.environ.get(ENV_VAR)
    if override:
        return override
    local = os.path.abspath(FILE_NAME)
    if os.path.isfile(local):
        return local
    return user_config_path()


def _load(path: str) -> tuple[Config, list[str]]:
    cfg: Config = {name: dict(values) for name, values in DEFAULTS.items()}
    try:
        with open(path, encoding="utf-8") as fh:
            user = json.load(fh)
    except FileNotFoundError:
        return cfg, []
    except ValueError as exc:
        return cfg, [f"config.json is unreadable ({exc}): using defaults"]
    if not isinstance(user, dict):
        return cfg, ["config.json must contain a JSON object: using defaults"]
    errors: list[str] = []
    for name, values in user.items():
        if name not in cfg or not isinstance(values, dict):
            errors.append(f"config.json: unknown or invalid section '{name}'")
            continue
        for key, raw in values.items():
            validator = VALIDATORS[name].get(key)
            if validator is None:
                errors.append(f"config.json: unknown key '{name}.{key}'")
                continue
            value, problem = validator(raw)
            if problem is None:
                cfg[name][key] = value
            else:
                errors.append(f"config.json: '{name}.{key}' {problem} (got {raw!r}); using default {cfg[name][key]!r}")
    return cfg, errors


PATH: str = settings_path()
CONFIG: Config
ERRORS: list[str]
CONFIG, ERRORS = _load(PATH)


def section(name: str) -> Section:
    return CONFIG[name]
