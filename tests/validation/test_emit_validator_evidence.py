"""The evidence emitter maps a job conclusion to a typed, bindable record.

ADR-113 decision 2, issue #5636. A green job that did no work must not read as a
pass, a pull request run must write nothing, and a written file must be one the
gate's own loader accepts and binds to the candidate.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validation import emit_validator_evidence as emitter
from scripts.validation.emit_validator_evidence import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_LOGIC,
    EXIT_OK,
    build_outcome,
    emits_for,
    main,
    write_evidence,
)
from scripts.validation.evidence import EvidenceState
from scripts.validation.promotion_evidence import (
    Candidate,
    EvidenceError,
    bind_records,
    load_evidence_dir,
)

SHA = "a" * 40
OTHER_SHA = "b" * 40
SCOPE = "job test-result on push"


def _outcome(status: str, ran: bool = True):
    return build_outcome(
        validator="run_python_tests", job_status=status, ran=ran, revision=SHA, scope=SCOPE
    )


@pytest.mark.parametrize(
    ("status", "ran", "state", "reason"),
    [
        ("success", True, EvidenceState.PASS, ""),
        ("success", False, EvidenceState.SKIP, "validator.not_run"),
        ("failure", True, EvidenceState.FAIL, "job.failed"),
        ("failure", False, EvidenceState.FAIL, "job.failed"),
        ("cancelled", True, EvidenceState.UNKNOWN, "job.cancelled"),
        ("skipped", True, EvidenceState.UNKNOWN, "job.status_unrecognized"),
        ("", True, EvidenceState.UNKNOWN, "job.status_unrecognized"),
        ("SUCCESS", True, EvidenceState.UNKNOWN, "job.status_unrecognized"),
    ],
)
def test_job_status_maps_to_the_typed_state(
    status: str, ran: bool, state: EvidenceState, reason: str
) -> None:
    outcome = _outcome(status, ran)
    assert (outcome.state, outcome.reason) == (state, reason)
    assert outcome.revision == SHA


def test_a_green_job_that_did_no_work_is_never_a_pass() -> None:
    assert _outcome("success", ran=False).state is not EvidenceState.PASS


def test_an_unrecognized_status_is_cleaned_before_it_is_echoed() -> None:
    outcome = _outcome("bad\nstatus\x1b[31m")
    assert "\n" not in outcome.detail
    assert "\x1b" not in outcome.detail


@pytest.mark.parametrize(
    ("event", "ref", "expected"),
    [
        ("push", "refs/heads/main", True),
        ("push", "refs/heads/feature", False),
        ("push", "refs/tags/v1", False),
        ("merge_group", "refs/heads/gh-readonly-queue/main/pr-1-abc", True),
        ("merge_group", "refs/heads/main", False),
        ("pull_request", "refs/pull/1/merge", False),
        ("workflow_dispatch", "refs/heads/main", False),
        ("schedule", "refs/heads/main", False),
        ("", "", False),
    ],
)
def test_only_default_branch_pushes_and_merge_queue_runs_emit(
    event: str, ref: str, expected: bool
) -> None:
    assert emits_for(event, ref, "main") is expected


def test_a_push_with_no_default_branch_name_emits_nothing() -> None:
    assert emits_for("push", "refs/heads/", "") is False


def test_a_written_file_loads_and_binds_to_the_candidate(tmp_path: Path) -> None:
    write_evidence(_outcome("success"), tmp_path)
    records, rejected = load_evidence_dir(tmp_path)
    assert rejected == ()
    bound = bind_records(records, Candidate(SHA), frozenset())
    assert [r.outcome.state for r in bound.bound] == [EvidenceState.PASS]


def test_a_written_file_for_another_commit_does_not_bind(tmp_path: Path) -> None:
    write_evidence(_outcome("success"), tmp_path)
    records, _ = load_evidence_dir(tmp_path)
    bound = bind_records(records, Candidate(OTHER_SHA), frozenset())
    assert bound.bound == ()
    assert bound.rejected[0].reason == "binding.revision_mismatch"


def test_the_file_is_named_for_the_validator(tmp_path: Path) -> None:
    path = write_evidence(_outcome("failure"), tmp_path / "nested")
    assert path.name == "run_python_tests.json"
    assert json.loads(path.read_text(encoding="utf-8"))["state"] == "FAIL"


def test_write_refuses_a_record_the_strict_parser_rejects(tmp_path: Path) -> None:
    with (
        patch.object(emitter, "parse_evidence", side_effect=EvidenceError("nope")),
        pytest.raises(EvidenceError),
    ):
        write_evidence(_outcome("success"), tmp_path)
    assert list(tmp_path.iterdir()) == []


def _argv(tmp_path: Path, **overrides: str) -> list[str]:
    values = {
        "--validator": "run_python_tests",
        "--job-status": "success",
        "--revision": SHA,
        "--event": "push",
        "--ref": "refs/heads/main",
        "--default-branch": "main",
        "--job-id": "test-result",
        "--output-dir": str(tmp_path / "out"),
        "--github-output": str(tmp_path / "gh_output"),
    }
    values.update(overrides)
    return [token for pair in values.items() for token in pair]


def test_cli_writes_the_file_and_reports_emitted(tmp_path: Path) -> None:
    assert main(_argv(tmp_path)) == EXIT_OK
    assert (tmp_path / "out" / "run_python_tests.json").is_file()
    assert (tmp_path / "gh_output").read_text(encoding="utf-8") == "emitted=true\n"


def test_cli_writes_nothing_for_a_pull_request_run(tmp_path: Path) -> None:
    code = main(_argv(tmp_path, **{"--event": "pull_request", "--ref": "refs/pull/1/merge"}))
    assert code == EXIT_OK
    assert not (tmp_path / "out").exists()
    assert (tmp_path / "gh_output").read_text(encoding="utf-8") == "emitted=false\n"


def test_cli_records_a_failed_job_as_fail_and_still_exits_zero(tmp_path: Path) -> None:
    assert main(_argv(tmp_path, **{"--job-status": "failure"})) == EXIT_OK
    written = json.loads((tmp_path / "out" / "run_python_tests.json").read_text(encoding="utf-8"))
    assert written["state"] == "FAIL"


def test_cli_records_a_short_circuit_as_skip(tmp_path: Path) -> None:
    assert main(_argv(tmp_path, **{"--ran": "false"})) == EXIT_OK
    written = json.loads((tmp_path / "out" / "run_python_tests.json").read_text(encoding="utf-8"))
    assert (written["state"], written["reason"]) == ("SKIP", "validator.not_run")


@pytest.mark.parametrize(
    "validator", ["../escape", "a/b", "A", "", " ", "x" * 101, "a.b", "a-b", "a\nb"]
)
def test_cli_refuses_a_validator_name_that_could_leave_the_directory(
    tmp_path: Path, validator: str
) -> None:
    assert main(_argv(tmp_path, **{"--validator": validator})) == EXIT_CONFIG
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("revision", ["", "abc", "A" * 40, "g" * 40, SHA + "0", SHA[:-1]])
def test_cli_refuses_a_revision_that_is_not_a_full_sha(tmp_path: Path, revision: str) -> None:
    assert main(_argv(tmp_path, **{"--revision": revision})) == EXIT_CONFIG


def test_cli_refuses_a_ran_value_that_is_not_a_boolean(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as stop:
        main(_argv(tmp_path, **{"--ran": "yes"}))
    assert stop.value.code == EXIT_CONFIG


def test_cli_reports_blocked_when_the_directory_cannot_be_written(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert main(_argv(tmp_path, **{"--output-dir": str(blocker / "sub")})) == EXIT_EXTERNAL


def test_cli_exits_one_when_the_parser_rejects_the_record(tmp_path: Path) -> None:
    with patch.object(emitter, "parse_evidence", side_effect=EvidenceError("bad")):
        assert main(_argv(tmp_path)) == EXIT_LOGIC


def test_cli_cleans_control_characters_out_of_the_scope(tmp_path: Path) -> None:
    assert main(_argv(tmp_path, **{"--job-id": "job\nid\x1b"})) == EXIT_OK
    written = json.loads((tmp_path / "out" / "run_python_tests.json").read_text(encoding="utf-8"))
    assert "\n" not in written["scope"]
    assert "\x1b" not in written["scope"]


def test_cli_bounds_a_very_long_scope(tmp_path: Path) -> None:
    assert main(_argv(tmp_path, **{"--job-id": "j" * 5000})) == EXIT_OK
    written = json.loads((tmp_path / "out" / "run_python_tests.json").read_text(encoding="utf-8"))
    assert len(written["scope"]) <= 200


def test_cli_runs_without_a_github_output_file(tmp_path: Path) -> None:
    argv = _argv(tmp_path)
    index = argv.index("--github-output")
    del argv[index : index + 2]
    assert main(argv) == EXIT_OK
    assert (tmp_path / "out" / "run_python_tests.json").is_file()


def test_the_script_runs_under_bare_python_from_another_directory(tmp_path: Path) -> None:
    """Jobs call it as `python3 scripts/validation/...` with nothing installed."""
    script = Path(emitter.__file__).resolve()
    result = subprocess.run(
        [sys.executable, "-S", str(script), *_argv(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == EXIT_OK, result.stderr
    assert (tmp_path / "out" / "run_python_tests.json").is_file()


def test_the_script_exits_two_for_a_bad_validator_name(tmp_path: Path) -> None:
    script = Path(emitter.__file__).resolve()
    result = subprocess.run(
        [sys.executable, "-S", str(script), *_argv(tmp_path, **{"--validator": "../x"})],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == EXIT_CONFIG
