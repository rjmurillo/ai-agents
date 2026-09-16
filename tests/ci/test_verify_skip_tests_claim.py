"""Tests for scripts/ci/verify_skip_tests_claim.py.

Covers the independent recomputation `skip-tests` (pytest.yml) runs before
reporting the required `Run Python Tests` context green. ADR-101 names the
fail-open: `test-result` and `skip-tests` both publish that context name and
are mutually exclusive on `python-changed`, so a wrong-false `python-changed`
lets `skip-tests` report success for a change no test ever ran. These tests
pin every branch of `verify()` and `main()` per `.agents/governance/TESTING-RIGOR.md`
(positive, negative, edge) and `.claude/rules/ci-scripts.md` MUST 10 (the
nonzero exit proven at the CLI, not only on a helper's return value).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci import verify_skip_tests_claim as mod

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASE = "a" * 40
_HEAD = "b" * 40
_ALL_ZERO = "0" * 40


def _no_matches(monkeypatch: pytest.MonkeyPatch, changed: list[str]) -> None:
    monkeypatch.setattr(mod, "changed_from_git", lambda *_: changed)


# --- positive -----------------------------------------------------------


def test_no_policy_match_returns_zero_with_examined_count(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # assets/logo.svg is the policy test suite's own unrelated fixture
    # (tests/test_selection/test_path_policy.py). README.md and any *.md/*.txt
    # would be the wrong choice here: the policy names them explicitly.
    _no_matches(monkeypatch, ["assets/logo.svg", "assets/photo.png"])
    rc = mod.main(["--repo-root", str(_REPO_ROOT), "--base", _BASE, "--head", _HEAD])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK: 0 policy matches in 2 changed files" in out


# --- negative -------------------------------------------------------------


def test_changed_python_file_returns_one_and_names_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _no_matches(monkeypatch, ["scripts/ci/some_module.py"])
    rc = mod.main(["--repo-root", str(_REPO_ROOT), "--base", _BASE, "--head", _HEAD])
    out = capsys.readouterr().out
    assert rc == 1
    assert "scripts/ci/some_module.py" in out
    assert "python-changed was reported false" in out


@pytest.mark.parametrize(
    "rel",
    ["lefthook.yml", ".claude/rules/example.md"],
)
def test_non_python_policy_match_returns_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], rel: str
) -> None:
    _no_matches(monkeypatch, [rel])
    rc = mod.main(["--repo-root", str(_REPO_ROOT), "--base", _BASE, "--head", _HEAD])
    out = capsys.readouterr().out
    assert rc == 1
    assert rel in out


# --- edge -------------------------------------------------------------


def test_undiffable_range_returns_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(mod, "changed_from_git", lambda *_: None)
    rc = mod.main(["--repo-root", str(_REPO_ROOT), "--base", _BASE, "--head", _HEAD])
    out = capsys.readouterr().out
    assert rc == 1
    assert "could not diff" in out
    assert _BASE in out
    assert _HEAD in out


def test_all_zero_base_sha_returns_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # No changed_from_git patch: the all-zero check must short-circuit before
    # any diff is attempted.
    def _fail_if_called(*_args: object) -> list[str] | None:
        raise AssertionError("changed_from_git must not be called for an all-zero base")

    monkeypatch.setattr(mod, "changed_from_git", _fail_if_called)
    rc = mod.main(["--repo-root", str(_REPO_ROOT), "--base", _ALL_ZERO, "--head", _HEAD])
    out = capsys.readouterr().out
    assert rc == 1
    assert "cannot verify" in out
    assert _ALL_ZERO in out


@pytest.mark.parametrize(
    ("base", "head"),
    [("", _HEAD), (_BASE, "")],
)
def test_empty_base_or_head_returns_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    base: str,
    head: str,
) -> None:
    def _fail_if_called(*_args: object) -> list[str] | None:
        raise AssertionError("changed_from_git must not be called with a missing SHA")

    monkeypatch.setattr(mod, "changed_from_git", _fail_if_called)
    rc = mod.main(["--repo-root", str(_REPO_ROOT), "--base", base, "--head", head])
    out = capsys.readouterr().out
    assert rc == 1
    assert "cannot verify" in out


def test_empty_changed_list_returns_zero_with_zero_count(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _no_matches(monkeypatch, [])
    rc = mod.main(["--repo-root", str(_REPO_ROOT), "--base", _BASE, "--head", _HEAD])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK: 0 policy matches in 0 changed files" in out


def test_more_than_twenty_matches_are_truncated(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    changed = [f"scripts/ci/module_{i}.py" for i in range(25)]
    _no_matches(monkeypatch, changed)
    rc = mod.main(["--repo-root", str(_REPO_ROOT), "--base", _BASE, "--head", _HEAD])
    out = capsys.readouterr().out
    assert rc == 1
    assert "module_0.py" in out
    assert "module_19.py" in out
    assert "module_20.py" not in out
    assert "and 5 more" in out


def test_config_error_from_unreadable_policy_returns_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _no_matches(monkeypatch, ["unrelated/some_module.py"])
    monkeypatch.setattr(
        mod.path_policy,
        "load_patterns",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("no python filter")),
    )
    rc = mod.main(["--repo-root", str(_REPO_ROOT), "--base", _BASE, "--head", _HEAD])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no python filter" in err


# --- unit-level coverage of verify() directly ------------------------------


def test_verify_matches_glob_pairs(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_matches(monkeypatch, ["lefthook.yml"])
    code, message = mod.verify(_REPO_ROOT, _BASE, _HEAD)
    assert code == 1
    assert "lefthook.yml" in message
