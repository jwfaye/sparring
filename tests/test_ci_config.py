"""The CI workflow, the Dependabot configuration and the pre-commit configuration (SP-CI)."""
import os
import re

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "ci.yml")
DEPENDABOT = os.path.join(ROOT, ".github", "dependabot.yml")
PRE_COMMIT = os.path.join(ROOT, ".pre-commit-config.yaml")
PINNED_ACTION = re.compile(r"^\s*-?\s*uses: [\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class TestWorkflow:
    def test_every_action_is_pinned_to_a_commit_with_its_version_in_a_comment(self):
        with open(WORKFLOW, encoding="utf-8") as fh:
            uses = [line.rstrip("\n") for line in fh if "uses:" in line]
        assert uses, "the workflow uses no action"
        unpinned = [line for line in uses if not PINNED_ACTION.match(line)]
        assert unpinned == []

    def test_workflow_is_named_ci_with_a_concurrency_group_and_a_timeout_on_every_job(self):
        workflow = load(WORKFLOW)
        assert workflow["name"] == "CI"
        assert workflow["concurrency"]["group"]
        assert "cancel-in-progress" in workflow["concurrency"]
        assert set(workflow["jobs"]) == {"unit", "test", "js", "e2e"}
        for name, job in workflow["jobs"].items():
            assert isinstance(job.get("timeout-minutes"), int), name

    def test_unit_matrix_runs_both_python_versions_without_fail_fast(self):
        strategy = load(WORKFLOW)["jobs"]["unit"]["strategy"]
        assert strategy["fail-fast"] is False
        versions = [leg["python-version"] for leg in strategy["matrix"]["include"]]
        assert versions == ["3.12", "3.13"]

    def test_the_required_check_test_aggregates_the_matrix(self):
        test = load(WORKFLOW)["jobs"]["test"]
        assert test["needs"] == "unit"
        assert test["if"] == "always()"
        assert "needs.unit.result" in test["steps"][-1]["run"]

    def test_checkout_never_persists_credentials(self):
        for name, job in load(WORKFLOW)["jobs"].items():
            for step in job["steps"]:
                if str(step.get("uses", "")).startswith("actions/checkout@"):
                    assert step["with"]["persist-credentials"] is False, name


class TestDependabot:
    @staticmethod
    def entry(ecosystem):
        (entry,) = [e for e in load(DEPENDABOT)["updates"] if e["package-ecosystem"] == ecosystem]
        return entry

    def test_three_ecosystems_weekly_with_the_build_deps_prefix(self):
        updates = load(DEPENDABOT)["updates"]
        assert {entry["package-ecosystem"] for entry in updates} == {"pip", "npm", "github-actions"}
        for entry in updates:
            assert entry["directory"] == "/"
            assert entry["schedule"]["interval"] == "weekly"
            assert entry["commit-message"]["prefix"] == "build(deps)"

    def test_pip_groups_minor_and_patch_and_ignores_every_version_of_the_pyodide_pins(self):
        pip = self.entry("pip")
        (group,) = pip["groups"].values()
        assert sorted(group["update-types"]) == ["minor", "patch"]
        assert sorted(rule["dependency-name"] for rule in pip["ignore"]) == ["numpy", "pandas"]
        for rule in pip["ignore"]:
            assert set(rule) == {"dependency-name"}, rule

    def test_npm_moves_eslint_and_its_config_together_including_majors(self):
        groups = self.entry("npm")["groups"]
        assert set(groups) == {"javascript", "npm-minor-and-patch"}
        assert sorted(groups["javascript"]["patterns"]) == ["@eslint/*", "eslint*"]
        assert sorted(groups["javascript"]["update-types"]) == ["major", "minor", "patch"]
        assert sorted(groups["npm-minor-and-patch"]["exclude-patterns"]) == ["@eslint/*", "eslint*"]
        assert sorted(groups["npm-minor-and-patch"]["update-types"]) == ["minor", "patch"]

    def test_actions_arrive_in_one_group_including_majors(self):
        (group,) = self.entry("github-actions")["groups"].values()
        assert group["patterns"] == ["*"]
        assert sorted(group["update-types"]) == ["major", "minor", "patch"]


class TestPreCommit:
    def test_hook_repositories_are_pinned_to_commits_and_the_hooks_mirror_ci(self):
        repos = load(PRE_COMMIT)["repos"]
        hooks = {hook["id"] for repo in repos for hook in repo["hooks"]}
        assert hooks == {
            "end-of-file-fixer", "trailing-whitespace", "check-json", "check-yaml", "check-toml",
            "ruff-check", "mypy", "eslint",
        }
        for repo in repos:
            if repo["repo"] != "local":
                assert COMMIT_SHA.match(str(repo["rev"])), repo["repo"]
        local = {hook["id"]: hook for repo in repos if repo["repo"] == "local" for hook in repo["hooks"]}
        assert local["mypy"]["entry"] == ".venv-check/bin/python -m mypy ."
        assert local["eslint"]["entry"] == "npm run lint"
        assert all(hook["language"] == "system" for hook in local.values())
