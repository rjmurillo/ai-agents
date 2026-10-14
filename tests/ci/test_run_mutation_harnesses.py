"""Every mutation harness runs in a gate, and a failure names its harness (issue #5538).

``mutation_harness_*.py`` under ``tests/mutation/`` proves that a guard test
kills the defect it guards. Nothing ran them, so a stale selector (#5534) sat on
main unreported. ``scripts/ci/run_mutation_harnesses.py`` is the one caller. It
discovers harnesses by glob, so a harness added tomorrow is wired by being
added, and ``mutation-harness-guard`` in ``pytest.yml`` runs it on every event.

Three claims, one section each:

1. Discovery: the runner finds every harness and only harnesses.
2. Verdicts: a pass, a survivor, an unapplied anchor, a crash and a hang each
   produce a distinct, named result, and one failure does not hide the rest.
3. Wiring: the workflow job exists, has no path gate, takes no harness list,
   and ``test-result`` needs it. The YAML is parsed, never substring-matched
   (``.claude/rules/testing.md`` MUST 9).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci import run_mutation_harnesses as runner

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pytest.yml"
JOB = "mutation-harness-guard"
RUNNER_SCRIPT = "scripts/ci/run_mutation_harnesses.py"


def _write(root: Path, name: str, body: str) -> Path:
    path = root / "tests" / "mutation" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


PASSING = """
    print("All mutants killed. Tests are load-bearing.")
"""

SURVIVOR = """
    import sys
    print("--- Mutant: drop the guard ---")
    print("SURVIVING MUTANT: 'drop the guard' - tests passed, mutation undetected")
    sys.exit(1)
