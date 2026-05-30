"""Tests for run_install_parity_ci.py and its shared ci_runner_base helpers.

The base-ref allowlist and resolution logic were extracted into
``scripts/validation/ci_runner_base.py`` (shared with the plugin
version-bump CI runner). These tests target the helpers in their new home
and the thin ``run_install_parity_ci.main`` wrapper that composes them.

Covers the env-var allowlist (CWE-78 defense in depth) and the base-ref
resolution priority order. Fetch and validator invocation are mocked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

import ci_runner_base as base  # noqa: E402
import run_install_parity_ci as runner  # noqa: E402


# --- validate_branch -----------------------------------------------------


def test_branch_accepts_simple_name() -> None:
    assert base.validate_branch("main") == "main"
    assert base.validate_branch("feat/install-parity-guard") == "feat/install-parity-guard"
    assert base.validate_branch("fix-2094") == "fix-2094"
    assert base.validate_branch("release/1.2.3") == "release/1.2.3"


def test_branch_rejects_empty_or_whitespace() -> None:
    assert base.validate_branch("") is None
    assert base.validate_branch("   ") is None


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
        assert base.validate_branch(bad) is None, f"should reject: {bad!r}"


def test_branch_rejects_overly_long_names() -> None:
    """200 chars is the cap; anything longer is refused."""
    assert base.validate_branch("a" * 201) is None
    assert base.validate_branch("a" * 200) == "a" * 200


# --- validate_sha --------------------------------------------------------


def test_sha_accepts_valid_short_and_long() -> None:
    assert base.validate_sha("abc1234") == "abc1234"
    assert base.validate_sha("0123456789abcdef0123456789abcdef01234567") == (
        "0123456789abcdef0123456789abcdef01234567"
    )


def test_sha_rejects_non_hex_and_short() -> None:
    assert base.validate_sha("") is None
    assert base.validate_sha("xyz") is None
    assert base.validate_sha("abc") is None  # too short
    assert base.validate_sha("a" * 41) is None  # too long
    assert base.validate_sha("abc; rm -rf /") is None


def test_sha_rejects_all_zero_sentinel() -> None:
    """github.event.before is 0000... for the first push of a branch."""
    assert base.validate_sha("0" * 40) is None
    assert base.validate_sha("0" * 7) is None


# --- resolve_base --------------------------------------------------------
# resolve_base lives in ci_runner_base and calls ci_runner_base.run, so the
# subprocess seam is patched on `base`, not on the thin runner wrapper.


def test_resolve_base_prefers_origin_when_resolvable(monkeypatch) -> None:
    def fake_run(cmd, *, check=False, timeout=60):
        if cmd[:3] == ["git", "rev-parse", "--verify"] and cmd[-1] == "origin/main":
            return 0, "deadbeef\n", ""
        return 1, "", ""

    monkeypatch.setattr(base, "run", fake_run)
    assert base.resolve_base("main") == "origin/main"


def test_resolve_base_falls_back_to_push_before_sha(monkeypatch) -> None:
    monkeypatch.setenv("PUSH_BEFORE_SHA", "abc1234")

    def fake_run(cmd, *, check=False, timeout=60):
        if cmd[:3] == ["git", "rev-parse", "--verify"] and cmd[-1] == "abc1234":
            return 0, "abc1234\n", ""
        return 1, "", ""

    monkeypatch.setattr(base, "run", fake_run)
    assert base.resolve_base("main") == "abc1234"


def test_resolve_base_falls_back_to_head_caret(monkeypatch) -> None:
    monkeypatch.delenv("PUSH_BEFORE_SHA", raising=False)

    def fake_run(cmd, *, check=False, timeout=60):
        if cmd[:3] == ["git", "rev-parse", "--verify"] and cmd[-1] == "HEAD^":
            return 0, "abc\n", ""
        return 1, "", ""

    monkeypatch.setattr(base, "run", fake_run)
    assert base.resolve_base("main") == "HEAD^"


def test_resolve_base_returns_none_when_nothing_resolves(monkeypatch) -> None:
    monkeypatch.delenv("PUSH_BEFORE_SHA", raising=False)

    def fake_run(cmd, *, check=False, timeout=60):
        return 1, "", ""

    monkeypatch.setattr(base, "run", fake_run)
    assert base.resolve_base("main") is None


def test_resolve_base_ignores_malformed_push_before_sha(monkeypatch) -> None:
    """A garbage PUSH_BEFORE_SHA env value is silently dropped."""
    monkeypatch.setenv("PUSH_BEFORE_SHA", "abc; rm -rf /")

    def fake_run(cmd, *, check=False, timeout=60):
        if cmd[:3] == ["git", "rev-parse", "--verify"] and cmd[-1] == "HEAD^":
            return 0, "x\n", ""
        return 1, "", ""

    monkeypatch.setattr(base, "run", fake_run)
    # Should NOT call rev-parse on the malformed sha; falls to HEAD^.
    assert base.resolve_base("main") == "HEAD^"


# --- main ----------------------------------------------------------------
# main() composes the imported helpers; patching them on the runner module
# (where main looks them up) is the correct seam.


def test_main_with_malformed_pr_base_ref_fails_closed(
    monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An attacker-controlled PR_BASE_REF must fail closed, not fall back to main."""
    monkeypatch.setenv("PR_BASE_REF", "main; rm -rf /")
    monkeypatch.setenv("PUSH_BEFORE_SHA", "")

    fetch_calls: list[str] = []

    monkeypatch.setattr(runner, "fetch_base_ref", lambda base_ref: fetch_calls.append(base_ref))
    monkeypatch.setattr(runner, "resolve_base", lambda base_ref: f"origin/{base_ref}")
    monkeypatch.setattr(runner, "run", lambda cmd, *, check=False, timeout=60: (0, "OK\n", ""))

    rc = runner.main()
    assert rc == 2
    # The malformed ref must not have reached the fetch at all.
    assert fetch_calls == []
    err = capsys.readouterr().err
    assert "failed branch-name allowlist" in err
    assert "refusing to fall back" in err
