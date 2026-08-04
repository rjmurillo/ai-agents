"""Detection of commits pushed after their PR merged (issue #4316).

The shape under test is the one measured on PR #4274: the PR froze
``headRefOid`` at ``fdfb4ba1...`` and the branch tip moved to ``145b44b9...``
afterwards.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.maintenance import detect_orphan_commits as detector

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-maintenance.yml"

MERGED_HEAD = "fdfb4ba1e9fbe38cc91603999b2e8ddd3db592af"
POST_MERGE_TIP = "145b44b948e689eee0924812c1d2931a96c62f2e"


def _pr(number=4274, branch="fix/debate-log-canonical-path", head=MERGED_HEAD):
    return {
        "number": number,
        "headRefName": branch,
        "headRefOid": head,
        "mergedAt": "2026-08-02T18:35:48Z",
    }


def _never_landed(_sha: str) -> bool:
    return False


def test_reports_a_branch_that_moved_after_the_merge() -> None:
    findings = detector.find_orphan_commits(
        [_pr()],
        {"fix/debate-log-canonical-path": POST_MERGE_TIP},
        _never_landed,
    )

    assert len(findings) == 1
    assert findings[0].number == 4274
    assert findings[0].merged_head == MERGED_HEAD
    assert findings[0].current_tip == POST_MERGE_TIP
    assert findings[0].landed_anyway is False


def test_squash_merged_branch_that_never_moved_is_not_a_finding() -> None:
    """A squash merge leaves the head unreachable from main; that is not loss."""
    findings = detector.find_orphan_commits(
        [_pr()],
        {"fix/debate-log-canonical-path": MERGED_HEAD},
        _never_landed,
    )

    assert findings == []


def test_deleted_branch_is_not_a_finding() -> None:
    findings = detector.find_orphan_commits([_pr()], {}, _never_landed)

    assert findings == []


def test_a_tip_already_on_main_is_reported_but_marked_landed() -> None:
    findings = detector.find_orphan_commits(
        [_pr()],
        {"fix/debate-log-canonical-path": POST_MERGE_TIP},
        lambda _sha: True,
    )

    assert len(findings) == 1
    assert findings[0].landed_anyway is True


def test_pr_missing_a_head_ref_is_skipped() -> None:
    findings = detector.find_orphan_commits(
        [{"number": 1, "headRefName": "", "headRefOid": ""}],
        {"": POST_MERGE_TIP},
        _never_landed,
    )

    assert findings == []


def test_only_the_moved_branch_is_reported_among_several() -> None:
    prs = [
        _pr(number=1, branch="clean", head="a" * 40),
        _pr(number=2, branch="moved", head=MERGED_HEAD),
    ]
    tips = {"clean": "a" * 40, "moved": POST_MERGE_TIP}

    findings = detector.find_orphan_commits(prs, tips, _never_landed)

    assert [finding.number for finding in findings] == [2]


def test_report_names_the_examined_count_and_the_recovery_command() -> None:
    findings = detector.find_orphan_commits(
        [_pr()],
        {"fix/debate-log-canonical-path": POST_MERGE_TIP},
        _never_landed,
    )

    report = detector.format_report(findings, examined=17)

    assert "1 finding(s) in 17 merged PR(s)" in report
    assert f"git diff {MERGED_HEAD} {POST_MERGE_TIP}" in report


def test_report_of_a_clean_sweep_still_names_the_examined_count() -> None:
    assert "0 finding(s) in 17 merged PR(s)" in detector.format_report([], examined=17)


def test_fetch_remote_tips_parses_ls_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Result:
        returncode = 0
        stdout = f"{POST_MERGE_TIP}\trefs/heads/moved\n{MERGED_HEAD}\trefs/tags/v1\n"
        stderr = ""

    monkeypatch.setattr(detector, "_run", lambda *_args, **_kwargs: _Result())

    assert detector.fetch_remote_tips() == {"moved": POST_MERGE_TIP}


def test_main_exits_1_when_an_orphan_is_found(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(detector, "fetch_merged_prs", lambda *_a, **_k: [_pr()])
    monkeypatch.setattr(
        detector,
        "fetch_remote_tips",
        lambda *_a, **_k: {"fix/debate-log-canonical-path": POST_MERGE_TIP},
    )
    monkeypatch.setattr(detector, "make_is_landed", lambda *_a, **_k: _never_landed)

    assert detector.main([]) == 1
    assert "PR #4274" in capsys.readouterr().out


def test_main_exits_0_when_nothing_moved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detector, "fetch_merged_prs", lambda *_a, **_k: [_pr()])
    monkeypatch.setattr(
        detector,
        "fetch_remote_tips",
        lambda *_a, **_k: {"fix/debate-log-canonical-path": MERGED_HEAD},
    )
    monkeypatch.setattr(detector, "make_is_landed", lambda *_a, **_k: _never_landed)

    assert detector.main([]) == 0


def test_main_exits_2_when_the_remote_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("git ls-remote failed: network down")

    monkeypatch.setattr(detector, "fetch_merged_prs", lambda *_a, **_k: [_pr()])
    monkeypatch.setattr(detector, "fetch_remote_tips", _boom)

    assert detector.main([]) == 2
    assert "network down" in capsys.readouterr().err


def test_main_emits_machine_readable_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(detector, "fetch_merged_prs", lambda *_a, **_k: [_pr()])
    monkeypatch.setattr(
        detector,
        "fetch_remote_tips",
        lambda *_a, **_k: {"fix/debate-log-canonical-path": POST_MERGE_TIP},
    )
    monkeypatch.setattr(detector, "make_is_landed", lambda *_a, **_k: _never_landed)

    assert detector.main(["--json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["examined"] == 1
    assert payload["findings"][0]["current_tip"] == POST_MERGE_TIP


def test_the_hourly_sweep_runs_the_detector_without_blocking() -> None:
    """Wiring: the detector is dead code unless the hourly job invokes it."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    steps = workflow["jobs"]["discover-prs"]["steps"]
    matching = [
        step
        for step in steps
        if "scripts/maintenance/detect_orphan_commits.py" in str(step.get("run", ""))
    ]

    assert len(matching) == 1, "hourly sweep must invoke the orphan-commit detector once"
    assert matching[0]["continue-on-error"] is True, (
        "the detector warns; a finding must not fail the maintenance sweep"
    )


