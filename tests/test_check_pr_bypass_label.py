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

_SCRIPT_PATH = _MODULE_PATH
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


def test_returns_absent_when_pr_is_not_open(monkeypatch):
    payload = (
        '{"number": 2337, "labels": [{"name": "commit-limit-bypass"}], '
        '"state": "CLOSED"}'
    )
    monkeypatch.setattr(mod, "_run_gh_pr_view", lambda branch: _proc(0, payload))

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


def test_policy_denial_is_named_and_reported_as_unverifiable(monkeypatch):
    """A 403 must read as a denial, not as a missing label, and not as success.

    Measured on a Claude Code cloud session, 2026-08-20: every gh REST call
    returned HTTP 403 "GitHub access is not enabled for this session" while the
    commit-limit-bypass label was in fact applied to the PR. The old message
    rendered that as "gh pr view failed (exit 1)", which reads as a transient
    error worth retrying.
    """
    monkeypatch.setattr(
        mod,
        "_run_gh_pr_view",
        lambda branch: _proc(
            1,
            "",
            "gh: GitHub access is not enabled for this session. (HTTP 403)",
        ),
    )

    code, status = mod.check_bypass_label("commit-limit-bypass", None)

    # The verdict is unchanged: EXIT_EXTERNAL, never EXIT_PRESENT, on a denial.
    # What a caller does with EXIT_EXTERNAL is the caller's decision (see
    # scripts/validation/git_hook_policy.py:_check_commit_limit, issue #5232),
    # not something this module asserts.
    assert code == mod.EXIT_EXTERNAL
    assert "denied by policy" in status
    assert "will not pass on retry" in status
    assert "cannot be verified locally" in status


def test_unauthenticated_gh_is_named(monkeypatch):
    monkeypatch.setattr(
        mod,
        "_run_gh_pr_view",
        lambda branch: _proc(1, "", "The token in GH_TOKEN is invalid. (HTTP 401)"),
    )

    code, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert code == mod.EXIT_EXTERNAL
    assert "not authenticated" in status


@pytest.mark.parametrize(
    "stderr",
    [
        # The realistic shape: GitHub answers an exhausted rate limit with 403,
        # not 429. An earlier version of the classifier tested for "403" first
        # and labelled this a policy denial that "will not pass on retry",
        # which is the opposite of the truth. The original test used a body
        # with no status code, so it passed while the real case was wrong.
        # Refs #5130 review (Cursor Bugbot).
        "gh: API rate limit exceeded for user ID 6811113. (HTTP 403)",
        "You have exceeded a secondary rate limit. (HTTP 403)",
        "API rate limit exceeded",
    ],
)
def test_rate_limit_is_named_and_not_called_a_policy_denial(monkeypatch, stderr):
    monkeypatch.setattr(mod, "_run_gh_pr_view", lambda branch: _proc(1, "", stderr))

    code, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert code == mod.EXIT_EXTERNAL
    assert "rate limit" in status
    assert "denied by policy" not in status
    assert "will not pass on retry" not in status


@pytest.mark.parametrize(
    "stderr",
    [
        "You have exceeded a secondary rate limit. (HTTP 403)",
        "gh: You have triggered an abuse detection mechanism. (HTTP 403)",
    ],
)
def test_secondary_limit_gets_back_off_advice_not_a_reset_window(monkeypatch, stderr):
    """A secondary limit must not be handed the primary remedy.

    Both bodies contain the words "rate limit", so an earlier revision matched
    them with one branch and told secondary-limit callers to wait for a window
    reset. There is no primary window to wait for, and retrying against a
    secondary limit keeps it engaged. Refs #5130 review (Copilot), #4690.
    """
    monkeypatch.setattr(mod, "_run_gh_pr_view", lambda branch: _proc(1, "", stderr))

    code, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert code == mod.EXIT_EXTERNAL
    assert "secondary rate limit" in status
    assert "back off" in status
    assert "bucket resets" not in status
    assert "denied by policy" not in status


