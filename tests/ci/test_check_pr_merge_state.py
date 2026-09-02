from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import check_pr_merge_state as checker


def _pr(state: str, number: int = 123) -> checker.PullRequest:
    return checker.PullRequest(
        number=number,
        title="Test PR",
        url=f"https://github.com/rjmurillo/ai-agents/pull/{number}",
        merge_state_status=state,
        head_ref_name="feature",
        base_ref_name="main",
    )


class _RetryClock:
    """Records the retry waits instead of discarding them.

    Substituting a no-op sleep hides the delay from the test, so removing it,
    or adding one after the final read, leaves the suite green. This keeps both
    the randint bounds and every slept value observable.
    """

    def __init__(self) -> None:
        self.randint_calls: list[tuple[int, int]] = []
        self.sleeps: list[int] = []

    def install(self, monkeypatch) -> None:
        def fake_randint(low: int, high: int) -> int:
            self.randint_calls.append((low, high))
            return high

        monkeypatch.setattr(checker.random, "randint", fake_randint)
        monkeypatch.setattr(checker.time, "sleep", self.sleeps.append)


def test_clean_pr_passes(capsys):
    rc = checker.check_prs([_pr("CLEAN")])
    assert rc == checker.EXIT_OK
    assert "merge state OK" in capsys.readouterr().out


def test_dirty_pr_fails_loud(capsys):
    rc = checker.check_prs([_pr("DIRTY")])
    captured = capsys.readouterr()
    assert rc == checker.EXIT_REGRESSION
    assert "mergeStateStatus=DIRTY" in captured.out
    assert "workflows are unreachable" in captured.out


def test_blocked_pr_does_not_fail_reachability_detector(capsys):
    rc = checker.check_prs([_pr("BLOCKED")])
    captured = capsys.readouterr()
    assert rc == checker.EXIT_OK
    assert "merge state OK" in captured.out


def test_behind_pr_does_not_fail_reachability_detector(capsys):
    rc = checker.check_prs([_pr("BEHIND")])
    captured = capsys.readouterr()
    assert rc == checker.EXIT_OK
    assert "merge state OK" in captured.out


def test_unknown_pr_is_external_error(capsys):
    rc = checker.check_prs([_pr("UNKNOWN")])
    captured = capsys.readouterr()
    assert rc == checker.EXIT_EXTERNAL
    assert "did not provide an authoritative merge verdict" in captured.out


def test_missing_repo_is_config_error(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    rc = checker.main(["--head-ref", "feature"])
    assert rc == checker.EXIT_CONFIG


def test_gh_non_list_payload_is_external_error(monkeypatch, capsys):
    def fake_run_gh(_argv):
        return subprocess.CompletedProcess(
            args=["gh"],
            returncode=0,
            stdout='{"error":"bad shape"}',
            stderr="",
        )

    monkeypatch.setattr(checker, "run_gh", fake_run_gh)
    rc, prs = checker.load_open_prs("rjmurillo/ai-agents", "feature")
    captured = capsys.readouterr()
    assert rc == checker.EXIT_EXTERNAL
    assert prs == []
    assert "not a PR list" in captured.err


def test_gh_malformed_pr_item_is_external_error(monkeypatch, capsys):
    def fake_run_gh(_argv):
        return subprocess.CompletedProcess(
            args=["gh"],
            returncode=0,
            stdout='["not an object"]',
            stderr="",
        )

    monkeypatch.setattr(checker, "run_gh", fake_run_gh)
    rc, prs = checker.load_open_prs("rjmurillo/ai-agents", "feature")
    captured = capsys.readouterr()
    assert rc == checker.EXIT_EXTERNAL
    assert prs == []
    assert "malformed PR item" in captured.err


def test_pr_list_requests_mergeable_so_github_computes_the_verdict(monkeypatch):
    """The retry loop is inert unless the query forces the lazy computation.

    GitHub computes mergeability on demand. `mergeStateStatus` alone does not
    ask for it, so every retry re-reads the same UNKNOWN. `mergeable` is the
    field that triggers the computation, so it is pinned at the argv level:
    dropping it from the --json list fails here, not three retries later in
    production.
    """
    seen = {}

    def fake_run_gh(argv):
        seen["argv"] = list(argv)
        return subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="[]", stderr="")

    monkeypatch.setattr(checker, "run_gh", fake_run_gh)
    checker.load_open_prs("rjmurillo/ai-agents", "feature")

    json_fields = seen["argv"][seen["argv"].index("--json") + 1].split(",")
    assert "mergeable" in json_fields
    assert "mergeStateStatus" in json_fields