# ---------------------------------------------------------------------------
# Reporting: continue-on-error means the exit code reaches nobody (issue #4316)
# ---------------------------------------------------------------------------


def _wire_one_orphan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detector, "fetch_merged_prs", lambda *_a, **_k: [_pr()])
    monkeypatch.setattr(
        detector,
        "fetch_remote_tips",
        lambda *_a, **_k: {"fix/debate-log-canonical-path": POST_MERGE_TIP},
    )
    monkeypatch.setattr(detector, "make_is_landed", lambda *_a, **_k: _never_landed)


def test_main_writes_every_finding_to_the_job_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _wire_one_orphan(monkeypatch)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    assert detector.main([]) == 1

    written = summary.read_text(encoding="utf-8")
    assert "#4274" in written
    assert "fix/debate-log-canonical-path" in written
    assert POST_MERGE_TIP[:12] in written


def test_a_clean_sweep_still_names_the_examined_count_in_the_job_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(detector, "fetch_merged_prs", lambda *_a, **_k: [_pr()])
    monkeypatch.setattr(
        detector,
        "fetch_remote_tips",
        lambda *_a, **_k: {"fix/debate-log-canonical-path": MERGED_HEAD},
    )
    monkeypatch.setattr(detector, "make_is_landed", lambda *_a, **_k: _never_landed)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    assert detector.main([]) == 0

    assert "(0 in 1)" in summary.read_text(encoding="utf-8")


def test_main_appends_rather_than_truncating_an_existing_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _wire_one_orphan(monkeypatch)
    summary = tmp_path / "summary.md"
    summary.write_text("## Earlier step\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    detector.main([])

    assert summary.read_text(encoding="utf-8").startswith("## Earlier step\n")


def test_main_still_reports_on_stdout_when_no_summary_file_exists(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _wire_one_orphan(monkeypatch)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    assert detector.main([]) == 1
    assert "PR #4274" in capsys.readouterr().out


def test_an_unwritable_summary_path_warns_without_changing_the_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _wire_one_orphan(monkeypatch)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "missing-dir" / "s.md"))

    assert detector.main([]) == 1
    assert "could not write the job summary" in capsys.readouterr().err


def test_the_sweep_step_leaves_the_job_summary_variable_alone() -> None:
    """Wiring: the runner sets GITHUB_STEP_SUMMARY, so the step must not shadow it.

    Overriding or clearing it in the step env silently returns the detector to
    stdout-only reporting inside an always-green step, which is the exact
    non-report issue #4316(b) is about.
    """
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    steps = workflow["jobs"]["discover-prs"]["steps"]
    step = next(
        s
        for s in steps
        if "scripts/maintenance/detect_orphan_commits.py" in str(s.get("run", ""))
    )

    assert "GITHUB_STEP_SUMMARY" not in step.get("env", {})
