"""Static-contract tests for bounded pytest-xdist parallelism in pytest.yml.

Issue #4854. The test job is a four-entry matrix (bulk, mutation, safe-push,
pr-autofix). Only bulk and mutation use xdist (`-n auto --dist loadfile`).
Safe-push and pr-autofix stay serial. No hard-coded worker count.

The coverage combine job downloads artifacts from all matrix legs and merges
them. The aggregate job gates on both test and coverage.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"

_MAIN_STEP = "Run pytest"
_WINDOWS_JOB = "test-windows-pwsh"
_WINDOWS_STEP = "Run Windows path-contract tests"

_EXPECTED_WORKERS = "auto"
_EXPECTED_DIST = "loadfile"
_BULK_IGNORES = {
    "tests/test_ai_review.py",
    "tests/test_verdict.py",
    "tests/test_quality_gate.py",
    "tests/skills/github/test_wait_for_unresolved_zero.py",
    "tests/skills/session-end/test_rework_warning.py",
    "tests/mutation",
    "tests/test_safe_push_pr_branch.py",
    "tests/test_mutation_workspace_signals.py",
    "tests/test_pr_autofix_late_live_state_gate.py",
}

# Any argv spelling that starts workers or picks a distribution mode.
_PARALLEL_TOKEN = re.compile(r"(?<!\S)(-n|--numprocesses|--dist)(?:[=\s]|$)")


def _load_workflow() -> dict[str, Any]:
    with _WORKFLOW.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _job(name: str) -> dict[str, Any]:
    return _load_workflow()["jobs"][name]


def _job_steps(job: str) -> list[dict[str, Any]]:
    return _load_workflow()["jobs"][job]["steps"]


def _matrix() -> list[dict[str, Any]]:
    return _job("test")["strategy"]["matrix"]["include"]


def _partition(name: str) -> dict[str, Any]:
    for entry in _matrix():
        if entry["partition"] == name:
            return entry
    raise AssertionError(f"partition {name!r} not found in matrix")


class TestMatrixStructure:
    """The test job is a four-partition matrix."""

    def test_node_uses_the_runner_system_ca(self) -> None:
        assert _job("test")["env"]["NODE_OPTIONS"] == "--use-system-ca"

    def test_local_act_runs_all_tests_without_paths_filter(self) -> None:
        check_paths = _job("check-paths")
        output = check_paths["outputs"]["python-changed"]
        filter_step = [s for s in check_paths["steps"] if s.get("id") == "filter"][0]
        assert "env.ACT == 'true'" in output
        assert "env.ACT != 'true'" in filter_step["if"]

    def test_four_partitions_exist(self) -> None:
        partitions = [e["partition"] for e in _matrix()]
        assert partitions == ["bulk", "mutation", "safe-push", "pr-autofix"]

    def test_job_name_includes_partition(self) -> None:
        name = _job("test")["name"]
        assert "pytest (${{ matrix.partition }})" in name

    def test_matrix_job_skips_when_python_inputs_are_unchanged(self) -> None:
        assert _job("test")["if"] == "needs.check-paths.outputs.python-changed == 'true'"

    def test_each_partition_has_coverage_and_junit(self) -> None:
        for entry in _matrix():
            assert "coverage_file" in entry, f"{entry['partition']} missing coverage_file"
            assert "junit_file" in entry, f"{entry['partition']} missing junit_file"
            assert "pytest_args" in entry, f"{entry['partition']} missing pytest_args"
        assert len({entry["coverage_file"] for entry in _matrix()}) == 4
        assert len({entry["junit_file"] for entry in _matrix()}) == 4

    def test_bulk_ignores_owned_files_and_mutation_and_safe_push_and_autofix(self) -> None:
        args = _partition("bulk")["pytest_args"]
        ignored = {
            token.removeprefix("--ignore=")
            for token in args.split()
            if token.startswith("--ignore=")
        }
        assert ignored == _BULK_IGNORES
        assert args.split()[-1] == "tests/"
        assert "-m" not in args, "CI must not drop integration-marked tests"

    def test_mutation_runs_only_tests_mutation(self) -> None:
        args = _partition("mutation")["pytest_args"]
        assert args.split() == ["-n", "auto", "--dist", "loadfile", "tests/mutation"]

    def test_safe_push_runs_process_sensitive_files(self) -> None:
        args = _partition("safe-push")["pytest_args"]
        assert args.split() == [
            "tests/test_safe_push_pr_branch.py",
            "tests/test_mutation_workspace_signals.py",
        ]

    def test_pr_autofix_runs_only_its_file(self) -> None:
        args = _partition("pr-autofix")["pytest_args"]
        assert args.strip() == "tests/test_pr_autofix_late_live_state_gate.py"


class TestXdistParallelism:
    """Only bulk and mutation use xdist; safe-push and pr-autofix stay serial."""

    def test_bulk_uses_xdist(self) -> None:
        args = _partition("bulk")["pytest_args"]
        assert "-n auto" in args
        assert "--dist loadfile" in args

    def test_mutation_uses_xdist(self) -> None:
        args = _partition("mutation")["pytest_args"]
        assert "-n auto" in args
        assert "--dist loadfile" in args

    def test_safe_push_stays_serial(self) -> None:
        args = _partition("safe-push")["pytest_args"]
        assert _PARALLEL_TOKEN.search(args) is None

    def test_pr_autofix_stays_serial(self) -> None:
        args = _partition("pr-autofix")["pytest_args"]
        assert _PARALLEL_TOKEN.search(args) is None

    def test_no_hard_coded_worker_count(self) -> None:
        for entry in _matrix():
            args = entry["pytest_args"]
            if "-n" in args:
                tokens = args.split()
                idx = tokens.index("-n")
                val = tokens[idx + 1]
                assert not val.lstrip("+-").isdigit(), (
                    f"partition {entry['partition']} hard-codes worker count {val!r}"
                )

    def test_windows_path_contract_job_stays_serial(self) -> None:
        steps = _job_steps(_WINDOWS_JOB)
        win_step = [s for s in steps if s.get("name") == _WINDOWS_STEP][0]
        run = win_step["run"]
        assert _PARALLEL_TOKEN.search(run) is None


class TestRunPytestStep:
    """The shared Run pytest step uses matrix data."""

    def test_run_step_uses_matrix_pytest_args(self) -> None:
        steps = _job_steps("test")
        run_step = [s for s in steps if s.get("name") == _MAIN_STEP][0]
        run = run_step["run"]
        assert "${{ matrix.pytest_args }}" in run

    def test_run_step_uses_matrix_coverage_file(self) -> None:
        steps = _job_steps("test")
        run_step = [s for s in steps if s.get("name") == _MAIN_STEP][0]
        env = run_step.get("env", {})
        assert "${{ matrix.coverage_file }}" in env.get("COVERAGE_FILE", "")

    def test_run_step_uses_matrix_junit_file(self) -> None:
        steps = _job_steps("test")
        run_step = [s for s in steps if s.get("name") == _MAIN_STEP][0]
        run = run_step["run"]
        assert "${{ matrix.junit_file }}" in run

    def test_run_step_has_cov_and_cov_report(self) -> None:
        steps = _job_steps("test")
        run_step = [s for s in steps if s.get("name") == _MAIN_STEP][0]
        run = run_step["run"]
        assert "--cov" in run
        assert "--cov-report=" in run

    def test_run_step_has_no_cov_branch(self) -> None:
        steps = _job_steps("test")
        run_step = [s for s in steps if s.get("name") == _MAIN_STEP][0]
        run = run_step["run"]
        assert "--cov-branch" not in run


class TestArtifactUpload:
    """Each matrix leg uploads a unique artifact with include-hidden-files."""

    def test_upload_artifact_name_includes_partition(self) -> None:
        steps = _job_steps("test")
        upload = [s for s in steps if s.get("name") == "Upload test results"][0]
        assert "pytest-results-${{ matrix.partition }}" in upload["with"]["name"]

    def test_upload_includes_hidden_files(self) -> None:
        steps = _job_steps("test")
        upload = [s for s in steps if s.get("name") == "Upload test results"][0]
        assert upload["with"].get("include-hidden-files") is True

    def test_upload_overwrites_prior_attempt_artifact(self) -> None:
        steps = _job_steps("test")
        upload = [s for s in steps if s.get("name") == "Upload test results"][0]
        assert upload["with"].get("overwrite") is True


class TestCoverageJob:
    """The coverage combine job merges all partition data."""

    def test_coverage_job_exists(self) -> None:
        assert "coverage" in _load_workflow()["jobs"]

    def test_coverage_job_name(self) -> None:
        assert _job("coverage")["name"] == "Combine Python coverage"

    def test_coverage_job_needs_test(self) -> None:
        needs = _job("coverage")["needs"]
        assert "test" in needs
        assert "check-paths" in needs

    def test_coverage_job_timeout(self) -> None:
        assert _job("coverage")["timeout-minutes"] == 10

    def test_coverage_downloads_with_pattern_and_merge(self) -> None:
        steps = _job("coverage")["steps"]
        dl = [s for s in steps if s.get("name") == "Download partition artifacts"][0]
        assert dl["with"]["pattern"] == "pytest-results-*"
        assert dl["with"]["merge-multiple"] is True

    def test_combine_uses_four_main_data_inputs(self) -> None:
        steps = _job("coverage")["steps"]
        combine = [s for s in steps if s.get("name") == "Combine coverage data"][0]
        run = combine["run"]
        assert re.findall(r"--main-data\s+(\S+)", run) == [
            "artifacts/.coverage.bulk",
            "artifacts/.coverage.mutation",
            "artifacts/.coverage.safe-push",
            "artifacts/.coverage.pr-autofix",
        ]

    def test_combine_has_two_pin_inputs(self) -> None:
        steps = _job("coverage")["steps"]
        combine = [s for s in steps if s.get("name") == "Combine coverage data"][0]
        run = combine["run"]
        assert re.findall(r"--pin-data\s+(\S+)", run) == [
            "artifacts/.coverage.pin-verdict",
            "artifacts/.coverage.pin-req009",
        ]

    def test_combine_runs_coverage_xml(self) -> None:
        steps = _job("coverage")["steps"]
        combine = [s for s in steps if s.get("name") == "Combine coverage data"][0]
        run = combine["run"]
        assert "coverage xml" in run

    def test_coverage_uploads_final_artifact(self) -> None:
        steps = _job("coverage")["steps"]
        upload = [s for s in steps if s.get("name") == "Upload combined coverage"][0]
        assert upload["with"]["name"] == "pytest-results"
        assert upload["with"].get("overwrite") is True

    def test_no_shell_branching_in_combine(self) -> None:
        steps = _job("coverage")["steps"]
        combine = [s for s in steps if s.get("name") == "Combine coverage data"][0]
        run = combine["run"]
        for token in (" if ", " if[", "\nif ", "for ", "while ", "$(", "`"):
            assert token not in run


class TestAggregateJob:
    """The test-result aggregate job gates the required status check."""

    def test_aggregate_job_exists(self) -> None:
        assert "test-result" in _load_workflow()["jobs"]

    def test_aggregate_job_name(self) -> None:
        assert _job("test-result")["name"] == "Run Python Tests"

    def test_aggregate_runs_when_path_detection_fails(self) -> None:
        condition = _job("test-result")["if"]
        assert "always()" in condition
        assert "needs.check-paths.result != 'success'" in condition
        assert "needs.check-paths.outputs.python-changed == 'true'" in condition

    def test_skip_job_requires_successful_path_detection(self) -> None:
        condition = _job("skip-tests")["if"]
        assert condition == (
            "needs.check-paths.result == 'success' && "
            "needs.check-paths.outputs.python-changed != 'true'"
        )

    def test_aggregate_needs(self) -> None:
        needs = _job("test-result")["needs"]
        assert "check-paths" in needs
        assert "test" in needs
        assert "coverage" in needs

    def test_aggregate_uses_require_job_results(self) -> None:
        steps = _job("test-result")["steps"]
        run_steps = [s for s in steps if isinstance(s.get("run"), str)]
        script_step = [s for s in run_steps if "require_job_results.py" in s["run"]][0]
        assert "PATH_RESULT" in script_step.get("env", {})
        assert "TEST_RESULT" in script_step.get("env", {})
        assert "COVERAGE_RESULT" in script_step.get("env", {})
        assert "--check PATH_RESULT success" in script_step["run"]

    def test_aggregate_timeout(self) -> None:
        assert _job("test-result")["timeout-minutes"] == 2


class TestMainFailureAlert:
    """main-failure-alert depends on test and test-result."""

    def test_alert_needs_test_and_aggregate(self) -> None:
        needs = _job("main-failure-alert")["needs"]
        assert "test" in needs
        assert "test-result" in needs