"""


class TestDiscovery:
    def test_finds_harnesses_sorted(self, tmp_path: Path) -> None:
        _write(tmp_path, "mutation_harness_2.py", PASSING)
        _write(tmp_path, "mutation_harness_1.py", PASSING)

        found = [p.name for p in runner.discover(tmp_path)]

        assert found == ["mutation_harness_1.py", "mutation_harness_2.py"]

    def test_ignores_helpers_and_pytest_modules(self, tmp_path: Path) -> None:
        _write(tmp_path, "mutation_harness_1.py", PASSING)
        _write(tmp_path, "_adr_debate_harness.py", PASSING)
        _write(tmp_path, "test_mutate_x.py", PASSING)
        _write(tmp_path, "conftest.py", PASSING)

        assert [p.name for p in runner.discover(tmp_path)] == ["mutation_harness_1.py"]

    def test_empty_tree_is_a_usage_error_not_a_pass(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = runner.main(["--root", str(tmp_path)])

        assert code == runner.EXIT_USAGE
        assert "no mutation_harness_*.py" in capsys.readouterr().err

    def test_list_prints_names_without_running(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        marker = tmp_path / "ran"
        _write(tmp_path, "mutation_harness_1.py", f"open({str(marker)!r}, 'w').close()")

        code = runner.main(["--root", str(tmp_path), "--list"])

        assert code == runner.EXIT_SUCCESS
        assert capsys.readouterr().out.split() == ["mutation_harness_1.py"]
        assert not marker.exists()

    def test_real_tree_has_harnesses_and_all_are_discovered(self) -> None:
        on_disk = sorted((REPO_ROOT / "tests" / "mutation").glob("mutation_harness_*.py"))

        assert on_disk, "tests/mutation holds no harness; the gate would pass on nothing"
        assert runner.discover(REPO_ROOT) == on_disk


class TestAddedHarnessIsRun:
    """A new harness file is wired by existing: the runner executes it unprompted."""

    def test_new_harness_runs_without_any_registration(self, tmp_path: Path) -> None:
        marker = tmp_path / "ran-new"
        _write(tmp_path, "mutation_harness_old.py", PASSING)
        assert runner.main(["--root", str(tmp_path)]) == runner.EXIT_SUCCESS
        assert not marker.exists()

        _write(tmp_path, "mutation_harness_new.py", f"open({str(marker)!r}, 'w').close()")

        assert runner.main(["--root", str(tmp_path)]) == runner.EXIT_SUCCESS
        assert marker.exists()

    def test_new_failing_harness_turns_the_gate_red(self, tmp_path: Path) -> None:
        _write(tmp_path, "mutation_harness_old.py", PASSING)
        _write(tmp_path, "mutation_harness_new.py", SURVIVOR)

        assert runner.main(["--root", str(tmp_path)]) == runner.EXIT_HARNESS_FAILED


class TestVerdicts:
    def test_passing_harness_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, "mutation_harness_ok.py", PASSING)

        code = runner.main(["--root", str(tmp_path)])

        out = capsys.readouterr().out
        assert code == runner.EXIT_SUCCESS
        assert "PASS mutation_harness_ok.py" in out
        assert "1/1 mutation harnesses passed" in out

    def test_survivor_is_named_with_its_harness_and_mutant(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, "mutation_harness_weak.py", SURVIVOR)

        code = runner.main(["--root", str(tmp_path)])

        out = capsys.readouterr().out
        assert code == runner.EXIT_HARNESS_FAILED
        assert "::error title=Mutation harness mutation_harness_weak.py::SURVIVED" in out
        assert "FAIL mutation_harness_weak.py: SURVIVED" in out
        assert "SURVIVING MUTANT: 'drop the guard'" in out
        assert "  SURVIVED: mutation_harness_weak.py" in out

    def test_survivor_with_exit_two_is_still_a_survivor(self, tmp_path: Path) -> None:
        body = """
            import sys
            print("  M3 drop one ratchet: SURVIVED (VACUOUS) :: x")
            sys.exit(2)
        """
        _write(tmp_path, "mutation_harness_two.py", body)

        result = runner.run_harness(
            tmp_path / "tests/mutation/mutation_harness_two.py", tmp_path, 30
        )

        assert result.outcome == runner.SURVIVED
        assert result.evidence == ("M3 drop one ratchet: SURVIVED (VACUOUS) :: x",)

    def test_did_not_apply_is_not_called_a_survivor(self, tmp_path: Path) -> None:
        body = """
            import sys
            print("  DID-NOT-APPLY: pattern not found in target file")
            print("SURVIVED:      0")
            sys.exit(1)
        """
        path = _write(tmp_path, "mutation_harness_stale.py", body)

        result = runner.run_harness(path, tmp_path, 30)

        assert result.outcome == runner.DID_NOT_APPLY
        assert result.evidence == ("DID-NOT-APPLY: pattern not found in target file",)

    def test_crash_with_a_message_is_an_error_carrying_the_message(self, tmp_path: Path) -> None:
        body = """
            raise SystemExit("ANCHOR MISSING in pre_pr_sequence.py: 'x'")
        """
        path = _write(tmp_path, "mutation_harness_crash.py", body)

        result = runner.run_harness(path, tmp_path, 30)

        assert result.outcome == runner.ERROR
        assert any("ANCHOR MISSING in pre_pr_sequence.py" in line for line in result.evidence)

    def test_inverted_control_and_zero_count_alone_are_not_survivors(self) -> None:
        output = (
            "  [ctl] SURVIVED (inverted control, expected)\n"
            "  SURVIVED: expected SURVIVED, pytest exit 0\n"
            "SURVIVED:      0\n"
            "Traceback: boom\n"
        )

        outcome, evidence = runner.classify_failure(output)

        assert outcome == runner.ERROR
        assert "Traceback: boom" in evidence

    def test_nonzero_survivor_count_is_a_survivor(self) -> None:
        outcome, evidence = runner.classify_failure("SURVIVED:      2\n")

        assert outcome == runner.SURVIVED
        assert evidence == ("SURVIVED:      2",)

    def test_hang_is_a_timeout_not_a_pass(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "mutation_harness_hang.py", "import time\ntime.sleep(60)\n")

        result = runner.run_harness(path, tmp_path, 1)

        assert result.outcome == runner.TIMEOUT
        assert "no exit after 1s" in result.evidence[0]

    @pytest.mark.parametrize(
        ("stream", "expected"),
        [(None, ""), ("text", "text"), (b"bytes", "bytes"), (b"bad\xff", "bad\ufffd")],
    )
    def test_timeout_stream_text_handles_none_str_and_bytes(
        self, stream: str | bytes | None, expected: str
    ) -> None:
        assert runner._text(stream) == expected

    def test_one_failure_does_not_hide_a_later_harness(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        marker = tmp_path / "ran-after"
        _write(tmp_path, "mutation_harness_a_fails.py", SURVIVOR)
        _write(tmp_path, "mutation_harness_b_after.py", f"open({str(marker)!r}, 'w').close()")

        code = runner.main(["--root", str(tmp_path)])

        out = capsys.readouterr().out
        assert code == runner.EXIT_HARNESS_FAILED
        assert marker.exists()
        assert "PASS mutation_harness_b_after.py" in out
        assert "1/2 mutation harnesses passed" in out

    def test_harness_sees_the_scanned_root_as_cwd_and_pythonpath(self, tmp_path: Path) -> None:
        probe = tmp_path / "probe.txt"
        body = f"""
            import os
            from pathlib import Path
            Path({str(probe)!r}).write_text(os.getcwd() + "|" + os.environ["PYTHONPATH"])
        """
        path = _write(tmp_path, "mutation_harness_env.py", body)

        assert runner.run_harness(path, tmp_path, 30).passed
        assert probe.read_text(encoding="utf-8") == f"{tmp_path.resolve()}|{tmp_path}"


def _jobs() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _run_lines(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in job["steps"] if "run" in step]


class TestWorkflowWiring:
    def test_job_has_no_path_gate(self) -> None:
        job = _jobs()[JOB]

        assert "needs" not in job
        assert "if" not in job

    def test_job_runs_the_runner_once_with_no_harness_filter(self) -> None:
        lines = [line for line in _run_lines(_jobs()[JOB]) if RUNNER_SCRIPT in line]

        assert len(lines) == 1
        tokens = lines[0].split()
        assert tokens[tokens.index(RUNNER_SCRIPT) + 1 :] == []

    def test_job_uses_the_dev_extra_the_harnesses_need(self) -> None:
        line = next(line for line in _run_lines(_jobs()[JOB]) if RUNNER_SCRIPT in line)

        assert line.startswith("uv run --frozen --extra dev python ")

    def test_job_name_is_unique(self) -> None:
        jobs = _jobs()
        names = [j.get("name", key) for key, j in jobs.items()]

        assert names.count(jobs[JOB]["name"]) == 1

    def test_aggregate_requires_the_job_to_succeed(self) -> None:
        aggregate = _jobs()["test-result"]
        script = next(
            step for step in aggregate["steps"] if "require_job_results.py" in step.get("run", "")
        )

        assert JOB in aggregate["needs"]
        assert f"needs.{JOB}.result" in script["env"]["MUTATION_HARNESS_RESULT"]
        assert "--check MUTATION_HARNESS_RESULT success" in script["run"]

    def test_job_timeout_covers_the_runner_budget(self) -> None:
        job = _jobs()[JOB]

        assert job["timeout-minutes"] * 60 > runner.DEFAULT_TIMEOUT_SECONDS
