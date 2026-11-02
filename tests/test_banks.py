"""Smoke tests: the shipped banks pass their own checkers (which execute every solution and quiz snippet)."""
import glob
import json
import os

from tools import check_bank, check_qcm, check_theory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_exercise_bank_is_valid(capsys):
    assert check_bank.main([]) == 0
    summary = capsys.readouterr().out.strip().splitlines()[-1]
    assert summary.endswith("0 invalid")
    assert int(summary.split()[0]) >= 30


def test_quiz_bank_is_valid(capsys):
    assert check_qcm.main([]) == 0
    summary = capsys.readouterr().out.strip().splitlines()[-1]
    assert summary.endswith("0 invalid")
    assert int(summary.split()[0]) >= 100


def test_theory_bank_is_valid(capsys):
    assert check_theory.main([]) == 0
    summary = capsys.readouterr().out.strip().splitlines()[-1]
    assert "0 invalid, 0 without a grid" in summary
    assert int(summary.split()[0]) >= 200


def test_bank_files_are_json_lists_with_unique_ids():
    seen: dict[str, str] = {}
    for path in glob.glob(os.path.join(ROOT, "bank", "*", "*.json")):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        items = data if isinstance(data, list) else data.get("items") or data.get("exercises") or [data]
        for item in items:
            assert item["id"] not in seen, f"{item['id']} in both {seen[item['id']]} and {path}"
            seen[item["id"]] = path
    assert len(seen) >= 350
