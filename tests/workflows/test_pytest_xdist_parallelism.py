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

import pytest
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


def _selected_dirs(args: list[str]) -> set[str]:
    return {t for t in args if t.startswith("tests/") and not t.startswith("--ignore=")}


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
    """The test job is a six-partition matrix."""

    def test_node_uses_the_runner_system_ca(self) -> None:
        assert _job("test")["env"]["NODE_OPTIONS"] == "--use-system-ca"

    def test_local_act_runs_all_tests_without_paths_filter(self) -> None:
        check_paths = _job("check-paths")
        output = check_paths["outputs"]["python-changed"]
        filter_step = [s for s in check_paths["steps"] if s.get("id") == "filter"][0]
        assert "env.ACT == 'true'" in output
        assert "env.ACT != 'true'" in filter_step["if"]

    def test_six_partitions_exist(self) -> None:
        partitions = [e["partition"] for e in _matrix()]
        assert partitions == [
            "bulk",
            "bulk-nested",
            "bulk-nested-ci",
            "mutation",
            "safe-push",
            "pr-autofix",
        ]

    def test_job_name_includes_partition(self) -> None:
        name = _job("test")["name"]
        assert "pytest (${{ matrix.partition }})" in name

    def test_matrix_job_is_not_gated_by_a_path_filter(self) -> None:
        """ADR-101 requirement 1: the partitions are part of the required chain.

        A job-level `if:` or a `needs:` on check-paths would let a path filter
        decide whether the tests behind the required context run at all.
        """
        job = _job("test")
        assert "if" not in job
        assert "needs" not in job

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
        assert len({entry["coverage_file"] for entry in _matrix()}) == 6
        assert len({entry["junit_file"] for entry in _matrix()}) == 6

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

    def test_nested_partitions_cover_every_non_mutation_directory_once(self) -> None:
        """The two nested legs together own each test directory exactly once."""
        first = _selected_dirs(_partition_args("bulk-nested"))
        second = _selected_dirs(_partition_args("bulk-nested-ci"))
        expected = {
            f"tests/{path.name}"
            for path in (_WORKFLOW.parents[2] / "tests").iterdir()
            if path.is_dir() and path.name not in {"__pycache__", "mutation"}
        }
        assert not first & second, f"directories run twice: {sorted(first & second)}"
        assert first | second == expected
        assert len(first) + len(second) == len(expected)

    def test_only_the_leg_that_owns_skills_ignores_the_pin_file(self) -> None:
        for partition, owns_skills in (("bulk-nested", False), ("bulk-nested-ci", True)):
            ignored = {
                token.removeprefix("--ignore=")
                for token in _partition_args(partition)
                if token.startswith("--ignore=")
            }
            assert ignored == (_NESTED_BULK_IGNORES if owns_skills else set())

    def test_classify_partition_agrees_with_the_nested_arg_lists(self) -> None:
        tests_root = _WORKFLOW.parents[2] / "tests"
        owners = {
            "bulk-nested": _selected_dirs(_partition_args("bulk-nested")),
            "bulk-nested-ci": _selected_dirs(_partition_args("bulk-nested-ci")),
        }
        for partition, dirs in owners.items():
            for directory in dirs:
                probe = f"{directory}/test_probe.py"
                assert run_pytest_selected.classify_partition(probe) == partition, probe
        assert (tests_root / "ci").is_dir()

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

    @pytest.mark.parametrize("partition", ["bulk-nested", "bulk-nested-ci"])
    def test_nested_bulk_uses_xdist(self, partition: str) -> None:
        args = _partition_args(partition)
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
        assert needs == "test"

    def test_coverage_job_is_not_gated_by_a_path_filter(self) -> None:
        job = _job("coverage")
        assert "check-paths" not in str(job["needs"])
        assert "python-changed" not in job["if"]
        assert "!cancelled()" in job["if"]
        assert "needs.test.result == 'success'" in job["if"]

    def test_coverage_job_timeout(self) -> None:
        assert _job("coverage")["timeout-minutes"] == 10

    def test_coverage_downloads_with_pattern_and_merge(self) -> None:
        steps = _job("coverage")["steps"]
        dl = [s for s in steps if s.get("name") == "Download partition artifacts"][0]
        assert dl["with"]["pattern"] == "pytest-results-*"
        assert dl["with"]["merge-multiple"] is True

    def test_combine_uses_six_main_data_inputs(self) -> None:
        steps = _job("coverage")["steps"]
        combine = [s for s in steps if s.get("name") == "Combine coverage data"][0]
        run = combine["run"]
        assert re.findall(r"--main-data\s+(\S+)", run) == [
            "artifacts/.coverage.bulk",
            "artifacts/.coverage.bulk-nested",
            "artifacts/.coverage.bulk-nested-ci",
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

    def test_aggregate_has_only_the_cancellation_condition(self) -> None:
        """The gate must survive a failed dependency but not a cancelled run.

        `!cancelled()` replaced `always()` for #5097: both run when a
        dependency failed or was skipped, but `always()` also ran during
        cancellation and published a red required check for a superseded run.
        `tests/workflows/test_aggregator_cancellation_guard.py` carries the
        full contract. ADR-101 requirement 1 adds the other half: nothing
        else may appear in the condition, because any other term is a
        condition sourced outside the chain's own logic.
        """
        condition = str(_job("test-result")["if"])
        assert condition.replace(" ", "") == "${{!cancelled()}}"
        assert "always()" not in condition
        assert "check-paths" not in condition
        assert "python-changed" not in condition

    def test_no_second_job_publishes_the_required_context(self) -> None:
        """A same-named pass-through is what ADR-101 requirement 1 removed."""
        jobs = _load_workflow()["jobs"]
        publishers = [key for key, job in jobs.items() if job.get("name") == "Run Python Tests"]
        assert publishers == ["test-result"]
        assert "skip-tests" not in jobs

    def test_aggregate_needs(self) -> None:
        needs = _job("test-result")["needs"]
        assert "check-paths" not in needs
        assert "test" in needs
        assert "coverage" in needs

    def test_aggregate_requires_every_dependency_to_have_succeeded(self) -> None:
        """A skipped dependency must fail the context, never pass it."""
        steps = _job("test-result")["steps"]
        run_steps = [s for s in steps if isinstance(s.get("run"), str)]
        script_step = [s for s in run_steps if "require_job_results.py" in s["run"]][0]
        env = script_step.get("env", {})
        needs = _job("test-result")["needs"]
        assert "PATH_RESULT" not in env
        assert "--check PATH_RESULT" not in script_step["run"]
        for dependency in needs:
            variable = {
                "test": "TEST_RESULT",
                "coverage": "COVERAGE_RESULT",
                "zero-collection-guard": "ZERO_COLLECTION_RESULT",
                "line-endings-guard": "LINE_ENDINGS_RESULT",
                "context-output-guard": "CONTEXT_OUTPUT_RESULT",
                "count-ratchet-guard": "COUNT_RATCHET_RESULT",
            }[dependency]
            assert f"needs.{dependency}.result" in env[variable]
            assert f"--check {variable} success" in script_step["run"]

    def test_aggregate_timeout(self) -> None:
        assert _job("test-result")["timeout-minutes"] == 2


class TestMainFailureAlert:
    """main-failure-alert depends on test and test-result."""

    def test_alert_needs_test_and_aggregate(self) -> None:
        needs = _job("main-failure-alert")["needs"]
        assert "test" in needs
        assert "test-result" in needs
