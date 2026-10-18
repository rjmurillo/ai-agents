"""The diff-scoped pre-PR gates fail closed without a fresh base ref (issue #6506).

Four gates in ``checks_ci_parity`` diff the branch against its base. With no
resolvable base they used to SKIP, and a failed refresh only warned and used the
stale ``origin/<branch>`` cache. Either way the gate judged the wrong file set
and could read clean while the matching required check failed. Both cases now
raise ``BaseRefUnavailable``, which the runner records as a FAIL.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_ci_parity
import checks_common
import pre_pr

_DIFF_GATES = (
    "validate_placeholder_identity",
    "validate_security_suppressions_diff",
    "validate_memory_placement",
    "validate_route_scenario_coverage",
)


def _stub_base(
    monkeypatch: pytest.MonkeyPatch, base: str | None, refresh: str | None = ""
) -> list[str]:
    """Stub base resolution and refresh; return the refs the refresh was asked about."""
    refreshed: list[str] = []

    def fake_refresh(base_ref: str, _root: Path) -> str | None:
        refreshed.append(base_ref)
        return refresh

    monkeypatch.setattr(checks_ci_parity, "_resolve_default_base_ref", lambda _root: base)
    monkeypatch.setattr(checks_ci_parity, "_refresh_remote_base", fake_refresh)
    return refreshed


def test_the_base_is_refreshed_before_the_gate_diffs(monkeypatch: pytest.MonkeyPatch) -> None:
    refreshed = _stub_base(monkeypatch, "origin/main")

    assert checks_ci_parity._require_base_ref(REPO_ROOT, "test gate") == "origin/main"
    assert refreshed == ["origin/main"]


@pytest.mark.parametrize("var", ["CI", "GITHUB_ACTIONS"])
def test_an_origin_base_that_needs_no_refresh_is_accepted_under_ci(
    monkeypatch: pytest.MonkeyPatch, var: str
) -> None:
    """``None`` from the refresh under CI means the runner already fetched the base."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv(var, "true")
    _stub_base(monkeypatch, "origin/main", refresh=None)

    assert checks_ci_parity._require_base_ref(REPO_ROOT, "test gate") == "origin/main"


_REMOTE_TIP = "a" * 40
_STALE_TIP = "b" * 40


def _stub_git(
    monkeypatch: pytest.MonkeyPatch,
    *,
    remote: tuple[int, str, str],
    local: tuple[int, str, str] = (0, _REMOTE_TIP + "\n", ""),
) -> list[list[str]]:
    """Stub ``git ls-remote`` and ``git rev-parse``; return the commands run."""
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> tuple[int, str, str]:
        commands.append(cmd)
        if "ls-remote" in cmd:
            return remote
        assert "rev-parse" in cmd, cmd
        return local

    monkeypatch.setattr(checks_ci_parity, "_run_subprocess", fake_run)
    return commands


def _outside_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


