"""Tests for scripts/validation/run_install_parity_ci.py.

Covers the env-var allowlist (CWE-78 defense in depth) and the
base-ref resolution priority order. The fetch and validator invocation
are exercised indirectly via mocks; the module is small enough that
the unit tests cover every branch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

import run_install_parity_ci as runner  # noqa: E402


# --- _validate_branch ----------------------------------------------------


def test_branch_accepts_simple_name() -> None:
    assert runner._validate_branch("main") == "main"
    assert runner._validate_branch("feat/install-parity-guard") == "feat/install-parity-guard"
    assert runner._validate_branch("fix-2094") == "fix-2094"
    assert runner._validate_branch("release/1.2.3") == "release/1.2.3"


def test_branch_rejects_empty_or_whitespace() -> None:
    assert runner._validate_branch("") is None
    assert runner._validate_branch("   ") is None


def test_branch_rejects_shell_metacharacters() -> None:
    """An attacker-controlled PR_BASE_REF must not smuggle shell or git metas."""
    for bad in [
        "main;rm -rf /",
        "main|cat",
        "main`whoami`",
        "main$(whoami)",
        "main && true",
        "main\nfoo",
        "main; echo pwned",
        "..main",
        "main..",
        "../etc/passwd",
        "-delete",
        "--upload-pack=evil",
    ]:
        assert runner._validate_branch(bad) is None, f"should reject: {bad!r}"


def test_branch_rejects_overly_long_names() -> None:
    """200 chars is the cap; anything longer is refused."""
    assert runner._validate_branch("a" * 201) is None
    assert runner._validate_branch("a" * 200) == "a" * 200


# --- _validate_sha -------------------------------------------------------


def test_sha_accepts_valid_short_and_long() -> None:
    assert runner._validate_sha("abc1234") == "abc1234"
    assert runner._validate_sha("0123456789abcdef0123456789abcdef01234567") == (
        "0123456789abcdef0123456789abcdef01234567"
    )


def test_sha_rejects_non_hex_and_short() -> None:
    assert runner._validate_sha("") is None
    assert runner._validate_sha("xyz") is None
    assert runner._validate_sha("abc") is None  # too short
    assert runner._validate_sha("a" * 41) is None  # too long
    assert runner._validate_sha("abc; rm -rf /") is None


def test_sha_rejects_all_zero_sentinel() -> None:
    """github.event.before is 0000... for the first push of a branch."""
    assert runner._validate_sha("0" * 40) is None
    assert runner._validate_sha("0" * 7) is None


# --- _resolve_base -------------------------------------------------------


def test_resolve_base_prefers_origin_when_resolvable(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, *, check=False, timeout=60):
        calls.append(cmd)
        # rev-parse for origin/main succeeds
        if cmd[:3] == ["git", "rev-parse", "--verify"]:
            ref = cmd[-1]
            if ref == "origin/main":
                return 0, "deadbeef\n", ""
        return 1, "", ""

    monkeypatch.setattr(runner, "_run", fake_run)
    assert runner._resolve_base("main") == "origin/main"


def test_resolve_base_falls_back_to_push_before_sha(monkeypatch) -> None:
    monkeypatch.setenv("PUSH_BEFORE_SHA", "abc1234")

    def fake_run(cmd, *, check=False, timeout=60):
        if cmd[:3] == ["git", "rev-parse", "--verify"]:
            ref = cmd[-1]
            if ref == "abc1234":
                return 0, "abc1234\n", ""
        return 1, "", ""

    monkeypatch.setattr(runner, "_run", fake_run)
    assert runner._resolve_base("main") == "abc1234"


def test_resolve_base_falls_back_to_head_caret(monkeypatch) -> None:
    monkeypatch.delenv("PUSH_BEFORE_SHA", raising=False)

    def fake_run(cmd, *, check=False, timeout=60):
        if cmd[:3] == ["git", "rev-parse", "--verify"]:
            ref = cmd[-1]
            if ref == "HEAD^":
                return 0, "abc\n", ""
        return 1, "", ""

    monkeypatch.setattr(runner, "_run", fake_run)
    assert runner._resolve_base("main") == "HEAD^"


def test_resolve_base_returns_none_when_nothing_resolves(monkeypatch) -> None:
    monkeypatch.delenv("PUSH_BEFORE_SHA", raising=False)

    def fake_run(cmd, *, check=False, timeout=60):
        return 1, "", ""

    monkeypatch.setattr(runner, "_run", fake_run)
    assert runner._resolve_base("main") is None


def test_resolve_base_ignores_malformed_push_before_sha(monkeypatch) -> None:
    """A garbage PUSH_BEFORE_SHA env value is silently dropped."""
    monkeypatch.setenv("PUSH_BEFORE_SHA", "abc; rm -rf /")

    def fake_run(cmd, *, check=False, timeout=60):
        if cmd[:3] == ["git", "rev-parse", "--verify"]:
            ref = cmd[-1]
            # Only HEAD^ resolves
            if ref == "HEAD^":
                return 0, "x\n", ""
        return 1, "", ""

    monkeypatch.setattr(runner, "_run", fake_run)
    # Should NOT call rev-parse on the malformed sha; falls to HEAD^.
    assert runner._resolve_base("main") == "HEAD^"


# --- main ----------------------------------------------------------------


def test_main_with_malformed_pr_base_ref_fails_closed(
    monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An attacker-controlled PR_BASE_REF must fail closed, not fall back to main."""
    monkeypatch.setenv("PR_BASE_REF", "main; rm -rf /")
    monkeypatch.setenv("PUSH_BEFORE_SHA", "")

    fetch_calls: list[str] = []

    def fake_fetch(base_ref: str) -> None:
        fetch_calls.append(base_ref)

    def fake_resolve(base_ref: str) -> str | None:
        return f"origin/{base_ref}"

    monkeypatch.setattr(runner, "_fetch_base_ref", fake_fetch)
    monkeypatch.setattr(runner, "_resolve_base", fake_resolve)

    # Stub the validator subprocess so we don't actually shell out.
    def fake_run(cmd, *, check=False, timeout=60):
        return 0, "install-parity: OK\n", ""

    monkeypatch.setattr(runner, "_run", fake_run)

    rc = runner.main()
    assert rc == 2
    # The malformed ref must not have reached the fetch at all.
    assert fetch_calls == []
    err = capsys.readouterr().err
    assert "failed branch-name allowlist" in err
    assert "refusing to fall back" in err
