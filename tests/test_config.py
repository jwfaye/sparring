"""Validation of config.json: every invalid value keeps its default and is reported in the error list."""
import json
import os

import pytest

from backend import config


def load_from(tmp_path, content):
    path = tmp_path / "config.json"
    if content is not None:
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return config._load(str(path))


def test_defaults_when_file_is_missing(tmp_path):
    cfg, errors = load_from(tmp_path, None)
    assert cfg == config.DEFAULTS
    assert errors == []


def test_valid_file_overrides_defaults(tmp_path):
    user = {
        "server": {"host": "0.0.0.0", "port": 9000},
        "grader": {"backend": "api", "model": "claude-sonnet-5-5", "effort": "high",
                   "claude_bin": "/usr/local/bin/claude", "timeout_seconds": 60},
    }
    cfg, errors = load_from(tmp_path, user)
    assert errors == []
    assert cfg == user


def test_partial_file_keeps_other_defaults(tmp_path):
    cfg, errors = load_from(tmp_path, {"server": {"port": 9000}})
    assert errors == []
    assert cfg["server"] == {"host": "127.0.0.1", "port": 9000}
    assert cfg["grader"] == config.DEFAULTS["grader"]


def test_defaults_are_copied_not_shared(tmp_path):
    cfg, _ = load_from(tmp_path, {"server": {"port": 9000}})
    assert config.DEFAULTS["server"]["port"] == 8765
    assert cfg["server"] is not config.DEFAULTS["server"]


def test_invalid_json_uses_defaults(tmp_path):
    cfg, errors = load_from(tmp_path, "{not json")
    assert cfg == config.DEFAULTS
    assert len(errors) == 1
    assert "unreadable" in errors[0]


def test_non_object_json_uses_defaults(tmp_path):
    cfg, errors = load_from(tmp_path, "[1, 2]")
    assert cfg == config.DEFAULTS
    assert errors == ["config.json must contain a JSON object: using defaults"]


def test_unknown_section_is_reported(tmp_path):
    cfg, errors = load_from(tmp_path, {"ui": {"theme": "dark"}})
    assert cfg == config.DEFAULTS
    assert errors == ["config.json: unknown or invalid section 'ui'"]


def test_section_that_is_not_an_object_is_reported(tmp_path):
    cfg, errors = load_from(tmp_path, {"server": 8765})
    assert cfg == config.DEFAULTS
    assert errors == ["config.json: unknown or invalid section 'server'"]


def test_unknown_key_is_reported(tmp_path):
    cfg, errors = load_from(tmp_path, {"grader": {"temperature": 0.2}})
    assert cfg == config.DEFAULTS
    assert errors == ["config.json: unknown key 'grader.temperature'"]


@pytest.mark.parametrize("value", ["", "   ", 42, None, ["localhost"]])
def test_invalid_host_keeps_default(tmp_path, value):
    cfg, errors = load_from(tmp_path, {"server": {"host": value}})
    assert cfg["server"]["host"] == "127.0.0.1"
    assert len(errors) == 1
    assert "'server.host' must be a non-empty string" in errors[0]
    assert "using default '127.0.0.1'" in errors[0]


def test_host_is_stripped(tmp_path):
    cfg, errors = load_from(tmp_path, {"server": {"host": " localhost "}})
    assert errors == []
    assert cfg["server"]["host"] == "localhost"


@pytest.mark.parametrize("value", ["8765", 8765.0, True, False, 0, -1, 65536, None])
def test_invalid_port_keeps_default(tmp_path, value):
    cfg, errors = load_from(tmp_path, {"server": {"port": value}})
    assert cfg["server"]["port"] == 8765
    assert len(errors) == 1
    assert "'server.port' must be an integer from 1 to 65535" in errors[0]
    assert f"got {value!r}" in errors[0]


@pytest.mark.parametrize("value", [1, 65535])
def test_port_bounds_are_accepted(tmp_path, value):
    cfg, errors = load_from(tmp_path, {"server": {"port": value}})
    assert errors == []
    assert cfg["server"]["port"] == value


@pytest.mark.parametrize("value", ["ollama", "", 1, None, "claude_code"])
def test_invalid_backend_keeps_default(tmp_path, value):
    cfg, errors = load_from(tmp_path, {"grader": {"backend": value}})
    assert cfg["grader"]["backend"] == "auto"
    assert len(errors) == 1
    assert "'grader.backend' must be one of auto | api | claude-code | offline" in errors[0]


