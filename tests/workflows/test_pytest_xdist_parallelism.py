"""Static-contract tests for bounded pytest-xdist parallelism in pytest.yml.

Issue #4854. The test job is a five-entry matrix. The root and nested bulk
partitions plus mutation use xdist (`-n auto --dist loadfile`). Safe-push and
pr-autofix stay serial. No hard-coded worker count.

The coverage combine job downloads artifacts from all matrix legs and merges
them. The aggregate job gates on both test and coverage.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from scripts.ci import run_pytest_selected

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"

_MAIN_STEP = "Run pytest"
_WINDOWS_JOB = "test-windows-pwsh"
_WINDOWS_STEP = "Run Windows path-contract tests"

_EXPECTED_WORKERS = "auto"
_EXPECTED_DIST = "loadfile"
_ROOT_BULK_IGNORES = {
    "tests/test_ai_review.py",
    "tests/test_verdict.py",
    "tests/test_quality_gate.py",
    "tests/test_safe_push_pr_branch.py",
    "tests/test_mutation_workspace_signals.py",
    "tests/test_pr_autofix_late_live_state_gate.py",
}
_NESTED_BULK_IGNORES = {
    "tests/skills/github/test_wait_for_unresolved_zero.py",
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


def _partition_args(name: str) -> list[str]:
    """Partition pytest args, now owned by the Python runner rather than the matrix.

    Issue #5050 moved the per-partition argument lists out of the workflow matrix
    and into ``scripts/ci/run_pytest_selected.py`` so the full-vs-subset decision
    stays in testable Python (ADR-006). These contract tests follow them there.
    """
    return run_pytest_selected._PARTITION_FULL_ARGS[name]


class TestMatrixStructure:
    """The test job is a five-partition matrix."""

    def test_node_uses_the_runner_system_ca(self) -> None:
        assert _job("test")["env"]["NODE_OPTIONS"] == "--use-system-ca"

    def test_local_act_runs_all_tests_without_paths_filter(self) -> None:
        check_paths = _job("check-paths")
        output = check_paths["outputs"]["python-changed"]
        filter_step = [s for s in check_paths["steps"] if s.get("id") == "filter"][0]
        assert "env.ACT == 'true'" in output
        assert "env.ACT != 'true'" in filter_step["if"]

    def test_five_partitions_exist(self) -> None:
        partitions = [e["partition"] for e in _matrix()]
        assert partitions == [
            "bulk",
            "bulk-nested",
            "mutation",
            "safe-push",
            "pr-autofix",
        ]

    def test_job_name_includes_partition(self) -> None:
        name = _job("test")["name"]
        assert "pytest (${{ matrix.partition }})" in name

    def test_matrix_job_skips_when_python_inputs_are_unchanged(self) -> None:
        assert _job("test")["if"] == "needs.check-paths.outputs.python-changed == 'true'"

    def test_read_only_checkouts_do_not_persist_credentials(self) -> None:
        for job_name in ("coverage", "test-result"):
            checkout = next(
                step
                for step in _job_steps(job_name)
                if str(step.get("uses", "")).startswith("actions/checkout@")
            )
            assert checkout["with"]["persist-credentials"] is False

    def test_each_partition_has_coverage_and_junit(self) -> None:
        for entry in _matrix():
            assert "coverage_file" in entry, f"{entry['partition']} missing coverage_file"
            assert "junit_file" in entry, f"{entry['partition']} missing junit_file"
        assert len({entry["coverage_file"] for entry in _matrix()}) == 5
        assert len({entry["junit_file"] for entry in _matrix()}) == 5

    def test_every_partition_has_runner_args(self) -> None:
        matrix_partitions = {entry["partition"] for entry in _matrix()}
        assert matrix_partitions == set(run_pytest_selected._PARTITION_FULL_ARGS)

    def test_root_bulk_ignores_nested_and_owned_files(self) -> None:
        args = _partition_args("bulk")
        ignored = {
            token.removeprefix("--ignore=") for token in args if token.startswith("--ignore=")
        }
        assert ignored == _ROOT_BULK_IGNORES
        assert "--ignore-glob=tests/*/*" in args
        assert args[-1] == "tests/"
        assert "-m" not in args, "CI must not drop integration-marked tests"

    def test_nested_bulk_covers_every_non_mutation_test_directory(self) -> None:
        args = _partition_args("bulk-nested")
        ignored = {
            token.removeprefix("--ignore=") for token in args if token.startswith("--ignore=")
        }
        selected = {
            token
            for token in args
            if token.startswith("tests/") and not token.startswith("--ignore=")
        }
        expected = {
            f"tests/{path.name}"
            for path in (_WORKFLOW.parents[2] / "tests").iterdir()
            if path.is_dir() and path.name not in {"__pycache__", "mutation"}
        }
        assert ignored == _NESTED_BULK_IGNORES
        assert selected == expected

    def test_mutation_runs_only_tests_mutation(self) -> None:
        args = _partition_args("mutation")
        assert args == ["-n", "auto", "--dist", "loadfile", "tests/mutation"]

    def test_safe_push_runs_process_sensitive_files(self) -> None:
        args = _partition_args("safe-push")
        assert args == [
            "tests/test_safe_push_pr_branch.py",
            "tests/test_mutation_workspace_signals.py",
        ]

    def test_pr_autofix_runs_only_its_file(self) -> None:
        args = _partition_args("pr-autofix")
        assert args == ["tests/test_pr_autofix_late_live_state_gate.py"]


class TestXdistParallelism:
    """Bulk partitions and mutation use xdist; sensitive files stay serial."""

    def test_bulk_uses_xdist(self) -> None:
        args = _partition_args("bulk")
        assert args[:4] == ["-n", "auto", "--dist", "loadfile"]

    def test_nested_bulk_uses_xdist(self) -> None:
        args = _partition_args("bulk-nested")
        assert args[:4] == ["-n", "auto", "--dist", "loadfile"]

    def test_mutation_uses_xdist(self) -> None:
        args = _partition_args("mutation")
        assert args[:4] == ["-n", "auto", "--dist", "loadfile"]

    def test_safe_push_stays_serial(self) -> None:
        args = _partition_args("safe-push")
        assert "-n" not in args
        assert "--dist" not in args

    def test_pr_autofix_stays_serial(self) -> None:
        args = _partition_args("pr-autofix")
        assert "-n" not in args
        assert "--dist" not in args

    def test_no_hard_coded_worker_count(self) -> None:
        for partition, args in run_pytest_selected._PARTITION_FULL_ARGS.items():
            if "-n" in args:
                val = args[args.index("-n") + 1]
                assert not val.lstrip("+-").isdigit(), (
                    f"partition {partition} hard-codes worker count {val!r}"
                )

    def test_windows_path_contract_job_stays_serial(self) -> None:
        steps = _job_steps(_WINDOWS_JOB)
        win_step = [s for s in steps if s.get("name") == _WINDOWS_STEP][0]
        run = win_step["run"]
        assert _PARALLEL_TOKEN.search(run) is None


class TestRunPytestStep:
    """The shared Run pytest step uses matrix data."""

    def test_run_step_invokes_the_selection_runner(self) -> None:
        steps = _job_steps("test")
        run_step = [s for s in steps if s.get("name") == _MAIN_STEP][0]
        run = run_step["run"]
        assert "scripts/ci/run_pytest_selected.py" in run
        assert "--partition ${{ matrix.partition }}" in run

    def test_run_step_passes_selection_base(self) -> None:
        steps = _job_steps("test")
        run_step = [s for s in steps if s.get("name") == _MAIN_STEP][0]
        base = run_step.get("env", {}).get("PYTEST_SELECT_BASE", "")
        assert "github.event.pull_request.base.sha" in base
        assert "github.event.before" in base

    def test_run_step_passes_selection_head(self) -> None:
        """Issue #5378: without the pull request's own head SHA the diff would
        run against the synthetic merge commit and credit this pull request
        with base-branch changes."""
        steps = _job_steps("test")
        run_step = [s for s in steps if s.get("name") == _MAIN_STEP][0]
        head = run_step.get("env", {}).get("PYTEST_SELECT_HEAD", "")
        assert "github.event.pull_request.head.sha" in head
        assert "github.sha" in head

    def test_selection_refs_are_shas_not_branch_names(self) -> None:
        steps = _job_steps("test")
        run_step = [s for s in steps if s.get("name") == _MAIN_STEP][0]
        env = run_step.get("env", {})
        for name in ("PYTEST_SELECT_BASE", "PYTEST_SELECT_HEAD"):
            value = env.get(name, "")
            assert "base_ref" not in value, f"{name} must not use a mutable branch name"
            assert "ref_name" not in value, f"{name} must not use a mutable branch name"

    def test_checkout_depth_can_reach_both_selection_commits(self) -> None:
        """A shallow checkout cannot hold base.sha and head.sha, so the diff
        would fail and every run would fall back to the full suite."""
        steps = _job_steps("test")
        checkout = [s for s in steps if "actions/checkout" in s.get("uses", "")][0]
        assert checkout.get("with", {}).get("fetch-depth") == 0

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

    def test_combine_uses_five_main_data_inputs(self) -> None:
        steps = _job("coverage")["steps"]
        combine = [s for s in steps if s.get("name") == "Combine coverage data"][0]
        run = combine["run"]
        assert re.findall(r"--main-data\s+(\S+)", run) == [
            "artifacts/.coverage.bulk",
            "artifacts/.coverage.bulk-nested",
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
        """The gate must survive a failed dependency but not a cancelled run.

        `!cancelled()` replaced `always()` for #5097: both run when a
        dependency failed or was skipped, but `always()` also ran during
        cancellation and published a red required check for a superseded run.
        `tests/workflows/test_aggregator_cancellation_guard.py` carries the
        full contract.
        """
        condition = _job("test-result")["if"]
        assert "!cancelled()" in condition
        assert "always()" not in condition
        assert "needs.check-paths.result != 'success'" in condition
        assert "needs.check-paths.outputs.python-changed == 'true'" in condition

    def test_skip_job_requires_successful_path_detection(self) -> None:
        condition = _job("skip-tests")["if"]
        assert condition == (
            "!cancelled() && "
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
