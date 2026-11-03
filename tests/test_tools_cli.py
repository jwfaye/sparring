"""Argument parsing of the bank import tools (tools/add_exercises.py, tools/add_qcm.py, tools/add_theory_grids.py)."""
import json
import sys

import pytest

from tools import add_exercises, add_qcm, add_theory_grids


def write_draft(tmp_path, name, items):
    path = tmp_path / name
    path.write_text(json.dumps(items), encoding="utf-8")
    return str(path)


class TestAddExercises:
    def test_without_a_draft_argument_argparse_exits_with_2(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["add_exercises"])
        with pytest.raises(SystemExit) as exc:
            add_exercises.main()
        assert exc.value.code == 2

    def test_dry_run_reports_a_rejected_draft_and_writes_nothing(self, tmp_path, monkeypatch, capsys):
        draft = write_draft(tmp_path, "draft.json", [{"id": "draft-001", "title": "Not an exercise"}])
        out = tmp_path / "out.json"
        monkeypatch.setattr(sys, "argv", ["add_exercises", draft, "--out", str(out), "--dry-run"])
        assert add_exercises.main() == 1
        printed = capsys.readouterr().out
        assert "KO  draft-001" in printed and "0 accepted, 1 rejected" in printed
        assert not out.exists()


class TestAddQcm:
    def test_without_a_draft_argument_argparse_exits_with_2(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["add_qcm"])
        with pytest.raises(SystemExit) as exc:
            add_qcm.main()
        assert exc.value.code == 2

    def test_dry_run_reports_a_rejected_draft_and_writes_nothing(self, tmp_path, monkeypatch, capsys):
        draft = write_draft(tmp_path, "draft.json", [{"id": "qcm-draft-001", "question": "Incomplete?"}])
        out = tmp_path / "out.json"
        monkeypatch.setattr(sys, "argv", ["add_qcm", draft, "--out", str(out), "--dry-run"])
        assert add_qcm.main() == 1
        printed = capsys.readouterr().out
        assert "KO  qcm-draft-001" in printed and "0 accepted, 1 rejected" in printed
        assert not out.exists()


class TestAddTheoryGrids:
    def test_without_a_draft_argument_prints_the_usage_and_returns_2(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["add_theory_grids"])
        assert add_theory_grids.main() == 2
        assert "Usage: python -m tools.add_theory_grids" in capsys.readouterr().out
