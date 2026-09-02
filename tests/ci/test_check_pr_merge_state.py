from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.ci import check_pr_merge_state as checker


def _pr(state: str) -> checker.PullRequest:
    return checker.PullRequest(
        number=123,
        title="Test PR",
        url="https://github.com/rjmurillo/ai-agents/pull/123",
        merge_state_status=state,
        head_ref_name="feature",
        base_ref_name="main",
    )


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
    call_count = 0

    def fake_load_open_prs(repo, head_ref):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            # First two attempts return UNKNOWN
            return checker.EXIT_OK, [_pr("UNKNOWN")]
        # Third attempt returns CLEAN
        return checker.EXIT_OK, [_pr("CLEAN")]

    # Mock time.sleep so tests run fast
    def fake_sleep(seconds):
        pass

    monkeypatch.setattr(checker, "load_open_prs", fake_load_open_prs)
    monkeypatch.setattr("time.sleep", fake_sleep)

    rc, prs = checker.load_open_prs_with_retry("rjmurillo/ai-agents", "feature")

    assert rc == checker.EXIT_OK
    assert call_count == 3
    assert len(prs) == 1
    assert prs[0].merge_state_status == "CLEAN"


def test_retry_exhausted_still_returns_ok_with_unknown_prs(monkeypatch):
    """load_open_prs_with_retry returns EXIT_OK (the gh call succeeded);
    it does not itself decide pass/fail on UNKNOWN. That decision belongs
    to check_prs, exercised separately below via main()."""
    call_count = 0

    def fake_load_open_prs(repo, head_ref):
        nonlocal call_count
        call_count += 1
        # All attempts return UNKNOWN
        return checker.EXIT_OK, [_pr("UNKNOWN")]

    # Mock time.sleep so tests run fast
    def fake_sleep(seconds):
        pass

    monkeypatch.setattr(checker, "load_open_prs", fake_load_open_prs)
    monkeypatch.setattr("time.sleep", fake_sleep)

    rc, prs = checker.load_open_prs_with_retry("rjmurillo/ai-agents", "feature")

    assert rc == checker.EXIT_OK
    assert call_count == 3
    assert len(prs) == 1
    assert prs[0].merge_state_status == "UNKNOWN"


def test_main_exits_external_after_retries_exhausted_on_unknown(monkeypatch):
    """End-to-end: main() must route through load_open_prs_with_retry, not
    the bare load_open_prs. Mocking load_open_prs (the retry loop's inner
    call) and counting invocations catches a regression that wires main()
    back to the un-retried call: call_count would drop from 3 to 1."""
    call_count = 0

    def fake_load_open_prs(repo, head_ref):
        nonlocal call_count
        call_count += 1
        return checker.EXIT_OK, [_pr("UNKNOWN")]

    monkeypatch.setattr(checker, "load_open_prs", fake_load_open_prs)
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    monkeypatch.setenv("GITHUB_REPOSITORY", "rjmurillo/ai-agents")
    monkeypatch.setenv("GITHUB_REF_NAME", "feature")

    rc = checker.main([])

    assert rc == checker.EXIT_EXTERNAL
    assert call_count == 3