def test_python_workflow_runs_merge_state_on_branch_pushes():
    workflow = Path(".github/workflows/pytest.yml").read_text(encoding="utf-8")
    assert "pr-merge-state:" in workflow
    assert "github.event_name == 'push'" in workflow
    assert "python scripts/ci/check_pr_merge_state.py" in workflow
    assert "push:\n    branches:\n      - main" not in workflow


def test_unknown_pr_retries_and_resolves_to_clean(monkeypatch):
    """Test that UNKNOWN is retried and eventually resolves to CLEAN."""
    clock = _RetryClock()
    clock.install(monkeypatch)
    call_count = 0

    def fake_load_open_prs(repo, head_ref):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            # First two attempts return UNKNOWN
            return checker.EXIT_OK, [_pr("UNKNOWN")]
        # Third attempt returns CLEAN
        return checker.EXIT_OK, [_pr("CLEAN")]

    monkeypatch.setattr(checker, "load_open_prs", fake_load_open_prs)

    rc, prs = checker.load_open_prs_with_retry("rjmurillo/ai-agents", "feature")

    assert rc == checker.EXIT_OK
    assert call_count == 3
    assert len(prs) == 1
    assert prs[0].merge_state_status == "CLEAN"


def test_retry_exhausted_still_returns_ok_with_unknown_prs(monkeypatch):
    """load_open_prs_with_retry returns EXIT_OK (the gh call succeeded);
    it does not itself decide pass/fail on UNKNOWN. That decision belongs
    to check_prs, exercised separately below via main()."""
    clock = _RetryClock()
    clock.install(monkeypatch)
    call_count = 0

    def fake_load_open_prs(repo, head_ref):
        nonlocal call_count
        call_count += 1
        # All attempts return UNKNOWN
        return checker.EXIT_OK, [_pr("UNKNOWN")]

    monkeypatch.setattr(checker, "load_open_prs", fake_load_open_prs)

    rc, prs = checker.load_open_prs_with_retry("rjmurillo/ai-agents", "feature")

    assert rc == checker.EXIT_OK
    assert call_count == 3
    assert len(prs) == 1
    assert prs[0].merge_state_status == "UNKNOWN"


def test_retry_waits_the_promised_bounds_and_never_after_the_last_read(monkeypatch):
    """Pin the delay itself, not just that a delay function was importable.

    Three reads means exactly two waits, each drawn from the promised 10-to-20
    second window. Deleting the sleep empties clock.sleeps, adding one after the
    final read makes it three, and moving the bounds fails the literal below.
    """
    clock = _RetryClock()
    clock.install(monkeypatch)
    monkeypatch.setattr(
        checker,
        "load_open_prs",
        lambda repo, head_ref: (checker.EXIT_OK, [_pr("UNKNOWN")]),
    )

    checker.load_open_prs_with_retry("rjmurillo/ai-agents", "feature")

    assert (checker.RETRY_DELAY_MIN_SECONDS, checker.RETRY_DELAY_MAX_SECONDS) == (10, 20)
    assert clock.randint_calls == [(10, 20), (10, 20)]
    assert clock.sleeps == [20, 20]


def test_gh_failure_mid_retry_returns_at_once_without_further_reads(monkeypatch):
    """The early return on a gh failure must not be retried or swallowed.

    A gh crash is not a lazily-computed verdict, so waiting cannot help. The
    second read fails, the third never happens, and the failing code reaches
    the caller unchanged.
    """
    clock = _RetryClock()
    clock.install(monkeypatch)
    call_count = 0

    def fake_load_open_prs(repo, head_ref):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return checker.EXIT_OK, [_pr("UNKNOWN")]
        return checker.EXIT_EXTERNAL, []

    monkeypatch.setattr(checker, "load_open_prs", fake_load_open_prs)

    rc, prs = checker.load_open_prs_with_retry("rjmurillo/ai-agents", "feature")

    assert rc == checker.EXIT_EXTERNAL
    assert prs == []
    assert call_count == 2
    assert clock.sleeps == [20]


@pytest.mark.parametrize("budget", [0, -1, "3", 2.5, None, True])
def test_invalid_max_attempts_is_rejected_before_any_read(monkeypatch, budget):
    """Guard the public parameter, and prove it fires before the first read.

    pytest.raises alone would pass if the function read once and then blew up
    on range(), so the isolating assertion is that no read happened at all.
    """
    reads = []
    monkeypatch.setattr(
        checker,
        "load_open_prs",
        lambda repo, head_ref: (reads.append(head_ref), (checker.EXIT_OK, []))[1],
    )

    with pytest.raises(ValueError, match="max_attempts"):
        checker.load_open_prs_with_retry("rjmurillo/ai-agents", "feature", max_attempts=budget)

    assert reads == []


