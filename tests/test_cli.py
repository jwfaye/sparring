"""Command line of server.py (the `sparring` entry point): positional port, --host, --port, --version."""
import importlib.metadata
import logging

import pytest

import server


def test_no_argument_leaves_host_and_port_to_the_settings():
    args = server.parse_args([])
    assert args.port is None and args.host is None


def test_positional_port_is_kept_for_compatibility():
    assert server.parse_args(["9000"]).port == 9000


def test_port_option():
    assert server.parse_args(["--port", "9000"]).port == 9000


def test_positional_and_option_may_agree():
    assert server.parse_args(["9000", "--port", "9000"]).port == 9000


def test_positional_and_option_must_not_disagree(capsys):
    with pytest.raises(SystemExit) as info:
        server.parse_args(["9000", "--port", "9001"])
    assert info.value.code == 2
    assert "give the port once" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [["0"], ["65536"], ["--port", "-1"], ["abc"], ["--port", "8.5"]])
def test_invalid_port_is_refused(argv, capsys):
    with pytest.raises(SystemExit) as info:
        server.parse_args(argv)
    assert info.value.code == 2
    assert "port" in capsys.readouterr().err


def test_host_option():
    assert server.parse_args(["--host", "localhost"]).host == "localhost"


def test_version_prints_the_package_version(capsys):
    with pytest.raises(SystemExit) as info:
        server.parse_args(["--version"])
    assert info.value.code == 0
    assert capsys.readouterr().out.strip().endswith(" " + server.version())


def test_version_comes_from_the_package_metadata():
    assert server.version() == importlib.metadata.version("sparring")


def test_version_is_unknown_without_metadata(monkeypatch):
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    assert server.version() == "unknown"


def test_help_lists_every_option(capsys):
    with pytest.raises(SystemExit) as info:
        server.parse_args(["--help"])
    assert info.value.code == 0
    out = capsys.readouterr().out
    assert "--host" in out and "--port" in out and "--version" in out and "port" in out


@pytest.fixture
def fake_server(monkeypatch):
    """A ThreadingHTTPServer stand-in that records the bind address and stops at once; bind_host is restored."""
    seen = {}

    class FakeServer:
        def __init__(self, address, handler):
            seen["address"] = address

        def serve_forever(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(server.http.server, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(server, "bind_host", server.bind_host)
    return seen


def test_main_uses_the_arguments_over_the_settings(fake_server):
    server.main(["--host", "127.0.0.2", "--port", "9123"])
    assert fake_server["address"] == ("127.0.0.2", 9123)
    assert server.bind_host == "127.0.0.2"


def test_main_falls_back_to_the_settings(fake_server):
    server.main([])
    srv = server.config.section("server")
    assert fake_server["address"] == (srv["host"], srv["port"])


def test_main_logs_settings_and_data_directory(fake_server, monkeypatch, tmp_path, caplog):
    absent = tmp_path / "absent.json"
    monkeypatch.setattr(server.config, "PATH", str(absent))
    monkeypatch.setattr(server.store, "DATA_DIR", str(tmp_path / "data"))
    with caplog.at_level(logging.INFO, logger="sparring"):
        server.main([])
    messages = [record.getMessage() for record in caplog.records]
    assert f"Settings: {absent} (not found, using defaults)" in messages
    assert f"Data directory: {tmp_path / 'data'}" in messages


def test_main_logs_an_existing_settings_file_without_a_caveat(fake_server, monkeypatch, tmp_path, caplog):
    present = tmp_path / "config.json"
    present.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(server.config, "PATH", str(present))
    with caplog.at_level(logging.INFO, logger="sparring"):
        server.main([])
    assert f"Settings: {present}" in [record.getMessage() for record in caplog.records]


def test_main_warns_when_the_local_settings_file_changes_claude_bin(fake_server, monkeypatch, tmp_path, caplog):
    monkeypatch.delenv(server.config.ENV_VAR, raising=False)
    monkeypatch.setattr(server.config, "PATH", str(tmp_path / "config.json"))
    monkeypatch.setitem(server.config.CONFIG["grader"], "claude_bin", "/somewhere/claude")
    with caplog.at_level(logging.WARNING, logger="sparring"):
        server.main([])
    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert any("grader.claude_bin = '/somewhere/claude'" in message for message in warnings)


def test_main_does_not_warn_for_a_named_or_per_user_settings_file(fake_server, monkeypatch, tmp_path, caplog):
    monkeypatch.setitem(server.config.CONFIG["grader"], "claude_bin", "/somewhere/claude")
    monkeypatch.setenv(server.config.ENV_VAR, str(tmp_path / "config.json"))
    monkeypatch.setattr(server.config, "PATH", str(tmp_path / "config.json"))
    with caplog.at_level(logging.WARNING, logger="sparring"):
        server.main([])
    monkeypatch.delenv(server.config.ENV_VAR)
    monkeypatch.setattr(server.config, "PATH", server.config.user_config_path())
    with caplog.at_level(logging.WARNING, logger="sparring"):
        server.main([])
    assert not any("grader.claude_bin" in record.getMessage() for record in caplog.records)
