"""Tests for scripts/validation/run_plugin_version_bump_ci.py.

Covers the env-var allowlist (CWE-78 defense in depth), the base-ref
resolution priority order, the missing-validator config-error path, and
forwarding of the validator exit code. The fetch and validator invocation are
exercised via mocks; the runner is small enough that the unit tests cover
every branch.

Mirrors tests/validation/test_run_install_parity_ci.py for the sibling runner.
The shared helpers live in ``ci_runner_base``; the runner imports them into its
namespace, so the ``main()`` tests monkeypatch the names bound on the runner.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

import run_plugin_version_bump_ci as runner  # noqa: E402


def _stub_happy_path(monkeypatch) -> list[str]:
    """Wire fetch/resolve/run to a clean pass; return the fetch-call log."""
    fetch_calls: list[str] = []
    monkeypatch.setattr(runner, "fetch_base_ref", lambda ref: fetch_calls.append(ref))
    monkeypatch.setattr(runner, "resolve_base", lambda ref: f"origin/{ref}")
    monkeypatch.setattr(
        runner, "run", lambda *a, **k: (0, "plugin-version-bump: OK\n", "")
    )
    return fetch_calls


# --- main: branch allowlist ----------------------------------------------


def test_main_rejects_malformed_pr_base_ref(
    monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An attacker-controlled PR_BASE_REF fails closed, never falls back."""
    monkeypatch.setenv("PR_BASE_REF", "main; rm -rf /")

    fetch_calls = _stub_happy_path(monkeypatch)
    rc = runner.main()

    assert rc == 2
    assert fetch_calls == []  # malformed ref never reaches the fetch
    err = capsys.readouterr().err
    assert "failed branch-name allowlist" in err
    assert "refusing to fall back" in err


def test_main_defaults_to_main_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("PR_BASE_REF", raising=False)
    fetch_calls = _stub_happy_path(monkeypatch)

    rc = runner.main()

    assert rc == 0
    assert fetch_calls == ["main"]


# --- main: base resolution failure ---------------------------------------


def test_main_returns_2_when_base_unresolvable(
    monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PR_BASE_REF", "main")
    monkeypatch.setattr(runner, "fetch_base_ref", lambda ref: None)
    monkeypatch.setattr(runner, "resolve_base", lambda ref: None)

    rc = runner.main()

    assert rc == 2
    assert "could not resolve a diff base" in capsys.readouterr().err


# --- main: missing validator ---------------------------------------------


def test_main_returns_2_when_validator_missing(
    monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PR_BASE_REF", "main")
    monkeypatch.setattr(runner, "fetch_base_ref", lambda ref: None)
    monkeypatch.setattr(runner, "resolve_base", lambda ref: "origin/main")
    # Point REPO_ROOT at an empty dir so the validator file is absent.
    monkeypatch.setattr(runner, "REPO_ROOT", REPO_ROOT / "no" / "such" / "tree")

    rc = runner.main()

    assert rc == 2
    assert "validator not found" in capsys.readouterr().err


# --- main: exit-code forwarding ------------------------------------------


def test_main_forwards_validator_violation_exit(monkeypatch, capsys) -> None:
    monkeypatch.setenv("PR_BASE_REF", "main")
    monkeypatch.setattr(runner, "fetch_base_ref", lambda ref: None)
    monkeypatch.setattr(runner, "resolve_base", lambda ref: "origin/main")
    monkeypatch.setattr(
        runner, "run", lambda *a, **k: (1, "plugin-version-bump: NOT BUMPED\n", "")
    )

    rc = runner.main()

    assert rc == 1
    assert "NOT BUMPED" in capsys.readouterr().out


def test_main_forwards_validator_config_error_exit(monkeypatch, capsys) -> None:
    monkeypatch.setenv("PR_BASE_REF", "main")
    monkeypatch.setattr(runner, "fetch_base_ref", lambda ref: None)
    monkeypatch.setattr(runner, "resolve_base", lambda ref: "origin/main")
    monkeypatch.setattr(
        runner, "run", lambda *a, **k: (2, "", "plugin-version-bump: CONFIG ERROR\n")
    )

    rc = runner.main()

    assert rc == 2
    assert "CONFIG ERROR" in capsys.readouterr().err


def test_main_passes_resolved_base_to_validator(monkeypatch) -> None:
    """The runner forwards the resolved base ref to the validator's --base."""
    monkeypatch.setenv("PR_BASE_REF", "main")
    monkeypatch.setattr(runner, "fetch_base_ref", lambda ref: None)
    monkeypatch.setattr(runner, "resolve_base", lambda ref: "deadbeef")

    seen: dict[str, list[str]] = {}

    def fake_run(cmd, **k):
        seen["cmd"] = cmd
        return 0, "OK\n", ""

    monkeypatch.setattr(runner, "run", fake_run)
    rc = runner.main()

    assert rc == 0
    assert "--base" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--base") + 1] == "deadbeef"
