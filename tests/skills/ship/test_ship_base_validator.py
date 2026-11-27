"""The paths check runs only the base branch's validator, from a private copy.

Owner ruling, 2026-11-25, security finding 1, option A: ship_pr.py never runs
scripts/validation/pr_description.py from the branch being shipped.
"""

from __future__ import annotations

import json
import os

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import (
    TITLE,
    VALIDATOR_BRANCH_EDIT,
    VALIDATOR_PASS,
    run_pr,
    values,
)


def _check(scripts, capsys, body):
    return run_pr(scripts, capsys, "check", "--title", TITLE, "--body-file", str(body))


def _commit_branch_validator(repo):
    validator = repo / "scripts" / "validation" / "pr_description.py"
    validator.parent.mkdir(parents=True, exist_ok=True)
    validator.write_text(VALIDATOR_BRANCH_EDIT, encoding="utf-8")
    git(repo, "add", "scripts")
    git(repo, "commit", "-q", "-m", "feat: edit the validator")


def test_branch_edit_of_the_validator_never_runs(
    owner, base_validator, scripts, capsys, tmp_path, monkeypatch
):
    repo, body = owner
    base_validator(repo, VALIDATOR_PASS)
    _commit_branch_validator(repo)
    sentinel = tmp_path / "branch-ran.txt"
    monkeypatch.setenv("SHIP_BRANCH_SENTINEL", str(sentinel))
    code, lines = _check(scripts, capsys, body)
    assert code == 0
    assert "paths=PASS" in values(lines, "CHECK")
    assert not sentinel.exists(), "the branch copy of the validator ran"


def test_missing_base_validator_reports_not_run(owner, scripts, capsys, tmp_path, monkeypatch):
    repo, body = owner
    _commit_branch_validator(repo)
    sentinel = tmp_path / "branch-ran.txt"
    monkeypatch.setenv("SHIP_BRANCH_SENTINEL", str(sentinel))
    code, lines = _check(scripts, capsys, body)
    assert code == 0
    assert values(lines, "CHECK")[-1].startswith("paths=NOT-RUN origin/main has no path validator")
    assert lines[-1] == "NEXT: compare-paths-by-hand"
    assert not sentinel.exists()


def test_base_copy_runs_private_isolated_and_against_the_checkout(
    owner, base_validator, scripts, capsys, tmp_path, monkeypatch
):
    repo, body = owner
    base_validator(repo, VALIDATOR_PASS)
    probe = tmp_path / "probe.json"
    monkeypatch.setenv("SHIP_VALIDATOR_PROBE", str(probe))
    code, _lines = _check(scripts, capsys, body)
    seen = json.loads(probe.read_text(encoding="utf-8"))
    assert code == 0
    assert seen["isolated"] == 1
    assert seen["file_mode"] == "0o600"
    assert seen["dir_mode"] == "0o700"
    assert os.path.realpath(seen["cwd"]) == os.path.realpath(repo)
    assert not seen["file"].startswith(str(repo))
    assert seen["argv"][0] == "--body-file"
    assert seen["argv"][-2:] == ["--base", "refs/remotes/origin/main"]
    assert not os.path.exists(seen["file"]), "the private copy outlived the check"


@pytest.mark.parametrize(
    "source",
    [
        "raise RuntimeError('boom')\n",
        "raise SystemExit(2)\n",
        "raise SystemExit(5)\n",
    ],
)
def test_base_validator_that_cannot_run_is_not_a_pass(
    owner, base_validator, scripts, capsys, source
):
    repo, body = owner
    base_validator(repo, source, closure=False)
    code, lines = _check(scripts, capsys, body)
    assert code == 0
    assert values(lines, "CHECK")[-1].startswith(
        "paths=NOT-RUN the origin/main validator could not run"
    )
    assert lines[-1] == "NEXT: compare-paths-by-hand"


def test_copy_failure_reports_not_run(owner, base_validator, scripts, capsys, monkeypatch):
    repo, body = owner
    base_validator(repo, VALIDATOR_PASS)
    common = scripts[0]
    real_git = common.git

    def failing_show(args, cwd=None, timeout=60, **kw):
        if args[:1] == ["show"]:
            return common.Completed(128, "", "fatal")
        return real_git(args, cwd=cwd, timeout=timeout, **kw)

    monkeypatch.setattr(common, "git", failing_show)
    code, lines = _check(scripts, capsys, body)
    assert code == 0
    assert values(lines, "CHECK")[-1].startswith("paths=NOT-RUN could not copy the validator")


@pytest.mark.parametrize("bad", ["../escape.py", "/abs/path.py", "other/x.py"])
def test_paths_outside_scripts_are_never_copied(
    owner, base_validator, scripts, capsys, monkeypatch, bad
):
    repo, body = owner
    base_validator(repo, VALIDATOR_PASS)
    checks = scripts[3].checks_mod
    monkeypatch.setattr(checks, "BASE_CLOSURE_FILES", (bad,))
    monkeypatch.setattr(checks, "_base_files", lambda ctx, ref: [checks.BASE_VALIDATOR, bad])
    code, lines = _check(scripts, capsys, body)
    assert code == 0
    assert values(lines, "CHECK")[-1].startswith("paths=NOT-RUN could not copy the validator")


def test_write_failure_reports_not_run(owner, base_validator, scripts, capsys, monkeypatch):
    repo, body = owner
    base_validator(repo, VALIDATOR_PASS)
    checks = scripts[3].checks_mod

    real_open = checks.os.open

    def refuse_py(path, *args, **kwargs):
        if str(path).endswith(".py"):
            raise OSError("no")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(checks.os, "open", refuse_py)
    code, lines = _check(scripts, capsys, body)
    assert code == 0
    assert values(lines, "CHECK")[-1].startswith("paths=NOT-RUN could not copy the validator")