def test_generic_rate_limit_body_does_not_claim_which_limiter(monkeypatch):
    """A generic body cannot prove primary exhaustion, so the message must not say so.

    An earlier revision of this file asserted the opposite: it required the
    words "bucket resets" on this input. Copilot pointed out on PR #5177 that a
    secondary limit can emit the same generic body while `x-ratelimit-remaining`
    is still above zero, which is exactly what `classify_gh_failure_response`
    uses headers to distinguish. This module has no headers, so it gives the
    advice that holds under either limiter rather than guessing.
    """
    monkeypatch.setattr(
        mod,
        "_run_gh_pr_view",
        lambda branch: _proc(1, "", "gh: API rate limit exceeded for user ID 1. (HTTP 403)"),
    )

    code, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert code == mod.EXIT_EXTERNAL
    assert "primary or secondary" in status
    assert "back off" in status
    assert "bucket resets" not in status
    assert "denied by policy" not in status


def test_message_does_not_advertise_a_throwaway_branch(monkeypatch):
    """The error must not teach a way around the ceiling it enforces.

    An earlier revision suggested landing the commits on another pushed branch
    so they stop counting as new. CONTRIBUTING.md:875 sanctions two routes and
    only two: split the PR, or have a human maintainer decide on the label.
    Refs #5130 review (Copilot).
    """
    monkeypatch.setattr(
        mod,
        "_run_gh_pr_view",
        lambda branch: _proc(1, "", "GitHub access is not enabled. (HTTP 403)"),
    )

    _, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert "another pushed branch" not in status
    assert "stop counting as new" not in status
    assert "Split the PR" in status
    assert "do not apply it yourself" in status


def test_policy_denial_still_wins_over_a_bare_403(monkeypatch):
    """A 403 with no rate-limit wording is still a denial, not a rate limit."""
    monkeypatch.setattr(
        mod,
        "_run_gh_pr_view",
        lambda branch: _proc(1, "", "gh: Forbidden (HTTP 403)"),
    )

    _, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert "denied by policy" in status
    assert "rate limit" not in status


def _external_paths():
    """Every way check_bypass_label can return EXIT_EXTERNAL.

    Enumerated rather than sampled. The first version of this guard tested
    only the non-zero-returncode path, so the timeout and unparseable-JSON
    messages kept naming `gh pr view` and the test stayed green. Covering one
    branch of a four-branch error surface is how a fix looks complete and is
    not. Refs #5130 review.
    """
    return {
        "gh missing": lambda branch: (_ for _ in ()).throw(FileNotFoundError()),
        "timeout": lambda branch: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd="gh", timeout=mod.GH_TIMEOUT_SECONDS)
        ),
        "nonzero exit": lambda branch: _proc(1, "", "could not connect to api.github.com"),
        "unparseable json": lambda branch: _proc(0, "not json at all", ""),
    }


@pytest.mark.parametrize("path", sorted(_external_paths()))
def test_no_external_path_names_gh_pr_view(monkeypatch, path):
    """Regression guard: this module uses REST list-pulls, not `gh pr view`.

    Issue #4690 moved this module off GraphQL; the operator-facing strings
    lagged behind.
    """
    monkeypatch.setattr(mod, "_run_gh_pr_view", _external_paths()[path])

    code, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert code == mod.EXIT_EXTERNAL
    assert "gh pr view" not in status


@pytest.mark.parametrize("path", sorted(_external_paths()))
def test_every_external_path_states_verification_is_unavailable(monkeypatch, path):
    """An unverifiable label is reported as such on every path, and each says so.

    A reader who hits the timeout branch needs the same guidance as one who
    hits the denial branch: the label cannot be confirmed locally, and only a
    human maintainer may apply commit-limit-bypass. What a caller does with
    that (block, or defer to CI per issue #5232) is not asserted here.
    """
    monkeypatch.setattr(mod, "_run_gh_pr_view", _external_paths()[path])

    _, status = mod.check_bypass_label("commit-limit-bypass", None)

    assert "cannot be verified locally" in status
    assert "human-only" in status


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


