"""Tests for the whole-repo taste-lint error-count ratchet (issue #3779)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.ci import count_ratchet
from scripts.ci import taste_count_ratchet as ratchet

REPO_ROOT = Path(__file__).resolve().parents[2]


def _report(error_count: int) -> str:
    return json.dumps(
        {
            "files_scanned": 1,
            "files_by_category": {"authored": 1},
            "error_count": error_count,
            "warning_count": 0,
            "violations": [],
        }
    )


def _fake_scan(
    returncode: int,
    error_count: int,
    *,
    tracked: tuple[str, ...] = ("pkg/mod.py",),
    git_returncode: int = 0,
    lint_stdout: str | None = None,
):
    """subprocess.run stand-in for every leg of the scan.

    ``git ls-files -z`` returns ``tracked`` NUL-joined; every linter invocation
    returns a report carrying ``error_count`` unless ``lint_stdout`` overrides
    it. The report is emitted once per linter call, so a multi-batch
    expectation must size ``tracked`` accordingly.
    """

    def _run(cmd, **kwargs):
        if cmd[0] == "git":
            stdout = "\0".join(tracked) + ("\0" if tracked else "")
            return subprocess.CompletedProcess(cmd, git_returncode, stdout=stdout, stderr="")
        stdout = lint_stdout if lint_stdout is not None else _report(error_count)
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    return _run


def test_git_failure_yields_no_count(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 615, git_returncode=128))
    assert ratchet.current_count(tmp_path) is None


def test_main_maps_an_unmeasurable_count_to_exit_3(monkeypatch):
    monkeypatch.setattr(ratchet, "current_count", lambda _root: None)
    assert ratchet.main(["--base-ref", "HEAD"]) == ratchet.EXIT_EXTERNAL


def test_a_crashed_linter_is_not_a_clean_tree(tmp_path, monkeypatch):
    """The failure mode that would disarm this gate permanently.

    taste_lints.py exits 1 on a script error. If that were read as a count of
    zero, the ratchet would report a full-tree improvement and nothing after
    that could ever fail. So a non-scan exit code must give no count (exit 3
    through ``main``), not zero.
    """
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 0, lint_stdout=""))
    count = ratchet.current_count(tmp_path)
    assert count is None


def test_a_crashed_linter_that_still_printed_a_report_is_rejected(tmp_path, monkeypatch):
    """Isolating control for the exit-code guard specifically.

    The JSON guard alone is not enough. A linter that crashed partway can still
    have printed a well-formed report covering the files it managed to read,
    and that report's count is not the tree's count. Only the exit code says
    whether the scan finished, so it has to be checked on its own.
    """
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 0, lint_stdout=_report(0)))
    count = ratchet.current_count(tmp_path)
    assert count is None


def test_a_clean_exit_is_a_real_zero(tmp_path, monkeypatch):
    # Exit 0 means the lint ran and found nothing. Unlike exit 1 it is a
    # trustworthy count and must be accepted, or a genuinely clean tree could
    # never be measured as improved.
    monkeypatch.setattr(subprocess, "run", _fake_scan(0, 0))
    count = ratchet.current_count(tmp_path)
    assert count == 0


def test_unparseable_report_yields_no_count(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 0, lint_stdout="not json"))
    count = ratchet.current_count(tmp_path)
    assert count is None


def test_a_non_mapping_report_yields_no_count(tmp_path, monkeypatch):
    """A report that parsed as JSON but is not an object (review of #4284).

    ``report.get("error_count")`` raised AttributeError on a list, a string, or
    a bare null, and the traceback left the process exiting 1: the ratchet's
    own code for a REGRESSION. An unreadable report is an external error and
    must exit 3, or a broken linter reads as new violations a contributor
    cannot find.
    """
    for payload in ("null", "7", '"hello"', '[{"error_count": 3}]'):
        monkeypatch.setattr(subprocess, "run", _fake_scan(10, 0, lint_stdout=payload))
        count = ratchet.current_count(tmp_path)
        assert count is None, payload


def test_report_without_an_integer_count_yields_no_count(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", _fake_scan(10, 0, lint_stdout=json.dumps({"violations": []}))
    )
    count = ratchet.current_count(tmp_path)
    assert count is None


def test_counts_are_summed_across_batches(tmp_path, monkeypatch):
    # 7,500 tracked paths do not fit one argv, so the scan is chunked and each
    # batch reports its own count. Reading only the last would undercount.
    tracked = tuple(f"{'p' * 200}/{index}.py" for index in range(400))
    batches = len(count_ratchet.chunk(list(tracked)))
    assert batches > 1, "fixture must span more than one batch to test summing"
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 1, tracked=tracked))
    assert ratchet.current_count(tmp_path) == batches


def test_an_empty_tracked_set_counts_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 5, tracked=()))
    assert ratchet.current_count(tmp_path) == 0


def test_every_tracked_path_is_offered_to_the_linter(tmp_path, monkeypatch):
    """Scope is the whole tracked set, not a suffix-filtered subset.

    ``run_lint`` already skips anything outside its scannable-extension set.
    Filtering here would duplicate that list and let the two drift, so a PR
    adding a new scannable extension to the linter would silently stay
    unratcheted.
    """
    seen: list[list[str]] = []

    def _run(cmd, **kwargs):
        seen.append(list(cmd))
        if cmd[0] == "git":
            return subprocess.CompletedProcess(cmd, 0, stdout="a.md\0b.py\0", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout=_report(0), stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    ratchet.current_count(tmp_path)
    assert seen[0][seen[0].index("--") + 1 :] == ["*"]
    assert seen[1][-2:] == ["a.md", "b.py"]


def test_main_without_base_ref_is_a_config_error(capsys):
    assert ratchet.main([]) == ratchet.EXIT_CONFIG
    captured = capsys.readouterr()
    assert "--base-ref" in captured.err + captured.out


def test_main_wires_this_ratchet_into_the_base_derived_run(monkeypatch):
    seen: dict = {}

    def _run(args, **kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(ratchet, "run", _run)
    assert ratchet.main(["--base-ref", "origin/main"]) == 0
    assert seen["label"] == "taste count ratchet"
    assert seen["introduced_by"] == ratchet._SCRIPT
    assert seen["counter"] is ratchet.current_count
    assert seen["lister"] is ratchet.list_violations


def test_script_marker_names_a_tracked_file():
    assert (REPO_ROOT / ratchet._SCRIPT).is_file()


def test_end_to_end_against_head_passes_on_the_real_repo():
    assert ratchet.main(["--base-ref", "HEAD", "--repo-root", str(REPO_ROOT)]) == ratchet.EXIT_OK