def test_a_single_attempt_budget_reads_once_and_never_waits(monkeypatch):
    """Pin the documented valid lower bound, not only the rejected values.

    Every case in the parametrization above is invalid, so none of them passes
    1. Tightening the guard from `< 1` to `< 2` would reject this legitimate
    budget while that suite stayed green. One read, no wait, first payload
    returned unchanged.
    """
    clock = _RetryClock()
    clock.install(monkeypatch)
    reads = []

    def fake_load_open_prs(repo, head_ref):
        reads.append(head_ref)
        return checker.EXIT_OK, [_pr("UNKNOWN")]

    monkeypatch.setattr(checker, "load_open_prs", fake_load_open_prs)

    rc, prs = checker.load_open_prs_with_retry(
        "rjmurillo/ai-agents", "feature", max_attempts=1
    )

    assert rc == checker.EXIT_OK
    assert reads == ["feature"]
    assert clock.sleeps == []
    assert [pr.merge_state_status for pr in prs] == ["UNKNOWN"]


def test_an_unlisted_status_is_retried_the_same_as_unknown(monkeypatch):
    """The retry predicate must match the predicate that fails the run.

    check_prs exits 3 on any status outside PASS_STATES | FAIL_STATES, not just
    the literal UNKNOWN. A retry that waited only on UNKNOWN would let a new or
    unlisted GitHub status skip the wait and still fail the check, so both sides
    share has_no_verdict. With the narrower predicate this reads once, not twice.
    """
    clock = _RetryClock()
    clock.install(monkeypatch)
    call_count = 0

    def fake_load_open_prs(repo, head_ref):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return checker.EXIT_OK, [_pr("MERGEABILITY_PENDING")]
        return checker.EXIT_OK, [_pr("CLEAN")]

    monkeypatch.setattr(checker, "load_open_prs", fake_load_open_prs)

    rc, prs = checker.load_open_prs_with_retry("rjmurillo/ai-agents", "feature")

    assert checker.check_prs([_pr("MERGEABILITY_PENDING")]) == checker.EXIT_EXTERNAL
    assert rc == checker.EXIT_OK
    assert call_count == 2
    assert clock.sleeps == [20]
    assert prs[0].merge_state_status == "CLEAN"


def test_one_verdictless_pr_retries_even_when_a_sibling_is_decided(monkeypatch):
    """A mixed list retries the whole batch, because the verdict-less member is
    the one that would fail the run."""
    clock = _RetryClock()
    clock.install(monkeypatch)
    call_count = 0

    def fake_load_open_prs(repo, head_ref):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return checker.EXIT_OK, [_pr("CLEAN", number=1), _pr("UNKNOWN", number=2)]
        return checker.EXIT_OK, [_pr("CLEAN", number=1), _pr("CLEAN", number=2)]

    monkeypatch.setattr(checker, "load_open_prs", fake_load_open_prs)

    rc, prs = checker.load_open_prs_with_retry("rjmurillo/ai-agents", "feature")

    assert rc == checker.EXIT_OK
    assert call_count == 2
    assert clock.sleeps == [20]
    assert [pr.merge_state_status for pr in prs] == ["CLEAN", "CLEAN"]


def test_main_exits_external_after_retries_exhausted_on_unknown(monkeypatch):
    """End-to-end: main() must route through load_open_prs_with_retry, not
    the bare load_open_prs. Mocking load_open_prs (the retry loop's inner
    call) and counting invocations catches a regression that wires main()
    back to the un-retried call: call_count would drop from 3 to 1."""
    clock = _RetryClock()
    clock.install(monkeypatch)
    call_count = 0

    def fake_load_open_prs(repo, head_ref):
        nonlocal call_count
        call_count += 1
        return checker.EXIT_OK, [_pr("UNKNOWN")]

    monkeypatch.setattr(checker, "load_open_prs", fake_load_open_prs)
    monkeypatch.setenv("GITHUB_REPOSITORY", "rjmurillo/ai-agents")
    monkeypatch.setenv("GITHUB_REF_NAME", "feature")

    rc = checker.main([])

    assert rc == checker.EXIT_EXTERNAL
    assert call_count == 3