class TestUsesRestNotGraphQL:
    """The bypass must survive an exhausted GraphQL budget.

    `gh pr view` is GraphQL, and GraphQL is the first budget to exhaust when
    several agents work one repository. Measured during a fleet session:
    graphql 0 of 5000 remaining while core REST still had 4921. In that state
    the commit-limit ceiling lost its only sanctioned relief, and the customer
    fix for issue #4672 could not be pushed. Refs #4690.
    """

    def test_source_does_not_call_gh_pr_view(self) -> None:
        source = _SCRIPT_PATH.read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("#")
        )
        assert '"pr", "view"' not in code, "gh pr view is GraphQL; use the REST pulls endpoint"

    def test_source_does_not_call_gh_repo_view(self) -> None:
        """The repository lookup must not reintroduce the GraphQL dependency."""
        source = _SCRIPT_PATH.read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("#")
        )
        assert '"repo", "view"' not in code, (
            "gh repo view is GraphQL; derive the repository from the git remote"
        )

    def test_source_uses_the_rest_pulls_endpoint(self) -> None:
        source = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "/pulls" in source and '"api"' in source


class TestRepositoryAndRefValidation:
    """Values reaching the API path are validated at the boundary.

    ``owner_repo`` comes from ``GITHUB_REPOSITORY`` or a parsed remote URL, and
    ``head`` from a branch name. All three are attacker-influenceable in a fork
    or a hostile checkout, and all are interpolated into the request path and
    query. Command injection is not the reachable risk, since gh runs as an
    argument list with no shell. What validation prevents is a crafted value
    steering the request at another repository or smuggling a second query
    parameter through the head filter. Refs #4672.
    """

    @pytest.mark.parametrize(
        "owner_repo",
        [
            "evil/../../other",
            "owner/repo?state=all&head=x",
            "owner repo",
            "owner/repo/extra/../..",
            "no-slash",
        ],
    )
    def test_malformed_repository_is_refused(self, monkeypatch, owner_repo):
        monkeypatch.setenv("GITHUB_REPOSITORY", owner_repo)
        monkeypatch.setattr(
            mod.subprocess,
            "run",
            lambda *a, **k: pytest.fail("gh must not run for a malformed repository"),
        )

        result = mod._run_gh_pr_view("main")

        assert result.returncode == 2
        assert "malformed repository" in result.stderr


    def test_malformed_remote_derived_repository_is_refused(self, monkeypatch):
        """An empty GITHUB_REPOSITORY falls through to remote derivation.

        Validation therefore has to sit after that fallback, not after the
        environment read. My first attempt checked too early and this case
        reached gh.
        """
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        calls: list[list[str]] = []

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ["git", "remote"]:
                return SimpleNamespace(
                    returncode=0, stdout="https://github.com/owner\n", stderr=""
                )
            pytest.fail("gh must not run for a malformed derived repository")

        monkeypatch.setattr(mod.subprocess, "run", _fake_run)

        result = mod._run_gh_pr_view("main")

        assert result.returncode == 2
        assert "malformed repository" in result.stderr

    @pytest.mark.parametrize(
        "branch",
        ["a b", "branch&state=all", "branch?x=1", "br~anch", "br^anch"],
    )
    def test_malformed_branch_is_refused(self, monkeypatch, branch):
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setattr(
            mod.subprocess,
            "run",
            lambda *a, **k: pytest.fail("gh must not run for a malformed branch"),
        )

        result = mod._run_gh_pr_view(branch)

        assert result.returncode == 2
        assert "malformed branch" in result.stderr

    def test_ordinary_values_still_reach_gh(self, monkeypatch):
        """The inverse control: validation must not block legitimate input."""
        monkeypatch.setenv("GITHUB_REPOSITORY", "rjmurillo/ai-agents")
        seen: list[list[str]] = []

        def _fake_run(cmd, **kwargs):
            seen.append(cmd)
            return SimpleNamespace(returncode=0, stdout='{"number": 1}', stderr="")

        monkeypatch.setattr(mod.subprocess, "run", _fake_run)

        result = mod._run_gh_pr_view("fix/some-branch_1.2")

        assert result.returncode == 0
        assert seen, "gh was never invoked for a valid repository and branch"
        assert "repos/rjmurillo/ai-agents/pulls" in seen[0]
