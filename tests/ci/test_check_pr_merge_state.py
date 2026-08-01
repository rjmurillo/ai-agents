from __future__ import annotations

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
    assert "workflows may be unreachable" in captured.out


def test_unknown_pr_is_external_error(capsys):
    rc = checker.check_prs([_pr("UNKNOWN")])
    captured = capsys.readouterr()
    assert rc == checker.EXIT_EXTERNAL
    assert "did not provide an authoritative merge verdict" in captured.out


def test_missing_repo_is_config_error():
    rc = checker.main(["--head-ref", "feature"])
    assert rc == checker.EXIT_CONFIG


def test_python_workflow_runs_merge_state_on_branch_pushes():
    workflow = Path(".github/workflows/pytest.yml").read_text(encoding="utf-8")
    assert "pr-merge-state:" in workflow
    assert "github.event_name == 'push'" in workflow
    assert "python scripts/ci/check_pr_merge_state.py" in workflow
    assert "push:\n    branches:\n      - main" not in workflow
