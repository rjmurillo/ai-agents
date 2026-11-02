"""Tests for scripts/ci/flaky_test_report.py: detect-only flaky test reporting."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.ci import flaky_test_report as ftr

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "flaky_test_report.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pytest.yml"

FLAKY = "tests/test_a.py::test_flaky"
BROKEN = "tests/test_a.py::test_broken[a|b]"


def _junit(path: Path, cases: list[str | None]) -> Path:
    """Write a JUnit report; each entry is None (pass), 'failure', or 'error'."""
    body = []
    for index, child in enumerate(cases):
        inner = f"<{child} message='x'/>" if child else ""
        body.append(f"<testcase classname='tests.test_a' name='t{index}'>{inner}</testcase>")
    path.write_text(
        f"<?xml version='1.0'?><testsuites><testsuite>{''.join(body)}</testsuite></testsuites>",
        encoding="utf-8",
    )
    return path


def _lastfailed(path: Path, nodeids: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict.fromkeys(nodeids, True)), encoding="utf-8")
    return path


def _state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "version": ftr.STATE_VERSION,
        "status": ftr.STATUS_RAN,
        "first_failures": [BROKEN, FLAKY],
        "max_tests": 25,
        "rerun_exit": 1,
        "rerun_failures": [BROKEN],
    }
    state.update(overrides)
    return state


def _fake_runner(out_dir: Path, still_failing: list[str], exit_code: int, calls: list):
    def runner(args: list[str]) -> int:
        calls.append(args)
        cache = out_dir / ftr.RERUN_CACHE_DIR / "v" / "cache" / "lastfailed"
        if still_failing:
            _lastfailed(cache, still_failing)
        return exit_code

    return runner


# --- load_junit_counts -------------------------------------------------------


def test_junit_counts_failures_and_errors(tmp_path):
    counts = ftr.load_junit_counts(_junit(tmp_path / "r.xml", [None, "failure", "error", None]))
    assert counts == ftr.JunitCounts(tests=4, failed=2)


def test_junit_single_testsuite_root_is_accepted(tmp_path):
    path = tmp_path / "r.xml"
    path.write_text("<testsuite><testcase name='a'/></testsuite>", encoding="utf-8")
    assert ftr.load_junit_counts(path) == ftr.JunitCounts(tests=1, failed=0)


def test_junit_missing_fails_closed(tmp_path):
    with pytest.raises(ftr.InputError, match="not found"):
        ftr.load_junit_counts(tmp_path / "absent.xml")


def test_junit_malformed_fails_closed(tmp_path):
    path = tmp_path / "r.xml"
    path.write_text("<testsuites><testcase>", encoding="utf-8")
    with pytest.raises(ftr.InputError, match="malformed"):
        ftr.load_junit_counts(path)


def test_junit_with_dtd_is_refused(tmp_path):
    path = tmp_path / "r.xml"
    path.write_text("<!DOCTYPE x [<!ENTITY a 'b'>]><testsuites/>", encoding="utf-8")
    with pytest.raises(ftr.InputError, match="DTD"):
        ftr.load_junit_counts(path)


def test_junit_wrong_root_is_refused(tmp_path):
    path = tmp_path / "r.xml"
    path.write_text("<html/>", encoding="utf-8")
    with pytest.raises(ftr.InputError, match="not a JUnit report"):
        ftr.load_junit_counts(path)


def test_junit_undecodable_fails_closed(tmp_path):
    path = tmp_path / "r.xml"
    path.write_bytes(b"\xff\xfe\xfa")
    with pytest.raises(ftr.InputError, match="could not read"):
        ftr.load_junit_counts(path)


# --- load_lastfailed ---------------------------------------------------------


def test_lastfailed_missing_is_empty(tmp_path):
    assert ftr.load_lastfailed(tmp_path / "lastfailed") == []


def test_lastfailed_sorted_and_false_entries_dropped(tmp_path):
    path = tmp_path / "lastfailed"
    path.write_text(json.dumps({"b": True, "a": True, "c": False}), encoding="utf-8")
    assert ftr.load_lastfailed(path) == ["a", "b"]


@pytest.mark.parametrize("payload", ["{not json", "[1, 2]"])
def test_lastfailed_malformed_fails_closed(tmp_path, payload):
    path = tmp_path / "lastfailed"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ftr.InputError):
        ftr.load_lastfailed(path)


# --- run_rerun ---------------------------------------------------------------


def test_rerun_runs_only_failed_tests_serially(tmp_path):
    out = tmp_path / "out"
    calls: list = []
    lastfailed = _lastfailed(tmp_path / "lf", [FLAKY, BROKEN])

    rc = ftr.run_rerun(lastfailed, out, 25, _fake_runner(out, [BROKEN], 1, calls))

    assert rc == ftr.EXIT_OK
    (args,) = calls
    assert args[:2] == ["-n", "0"]
    assert args[-2:] == [BROKEN, FLAKY]
    assert f"cache_dir={(out / ftr.RERUN_CACHE_DIR).resolve()}" in args
    assert f"--junitxml={(out / ftr.RERUN_JUNIT_FILE).resolve()}" in args
    state = json.loads((out / ftr.STATE_FILE).read_text(encoding="utf-8"))
    assert state["status"] == ftr.STATUS_RAN
    assert state["rerun_exit"] == 1
    assert state["rerun_failures"] == [BROKEN]


def test_rerun_skipped_without_nodeids(tmp_path):
    out = tmp_path / "out"
    calls: list = []
    rc = ftr.run_rerun(tmp_path / "absent", out, 25, _fake_runner(out, [], 0, calls))
    assert rc == ftr.EXIT_OK
    assert calls == []
    assert json.loads((out / ftr.STATE_FILE).read_text())["status"] == ftr.STATUS_NO_NODEIDS


def test_rerun_skipped_above_cap(tmp_path):
    out = tmp_path / "out"
    calls: list = []
    lastfailed = _lastfailed(tmp_path / "lf", [f"t::{i}" for i in range(3)])
    rc = ftr.run_rerun(lastfailed, out, 2, _fake_runner(out, [], 0, calls))
    assert rc == ftr.EXIT_OK
    assert calls == []
    assert json.loads((out / ftr.STATE_FILE).read_text())["status"] == ftr.STATUS_OVER_CAP


def test_rerun_at_cap_still_runs(tmp_path):
    out = tmp_path / "out"
    calls: list = []
    lastfailed = _lastfailed(tmp_path / "lf", ["t::0", "t::1"])
    ftr.run_rerun(lastfailed, out, 2, _fake_runner(out, [], 0, calls))
    assert len(calls) == 1


def test_rerun_state_says_started_while_pytest_runs(tmp_path):
    out = tmp_path / "out"
    seen: list = []

    def runner(args):
        seen.append(json.loads((out / ftr.STATE_FILE).read_text())["status"])
        return 0

    ftr.run_rerun(_lastfailed(tmp_path / "lf", [FLAKY]), out, 25, runner)
    assert seen == [ftr.STATUS_STARTED]


# --- load_state --------------------------------------------------------------


def test_state_missing_is_none(tmp_path):
    assert ftr.load_state(tmp_path / "state.json") is None


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ("{bad", ftr.InputError),
        (json.dumps({"version": 99}), ftr.StateError),
        (json.dumps(_state(status="weird")), ftr.StateError),
        (json.dumps(_state(first_failures="x")), ftr.StateError),
        (json.dumps(_state(rerun_failures=[1])), ftr.StateError),
    ],
)
def test_state_invalid(tmp_path, payload, error):
    path = tmp_path / "state.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(error):
        ftr.load_state(path)


# --- classify ----------------------------------------------------------------

_FAILED_FIRST = ftr.JunitCounts(tests=10, failed=2)
_RERUN_TWO = ftr.JunitCounts(tests=2, failed=1)


def test_classify_first_run_passed():
    outcome = ftr.classify(ftr.JunitCounts(5, 0), "success", None, None)
    assert outcome.exit_code == ftr.EXIT_OK
    assert outcome.rows == []


def test_classify_failed_step_without_failed_test():
    outcome = ftr.classify(ftr.JunitCounts(5, 0), "failure", None, None)
    assert outcome.exit_code == ftr.EXIT_FAILED
    assert "records no failed test" in outcome.headline


def test_classify_missing_state():
    outcome = ftr.classify(_FAILED_FIRST, "failure", None, None)
    assert outcome.exit_code == ftr.EXIT_EXTERNAL


def test_classify_no_nodeids():
    state = _state(status=ftr.STATUS_NO_NODEIDS, first_failures=[])
    assert ftr.classify(_FAILED_FIRST, "failure", state, None).exit_code == ftr.EXIT_EXTERNAL


def test_classify_over_cap_fails_and_lists_tests():
    outcome = ftr.classify(_FAILED_FIRST, "failure", _state(status=ftr.STATUS_OVER_CAP), None)
    assert outcome.exit_code == ftr.EXIT_FAILED
    assert outcome.unclassified == [BROKEN, FLAKY]
    assert "above the rerun cap of 25" in outcome.headline


def test_classify_started_but_not_finished():
    outcome = ftr.classify(_FAILED_FIRST, "failure", _state(status=ftr.STATUS_STARTED), None)
    assert outcome.exit_code == ftr.EXIT_EXTERNAL
    assert {row[1] for row in outcome.rows} == {"did not finish"}


@pytest.mark.parametrize(
    ("rerun", "rerun_exit"),
    [(None, 1), (ftr.JunitCounts(0, 0), 1), (_RERUN_TWO, 4), (_RERUN_TWO, None)],
)
def test_classify_unusable_rerun_is_inconclusive(rerun, rerun_exit):
    outcome = ftr.classify(_FAILED_FIRST, "failure", _state(rerun_exit=rerun_exit), rerun)
    assert outcome.exit_code == ftr.EXIT_EXTERNAL
    assert outcome.unclassified == [BROKEN, FLAKY]


def test_classify_nonzero_rerun_without_failures_is_inconclusive():
    outcome = ftr.classify(_FAILED_FIRST, "failure", _state(rerun_failures=[]), _RERUN_TWO)
    assert outcome.exit_code == ftr.EXIT_EXTERNAL


def test_classify_zero_exit_with_failure_is_inconsistent():
    state = _state(rerun_exit=0, rerun_failures=[])
    outcome = ftr.classify(_FAILED_FIRST, "failure", state, _RERUN_TWO)
    assert outcome.exit_code == ftr.EXIT_EXTERNAL
    assert "inconsistent" in outcome.headline


def test_classify_flaky_and_consistent():
    outcome = ftr.classify(_FAILED_FIRST, "failure", _state(), _RERUN_TWO)
    assert outcome.exit_code == ftr.EXIT_FAILED
    assert outcome.flaky == [FLAKY]
    assert outcome.consistent == [BROKEN]


def test_classify_all_flaky_still_fails_the_leg():
    state = _state(rerun_exit=0, rerun_failures=[])
    outcome = ftr.classify(_FAILED_FIRST, "failure", state, ftr.JunitCounts(2, 0))
    assert outcome.exit_code == ftr.EXIT_FAILED
    assert outcome.flaky == [BROKEN, FLAKY]


def test_classify_collection_error_rerun_counts_as_consistent():
    state = _state(rerun_exit=2, rerun_failures=[BROKEN, FLAKY])
    outcome = ftr.classify(_FAILED_FIRST, "failure", state, _RERUN_TWO)
    assert outcome.consistent == [BROKEN, FLAKY]
    assert outcome.exit_code == ftr.EXIT_FAILED


# --- rendering ---------------------------------------------------------------


def test_summary_escapes_pipes_and_shows_note():
    outcome = ftr.classify(_FAILED_FIRST, "failure", _state(), _RERUN_TWO)
    text = ftr.render_summary("split-1", outcome, "stale cache")
    assert "| `tests/test_a.py::test_broken[a\\|b]` | failed | failed | consistent |" in text
    assert "> stale cache" in text
    assert "a rerun never turns a leg green" in text


def test_cache_note_only_when_cache_exceeds_junit():
    assert ftr._cache_note(ftr.JunitCounts(5, 1), ["a", "b"]) != ""
    assert ftr._cache_note(ftr.JunitCounts(5, 2), ["a", "b"]) == ""


def test_emit_summary_unwritable_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "missing-dir" / "s.md"))
    assert ftr._emit_summary("x") == ftr.EXIT_EXTERNAL


def test_emit_summary_without_env_prints(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert ftr._emit_summary("hello\n") == ftr.EXIT_OK
    assert capsys.readouterr().out == "hello\n"


# --- main (CLI) --------------------------------------------------------------


def _report_argv(first: Path, out: Path, outcome: str = "failure") -> list[str]:
    return [
        "report",
        "--first-junit",
        str(first),
        "--first-outcome",
        outcome,
        "--out-dir",
        str(out),
        "--partition",
        "split-1",
    ]


def test_cli_end_to_end_reports_flaky_and_exits_nonzero(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    lastfailed = _lastfailed(tmp_path / "lf", [FLAKY, BROKEN])
    calls: list = []

    def runner(args):
        calls.append(args)
        _lastfailed(out / ftr.RERUN_CACHE_DIR / "v" / "cache" / "lastfailed", [BROKEN])
        _junit(out / ftr.RERUN_JUNIT_FILE, ["failure", None])
        return 1

    assert ftr.main(["rerun", "--out-dir", str(out), "--lastfailed", str(lastfailed)], runner) == 0
    first = _junit(tmp_path / "first.xml", ["failure", "failure", None])
    rc = ftr.main(_report_argv(first, out))

    assert rc == ftr.EXIT_FAILED
    assert f"::warning title=Flaky test::{FLAKY}" in capsys.readouterr().out
    assert "| flaky |" in summary.read_text(encoding="utf-8")
    report = json.loads((out / ftr.REPORT_FILE).read_text(encoding="utf-8"))
    assert report["flaky"] == [FLAKY]
    assert report["consistent"] == [BROKEN]
    assert report["exit_code"] == ftr.EXIT_FAILED


def test_cli_report_first_run_passed_writes_no_summary(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    first = _junit(tmp_path / "first.xml", [None])
    assert ftr.main(_report_argv(first, tmp_path / "out", "success")) == ftr.EXIT_OK
    assert not summary.exists()


def test_cli_report_missing_first_junit_exits_3(tmp_path):
    out = tmp_path / "out"
    assert ftr.main(_report_argv(tmp_path / "absent.xml", out)) == ftr.EXIT_EXTERNAL
    assert json.loads((out / ftr.REPORT_FILE).read_text())["verdict"] == "error"


def test_cli_report_bad_state_exits_2(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / ftr.STATE_FILE).write_text(json.dumps({"version": 0}), encoding="utf-8")
    first = _junit(tmp_path / "first.xml", ["failure"])
    assert ftr.main(_report_argv(first, out)) == ftr.EXIT_CONFIG


def test_cli_report_malformed_rerun_junit_exits_3(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / ftr.STATE_FILE).write_text(json.dumps(_state()), encoding="utf-8")
    (out / ftr.RERUN_JUNIT_FILE).write_text("<broken", encoding="utf-8")
    first = _junit(tmp_path / "first.xml", ["failure", "failure"])
    assert ftr.main(_report_argv(first, out)) == ftr.EXIT_EXTERNAL


def test_cli_rerun_malformed_cache_exits_3(tmp_path):
    lastfailed = tmp_path / "lf"
    lastfailed.write_text("{bad", encoding="utf-8")
    argv = ["rerun", "--out-dir", str(tmp_path / "o"), "--lastfailed", str(lastfailed)]
    assert ftr.main(argv, lambda args: 0) == ftr.EXIT_EXTERNAL


def test_cli_rerun_unwritable_out_dir_exits_3(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    argv = ["rerun", "--out-dir", str(blocker / "o"), "--lastfailed", str(tmp_path / "x")]
    assert ftr.main(argv, lambda args: 0) == ftr.EXIT_EXTERNAL


@pytest.mark.parametrize(
    "argv",
    [[], ["rerun"], ["rerun", "--out-dir", "o", "--max-tests", "0"], ["report", "--out-dir", "o"]],
)
def test_cli_bad_arguments_exit_2(argv):
    assert ftr.main(argv) == ftr.EXIT_CONFIG


def test_cli_help_exits_0():
    assert ftr.main(["--help"]) == ftr.EXIT_OK


def test_script_subprocess_exits_nonzero_on_missing_junit(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *_report_argv(tmp_path / "absent.xml", tmp_path / "o")],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == ftr.EXIT_EXTERNAL
    assert "JUnit report not found" in result.stdout


# --- workflow wiring ---------------------------------------------------------


def _test_steps() -> list[dict]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["test"]["steps"]


def test_workflow_rerun_follows_run_pytest_and_never_masks():
    steps = _test_steps()
    index = next(i for i, step in enumerate(steps) if step.get("id") == "run-pytest")
    main_step, rerun, report, upload = steps[index : index + 4]
    assert "continue-on-error" not in main_step
    gate = "failure() && steps.run-pytest.outcome == 'failure'"
    for step in (rerun, report, upload):
        assert step["if"] == gate
        assert "continue-on-error" not in step
    assert "flaky_test_report.py rerun" in rerun["run"]
    assert rerun["timeout-minutes"] <= 3
    assert "matrix.junit_file" not in rerun["run"]
    assert "flaky_test_report.py report" in report["run"]
    assert "--first-junit ${{ matrix.junit_file }}" in report["run"]
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"]["path"].endswith("flaky-tests.json")
