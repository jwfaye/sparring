"""Tests of backend/paths.py: shipped directories in a clone or in the installed package, the data directory."""
import os
import pathlib

import pytest

from backend import paths

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_clone_uses_the_directories_next_to_server_py():
    assert paths.is_clone()
    assert paths.resource_dir("app") == os.path.join(ROOT, "app")
    assert paths.resource_dir("bank") == os.path.join(ROOT, "bank")
    assert os.path.isfile(os.path.join(paths.resource_dir("app"), "index.html"))


def test_installed_layout_uses_the_data_package(monkeypatch, tmp_path):
    site = tmp_path / "site-packages"
    (site / "sparring_data" / "app").mkdir(parents=True)
    (site / "sparring_data" / "bank").mkdir()
    monkeypatch.setattr(paths, "ROOT", str(site))
    monkeypatch.setattr(paths.importlib.resources, "files", lambda name: pathlib.Path(site / name))
    assert not paths.is_clone()
    assert paths.resource_dir("app") == str(site / "sparring_data" / "app")
    assert paths.resource_dir("bank") == str(site / "sparring_data" / "bank")


def test_packaged_dir_missing_subdirectory_falls_through_to_error(monkeypatch, tmp_path):
    site = tmp_path / "site-packages"
    (site / "sparring_data").mkdir(parents=True)
    monkeypatch.setattr(paths, "ROOT", str(site))
    monkeypatch.setattr(paths.importlib.resources, "files", lambda name: pathlib.Path(site / name))
    assert paths._packaged_dir("app") is None
    with pytest.raises(FileNotFoundError, match="app/ not found"):
        paths.resource_dir("app")


def test_packaged_dir_ignores_a_resource_that_is_not_a_directory_on_disk(monkeypatch, tmp_path):
    class Zipped:
        def joinpath(self, name):
            return object()

    monkeypatch.setattr(paths, "ROOT", str(tmp_path))
    monkeypatch.setattr(paths.importlib.resources, "files", lambda name: Zipped())
    assert paths._packaged_dir("app") is None


def test_missing_everywhere_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "ROOT", str(tmp_path))

    def absent(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(paths.importlib.resources, "files", absent)
    with pytest.raises(FileNotFoundError, match="app/ not found"):
        paths.resource_dir("app")


def test_data_dir_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.DATA_ENV_VAR, str(tmp_path))
    assert paths.data_dir() == str(tmp_path)


def test_data_dir_in_a_clone_is_data_at_the_root(monkeypatch):
    monkeypatch.delenv(paths.DATA_ENV_VAR, raising=False)
    assert paths.data_dir() == os.path.join(ROOT, "data")


def test_data_dir_when_installed_is_the_user_data_directory(monkeypatch, tmp_path):
    monkeypatch.delenv(paths.DATA_ENV_VAR, raising=False)
    monkeypatch.setattr(paths, "ROOT", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    assert paths.data_dir() == os.path.join(str(tmp_path / "share"), "sparring")


def test_user_data_home_without_xdg_is_under_home(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(paths.sys, "platform", "linux")
    assert paths.user_data_home() == os.path.join(str(tmp_path), ".local", "share")


def test_user_data_home_on_macos_and_windows(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    assert paths.user_data_home() == os.path.join(str(tmp_path), "Library", "Application Support")
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert paths.user_data_home() == str(tmp_path / "Local")