@pytest.mark.parametrize("base", ["origin/release/1.0", "origin/fix/6506-stacked"])
def test_a_slash_base_matching_the_remote_tip_is_accepted_outside_ci(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    """No refresh runs for a slash branch, so the cache is checked against ls-remote."""
    _outside_ci(monkeypatch)
    refreshed = _stub_base(monkeypatch, base, refresh=None)
    commands = _stub_git(monkeypatch, remote=(0, f"{_REMOTE_TIP}\trefs/heads/x\n", ""))

    assert checks_ci_parity._require_base_ref(REPO_ROOT, "test gate") == base
    assert refreshed == [base]
    branch = base.removeprefix("origin/")
    assert any(cmd[-3:] == ["ls-remote", "origin", f"refs/heads/{branch}"] for cmd in commands)


@pytest.mark.parametrize("base", ["origin/release/1.0", "origin/fix/6506-stacked"])
def test_a_slash_base_behind_the_remote_tip_fails_outside_ci(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    _outside_ci(monkeypatch)
    _stub_base(monkeypatch, base, refresh=None)
    _stub_git(
        monkeypatch, remote=(0, f"{_REMOTE_TIP}\trefs/heads/x\n", ""), local=(0, _STALE_TIP, "")
    )

    with pytest.raises(checks_ci_parity.BaseRefUnavailable, match=r"did not refresh") as caught:
        checks_ci_parity._require_base_ref(REPO_ROOT, "test gate")
    message = str(caught.value)
    assert "differs from remote" in message
    assert f"git fetch origin {base.removeprefix('origin/')}" in message
    assert "CI=true" not in message


@pytest.mark.parametrize(
    ("remote", "detail"),
    [
        ((128, "", "fatal: unable to access"), "unable to access"),
        ((1, "", ""), "git ls-remote exit 1"),
        ((0, "", ""), "git ls-remote exit 0"),
    ],
)
def test_an_unreadable_remote_tip_fails_outside_ci(
    monkeypatch: pytest.MonkeyPatch, remote: tuple[int, str, str], detail: str
) -> None:
    """Offline or a missing remote branch leaves the cache unverified, so it is not trusted."""
    _outside_ci(monkeypatch)
    _stub_base(monkeypatch, "origin/a/b", refresh=None)
    _stub_git(monkeypatch, remote=remote)

    with pytest.raises(checks_ci_parity.BaseRefUnavailable, match=detail) as caught:
        checks_ci_parity._require_base_ref(REPO_ROOT, "test gate")
    assert "CI=true" not in str(caught.value)


def test_a_slash_base_missing_locally_fails_outside_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    _outside_ci(monkeypatch)
    _stub_base(monkeypatch, "origin/a/b", refresh=None)
    _stub_git(
        monkeypatch, remote=(0, f"{_REMOTE_TIP}\trefs/heads/a/b\n", ""), local=(128, "", "bad")
    )

    with pytest.raises(checks_ci_parity.BaseRefUnavailable, match=r"local missing differs"):
        checks_ci_parity._require_base_ref(REPO_ROOT, "test gate")


def test_a_slash_base_through_the_real_refresh_is_checked_against_the_remote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end with the real helper: it returns None for ``origin/a/b`` without fetching."""
    _outside_ci(monkeypatch)
    monkeypatch.setattr(checks_ci_parity, "_resolve_default_base_ref", lambda _r: "origin/a/b")
    monkeypatch.setattr(
        checks_common,
        "_run_subprocess",
        lambda *_a, **_k: pytest.fail("a slash branch must not be fetched"),
    )
    _stub_git(
        monkeypatch, remote=(0, f"{_REMOTE_TIP}\trefs/heads/a/b\n", ""), local=(0, _STALE_TIP, "")
    )

    with pytest.raises(checks_ci_parity.BaseRefUnavailable, match=r"did not refresh origin/a/b"):
        checks_ci_parity._require_base_ref(REPO_ROOT, "test gate")


def test_a_local_base_fails_because_it_is_never_fetched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    refreshed = _stub_base(monkeypatch, "main", refresh=None)

    with pytest.raises(checks_ci_parity.BaseRefUnavailable, match=r"local ref that is never"):
        checks_ci_parity._require_base_ref(REPO_ROOT, "test gate")
    assert refreshed == []


@pytest.mark.parametrize("var", ["CI", "GITHUB_ACTIONS"])
def test_a_local_base_is_accepted_under_ci(monkeypatch: pytest.MonkeyPatch, var: str) -> None:
    """The CI runner fetched the base before the gates ran."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv(var, "true")
    _stub_base(monkeypatch, "main", refresh=None)

    assert checks_ci_parity._require_base_ref(REPO_ROOT, "test gate") == "main"


def _stub_symbolic_ref(
    monkeypatch: pytest.MonkeyPatch, exit_code: int, stdout: str, stderr: str = ""
) -> None:
    def fake_run(cmd: list[str], **_kwargs: object) -> tuple[int, str, str]:
        assert cmd[-3:] == ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"]
        return exit_code, stdout, stderr

    monkeypatch.setattr(checks_ci_parity, "_run_subprocess", fake_run)


def test_remote_head_is_resolved_to_a_branch_and_fetched(monkeypatch: pytest.MonkeyPatch) -> None:
    """No open PR: the symref must become origin/<branch> so the refresh fetches it."""
    refreshed = _stub_base(monkeypatch, "refs/remotes/origin/HEAD")
    _stub_symbolic_ref(monkeypatch, 0, "origin/main\n")

    assert checks_ci_parity._require_base_ref(REPO_ROOT, "test gate") == "origin/main"
    assert refreshed == ["origin/main"]


def test_a_failed_refresh_of_remote_head_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_base(monkeypatch, "refs/remotes/origin/HEAD", refresh="offline")
    _stub_symbolic_ref(monkeypatch, 0, "origin/main\n")

    with pytest.raises(checks_ci_parity.BaseRefUnavailable, match=r"could not refresh origin/main"):
        checks_ci_parity._require_base_ref(REPO_ROOT, "test gate")


@pytest.mark.parametrize(
    ("exit_code", "stdout", "stderr", "detail"),
    [
        (
            128,
            "",
            "fatal: ref refs/remotes/origin/HEAD is not a symbolic ref",
            "not a symbolic ref",
        ),
        (1, "", "", "git symbolic-ref exit 1"),
        (0, "upstream/main\n", "", "git symbolic-ref exit 0"),
    ],
)
def test_an_unresolvable_remote_head_fails(
    monkeypatch: pytest.MonkeyPatch, exit_code: int, stdout: str, stderr: str, detail: str
) -> None:
    refreshed = _stub_base(monkeypatch, "refs/remotes/origin/HEAD")
    _stub_symbolic_ref(monkeypatch, exit_code, stdout, stderr)

    with pytest.raises(checks_ci_parity.BaseRefUnavailable, match=detail):
        checks_ci_parity._require_base_ref(REPO_ROOT, "test gate")
    assert refreshed == []


def test_a_failed_refresh_fails_instead_of_using_the_stale_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_base(monkeypatch, "origin/main", refresh="offline")

    with pytest.raises(checks_ci_parity.BaseRefUnavailable, match=r"could not refresh origin/main"):
        checks_ci_parity._require_base_ref(REPO_ROOT, "test gate")


def test_an_unresolved_base_fails_instead_of_skipping(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_base(monkeypatch, None)

    with pytest.raises(checks_ci_parity.BaseRefUnavailable, match="none resolved"):
        checks_ci_parity._require_base_ref(REPO_ROOT, "test gate")


@pytest.mark.parametrize("gate", _DIFF_GATES)
def test_each_diff_gate_raises_without_a_base_and_never_runs_its_validator(
    monkeypatch: pytest.MonkeyPatch, gate: str
) -> None:
    _stub_base(monkeypatch, None)
    monkeypatch.setattr(
        checks_ci_parity,
        "_run_workflow_validator",
        lambda *_a, **_k: pytest.fail("the validator must not run without a base"),
    )

    with pytest.raises(checks_ci_parity.BaseRefUnavailable):
        getattr(checks_ci_parity, gate)(REPO_ROOT)


@pytest.mark.parametrize("gate", _DIFF_GATES)
def test_each_diff_gate_raises_when_the_refresh_fails(
    monkeypatch: pytest.MonkeyPatch, gate: str
) -> None:
    _stub_base(monkeypatch, "origin/main", refresh="offline")
    monkeypatch.setattr(
        checks_ci_parity,
        "_run_workflow_validator",
        lambda *_a, **_k: pytest.fail("the validator must not run on a stale base"),
    )

    with pytest.raises(checks_ci_parity.BaseRefUnavailable):
        getattr(checks_ci_parity, gate)(REPO_ROOT)


def test_the_runner_records_a_missing_base_as_a_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_base(monkeypatch, None)
    state = pre_pr.ValidationState()

    passed = pre_pr.run_validation(
        "Placeholder Identity",
        state,
        lambda: checks_ci_parity.validate_placeholder_identity(REPO_ROOT),
    )

    assert passed is False
    assert "none resolved" in capsys.readouterr().out