@pytest.mark.parametrize("value, expected", [("API", "api"), (" Claude-Code ", "claude-code"), ("Offline", "offline"), ("AUTO", "auto")])
def test_backend_is_case_insensitive_and_normalised(tmp_path, value, expected):
    cfg, errors = load_from(tmp_path, {"grader": {"backend": value}})
    assert errors == []
    assert cfg["grader"]["backend"] == expected


@pytest.mark.parametrize("value", ["", "  ", 5, None])
def test_invalid_model_keeps_default(tmp_path, value):
    cfg, errors = load_from(tmp_path, {"grader": {"model": value}})
    assert cfg["grader"]["model"] == "claude-opus-5-5"
    assert len(errors) == 1
    assert "'grader.model' must be a non-empty string" in errors[0]


@pytest.mark.parametrize("value", ["max", "", 2, None])
def test_invalid_effort_keeps_default(tmp_path, value):
    cfg, errors = load_from(tmp_path, {"grader": {"effort": value}})
    assert cfg["grader"]["effort"] == "medium"
    assert len(errors) == 1
    assert "'grader.effort' must be one of low | medium | high" in errors[0]


def test_effort_is_normalised(tmp_path):
    cfg, errors = load_from(tmp_path, {"grader": {"effort": "HIGH"}})
    assert errors == []
    assert cfg["grader"]["effort"] == "high"


@pytest.mark.parametrize("value", ["", 0, None, ["claude"]])
def test_invalid_claude_bin_keeps_default(tmp_path, value):
    cfg, errors = load_from(tmp_path, {"grader": {"claude_bin": value}})
    assert cfg["grader"]["claude_bin"] == "claude"
    assert len(errors) == 1
    assert "'grader.claude_bin' must be a non-empty string" in errors[0]


@pytest.mark.parametrize("value", [0, -5, "240", 240.0, True, None])
def test_invalid_timeout_keeps_default(tmp_path, value):
    cfg, errors = load_from(tmp_path, {"grader": {"timeout_seconds": value}})
    assert cfg["grader"]["timeout_seconds"] == 240
    assert len(errors) == 1
    assert "'grader.timeout_seconds' must be an integer >= 1" in errors[0]


def test_every_error_is_collected_and_valid_values_still_apply(tmp_path):
    user = {"server": {"host": "", "port": 9000}, "grader": {"backend": "nope", "effort": "low", "extra": 1}, "other": {}}
    cfg, errors = load_from(tmp_path, user)
    assert cfg["server"] == {"host": "127.0.0.1", "port": 9000}
    assert cfg["grader"]["backend"] == "auto"
    assert cfg["grader"]["effort"] == "low"
    assert len(errors) == 4
    assert any("'server.host'" in e for e in errors)
    assert any("'grader.backend'" in e for e in errors)
    assert any("unknown key 'grader.extra'" in e for e in errors)
    assert any("unknown or invalid section 'other'" in e for e in errors)


def test_env_override_loads_the_given_file(tmp_path, monkeypatch):
    path = tmp_path / "e2e.json"
    path.write_text(json.dumps({"server": {"port": 9000}, "grader": {"backend": "offline"}}), encoding="utf-8")
    monkeypatch.setenv(config.ENV_VAR, str(path))
    assert config.settings_path() == str(path)
    cfg, errors = config._load(config.settings_path())
    assert errors == []
    assert cfg["server"] == {"host": "127.0.0.1", "port": 9000}
    assert cfg["grader"]["backend"] == "offline"


def test_env_override_missing_file_keeps_defaults(tmp_path, monkeypatch):
    path = tmp_path / "absent.json"
    monkeypatch.setenv(config.ENV_VAR, str(path))
    assert config.settings_path() == str(path)
    cfg, errors = config._load(config.settings_path())
    assert cfg == config.DEFAULTS
    assert errors == []


def test_unset_env_uses_the_default_path(monkeypatch):
    monkeypatch.delenv(config.ENV_VAR, raising=False)
    assert config.settings_path() == os.path.join(config.ROOT, "config.json")
    assert config.settings_path() == config.DEFAULT_PATH


def test_empty_env_uses_the_default_path(monkeypatch):
    monkeypatch.setenv(config.ENV_VAR, "")
    assert config.settings_path() == config.DEFAULT_PATH


def test_shipped_config_is_valid():
    assert config.ERRORS == []
    assert config.section("server")["port"] == 8765
    assert config.section("grader")["backend"] in config.BACKENDS
