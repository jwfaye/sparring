"""Shared fixtures. Run from the project root with `python -m pytest` (the root must be on sys.path)."""
import importlib.util
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_PATH = os.path.join(ROOT, "app", "py", "harness.py")


@pytest.fixture(scope="session")
def harness():
    """The browser harness, loaded from app/py/harness.py exactly as tools/check_bank.py does."""
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def store_dir(tmp_path, monkeypatch):
    """Point backend.store at a temporary directory."""
    from backend import store

    data = tmp_path / "theory"
    monkeypatch.setattr(store, "DATA", str(data))
    return data


@pytest.fixture
def grader_module(monkeypatch):
    """backend.grader with its availability cache cleared and the key removed from the environment."""
    from backend import grader

    monkeypatch.setattr(grader, "_cache", {"at": 0.0, "value": None})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    return grader
