"""Tests for scripts/validation/check_pr_bypass_label.py (Issue #2456).

Covers the decision logic over the gh result: label present, label absent,
no PR for the branch, and gh failure modes. I/O (the gh subprocess) is the only
mocked boundary; the decision function itself is exercised directly.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "validation"
    / "check_pr_bypass_label.py"
)
_spec = importlib.util.spec_from_file_location("check_pr_bypass_label", _MODULE_PATH)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _proc(returncode: int, stdout: str = "", stderr: str = ""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_returns_present_when_label_on_pr(monkeypatch):
    payload = (
        '{"number": 2337, "labels": [{"name": "bug"}, '
        '{"name": "commit-limit-bypass"}], "state": "OPEN"}'
    )
    monkeypatch.setattr(mod, "_run_gh_pr_view", lambda branch: _proc(0, payload))

    code, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert code == mod.EXIT_PRESENT
    assert "present on PR #2337" in status


def test_returns_absent_when_label_missing(monkeypatch):
    payload = '{"number": 2337, "labels": [{"name": "bug"}], "state": "OPEN"}'
    monkeypatch.setattr(mod, "_run_gh_pr_view", lambda branch: _proc(0, payload))

    code, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert code == mod.EXIT_ABSENT
    assert "no commit-limit-bypass label (PR #2337)" in status


def test_returns_absent_when_labels_field_null(monkeypatch):
    # A present-but-null labels field means "no labels", not an error.
    payload = '{"number": 5, "labels": null, "state": "OPEN"}'
    monkeypatch.setattr(mod, "_run_gh_pr_view", lambda branch: _proc(0, payload))

    code, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert code == mod.EXIT_ABSENT
    assert "PR #5" in status


def test_returns_absent_when_no_pr_for_branch(monkeypatch):
    monkeypatch.setattr(
        mod,
        "_run_gh_pr_view",
        lambda branch: _proc(1, "", "no pull requests found for branch"),
    )

    code, status = mod.check_bypass_label("commit-limit-bypass", "feat/foo")

    assert code == mod.EXIT_ABSENT
    assert "no open PR for feat/foo" in status


def test_returns_external_when_gh_fails(monkeypatch):
    monkeypatch.setattr(
        mod,
        "_run_gh_pr_view",
        lambda branch: _proc(1, "", "could not connect to api.github.com"),
    )

    code, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert code == mod.EXIT_EXTERNAL
    assert "failed" in status


def test_returns_external_when_gh_missing(monkeypatch):
    def _raise(branch):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(mod, "_run_gh_pr_view", _raise)

    code, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert code == mod.EXIT_EXTERNAL
    assert "gh CLI not found" in status


def test_returns_external_on_timeout(monkeypatch):
    def _raise(branch):
        raise subprocess.TimeoutExpired(cmd="gh", timeout=15)

    monkeypatch.setattr(mod, "_run_gh_pr_view", _raise)

    code, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert code == mod.EXIT_EXTERNAL
    assert "timed out" in status


def test_returns_external_on_bad_json(monkeypatch):
    monkeypatch.setattr(mod, "_run_gh_pr_view", lambda branch: _proc(0, "not json"))

    code, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert code == mod.EXIT_EXTERNAL
    assert "unparseable" in status


def test_custom_label_respected(monkeypatch):
    payload = '{"number": 9, "labels": [{"name": "override-me"}], "state": "OPEN"}'
    monkeypatch.setattr(mod, "_run_gh_pr_view", lambda branch: _proc(0, payload))

    code, _ = mod.check_bypass_label("override-me", None)

    assert code == mod.EXIT_PRESENT


def test_main_prints_status_and_returns_code(monkeypatch, capsys):
    payload = '{"number": 1, "labels": [{"name": "commit-limit-bypass"}], "state": "OPEN"}'
    monkeypatch.setattr(mod, "_run_gh_pr_view", lambda branch: _proc(0, payload))

    rc = mod.main([])

    captured = capsys.readouterr()
    assert rc == mod.EXIT_PRESENT
    assert "present on PR #1" in captured.out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
