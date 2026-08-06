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

import ci_runner_base as base
import run_install_parity_ci as runner

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
    """origin/<base_ref> is preferred when it resolves AND is not == HEAD.

    Regression test for #2254: incremental feature-branch pushes must diff
    against origin/main (the base branch), not PUSH_BEFORE_SHA (the previous
    branch head, which may already contain the plugin bump).
    """
    monkeypatch.setenv("PUSH_BEFORE_SHA", "abc1234")  # would shadow if used

    def fake_run(cmd, *, check=False, timeout=60):
        if cmd[:3] == ["git", "rev-parse", "--verify"] and cmd[-1] == "origin/main":
            return 0, "deadbeef\n", ""
        if cmd[:3] == ["git", "rev-parse", "--verify"] and cmd[-1] == "HEAD":
            return 0, "feedface\n", ""  # HEAD differs from origin/main
        if cmd[:3] == ["git", "rev-parse", "--verify"] and cmd[-1] == "abc1234":
            return 0, "abc1234\n", ""  # PUSH_BEFORE_SHA also resolves
        return 1, "", ""

    monkeypatch.setattr(base, "run", fake_run)
    assert base.resolve_base("main") == "origin/main"


def test_resolve_base_falls_back_to_push_before_sha_when_origin_equals_head(
    monkeypatch,
) -> None:
    """When origin/<base_ref> == HEAD (push directly to base branch), the
    diff against origin yields nothing, so fall back to PUSH_BEFORE_SHA to
    cover every commit in the push.
    """
    monkeypatch.setenv("PUSH_BEFORE_SHA", "abc1234")

    def fake_run(cmd, *, check=False, timeout=60):
        if cmd[:3] == ["git", "rev-parse", "--verify"] and cmd[-1] == "origin/main":
            return 0, "samesha\n", ""
        if cmd[:3] == ["git", "rev-parse", "--verify"] and cmd[-1] == "HEAD":
            return 0, "samesha\n", ""  # HEAD == origin/main
        if cmd[:3] == ["git", "rev-parse", "--verify"] and cmd[-1] == "abc1234":
            return 0, "abc1234\n", ""
        return 1, "", ""

    monkeypatch.setattr(base, "run", fake_run)
    assert base.resolve_base("main") == "abc1234"


def test_resolve_base_falls_back_to_push_before_sha_when_origin_unresolvable(
    monkeypatch,
) -> None:
    """When origin/<base_ref> does not resolve at all (network failure,
    base ref deleted), still honour PUSH_BEFORE_SHA before HEAD^.
    """
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

    monkeypatch.setattr(
        runner, "fetch_base_ref", lambda base_ref: (fetch_calls.append(base_ref), 0)[1]
    )
    monkeypatch.setattr(runner, "resolve_base", lambda base_ref: f"origin/{base_ref}")
    monkeypatch.setattr(runner, "run", lambda cmd, *, check=False, timeout=60: (0, "OK\n", ""))

    rc = runner.main()
    assert rc == 2
    # The malformed ref must not have reached the fetch at all.
    assert fetch_calls == []
    err = capsys.readouterr().err
    assert "failed branch-name allowlist" in err
    assert "refusing to fall back" in err


# --- fetch_base_ref shallow handling (issue #4680) -----------------------


def _record_calls(monkeypatch: pytest.MonkeyPatch, shallow_answers: list[str]):
    """Fake `run` that answers the shallow probe from a queue.

    Dispatch is on argv rather than call order, because `fetch_base_ref`
    branches and a positional list would silently hand a later call the answer
    meant for an earlier one.
    """
    calls: list[list[str]] = []
    answers = list(shallow_answers)

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        if argv[:2] == ["git", "rev-parse"]:
            return 0, (answers.pop(0) if answers else "false"), ""
        return 0, "", ""

    monkeypatch.setattr(base, "run", fake_run)
    return calls


def test_fetch_base_ref_does_not_graft_a_complete_clone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #4680: a depth-limited fetch writes .git/shallow even here.

    Both workflows that reach this helper check out at `fetch-depth: 0`, so
    `--depth=200` bought nothing and its only effect was the graft. The
    discriminating assertion is the absence of any depth flag, not the presence
    of a fetch.
    """
    calls = _record_calls(monkeypatch, ["false"])

    base.fetch_base_ref("main")

    fetches = [c for c in calls if c[:2] == ["git", "fetch"]]
    assert len(fetches) == 1, calls
    assert not any("--depth" in token for token in fetches[0]), fetches[0]
    assert "--unshallow" not in fetches[0], fetches[0]


def test_fetch_base_ref_still_repairs_a_genuinely_shallow_clone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shallow path must keep working, or CI checkouts at depth 1 break."""
    calls = _record_calls(monkeypatch, ["true", "false"])

    base.fetch_base_ref("main")

    fetches = [c for c in calls if c[:2] == ["git", "fetch"]]
    assert any("--unshallow" in token for c in fetches for token in c), calls
    # One round trip, not two: --unshallow fetches the ref as well as
    # completing history, so a preceding --depth fetch bought nothing.
    assert len(fetches) == 1, calls


def test_fetch_base_ref_reports_config_error_when_the_repair_did_not_take(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The defect this replaces: a swallowed `--unshallow` failure.

    `--unshallow` tolerated failure and the comment claimed the following
    `rev-parse` was authoritative. It is not: `rev-parse` resolves a base ref
    perfectly well on a grafted clone, so every range measured afterwards was
    wrong rather than absent.

    Asserted as a return code rather than an exception because neither caller
    wraps this in a try block, so a raise would exit 1 with a traceback where
    the exit-code contract calls for 2, and where both callers already return 2
    for their other config failures.
    """
    _record_calls(monkeypatch, ["true", "true"])

    assert base.fetch_base_ref("main") == 2
    assert "still shallow" in capsys.readouterr().err


def test_both_runners_propagate_the_shallow_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove the wiring, not only the guard.

    `fetch_base_ref` returning 2 proves the helper detected the graft. It
    proves nothing about whether either runner acts on it, and an unwired
    caller was the exact shape of the original defect. Driving each `main()`
    and asserting on the integer it returns is what closes that.
    """
    monkeypatch.setenv("PR_BASE_REF", "main")
    monkeypatch.setattr(base, "fetch_base_ref", lambda _ref: 2)
    monkeypatch.setattr(runner, "fetch_base_ref", lambda _ref: 2)

    assert runner.main() == 2


def test_fetch_base_ref_does_not_graft_when_the_probe_cannot_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unanswerable probe must not take the branch that writes the graft.

    `_is_shallow_repository` returns None when git could not answer, which a
    30 second `rev-parse` timeout is enough to cause. Branching on `is False`
    sent that case into `--depth=200`, grafting a clone that may well be
    complete, which is the exact defect this function exists to remove.
    """
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        if argv[:2] == ["git", "rev-parse"]:
            return 2, "", "TimeoutExpired: git rev-parse"
        return 0, "", ""

    monkeypatch.setattr(base, "run", fake_run)

    assert base.fetch_base_ref("main") == 0
    fetches = [c for c in calls if c[:2] == ["git", "fetch"]]
    assert len(fetches) == 1, calls
    assert not any("--depth" in token for token in fetches[0]), fetches[0]
