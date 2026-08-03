"""Tests for the CI-permissions mutation harness.

The harness previously scored *any* non-zero pytest exit as a kill. pytest
exits 4 on an unresolvable nodeid and 5 when nothing is collected, so four
mutations that pointed at a renamed test class were recorded as DEAD without a
single test running. These tests pin the classification and add two regression
guards: every mutation literal must be present exactly once, and every
``test_filter`` must actually collect.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "scripts/ci/mutation_harness_ciperms.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("mutation_harness_ciperms", HARNESS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Register before exec: @dataclass resolves its own module via sys.modules
    # and raises AttributeError on None if this is skipped.
    sys.modules["mutation_harness_ciperms"] = module
    spec.loader.exec_module(module)
    return module


harness = _load_harness()


def _proc(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["pytest"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestClassify:
    """Positive, negative, and edge outcomes for a pytest run."""

    def test_exit_1_is_dead(self):
        outcome, note = harness._classify(_proc(1, stdout="1 failed"))
        assert outcome == harness.DEAD
        assert note == ""

    def test_exit_0_is_survived(self):
        outcome, note = harness._classify(_proc(0, stdout="3 passed"))
        assert outcome == harness.SURVIVED
        assert note == ""

    @pytest.mark.parametrize(
        ("code", "fragment"),
        [
            (2, "interrupted"),
            (3, "internal error"),
            (4, "usage error"),
            (5, "no tests collected"),
        ],
    )
    def test_documented_non_verdict_codes_are_not_run(self, code, fragment):
        outcome, note = harness._classify(_proc(code, stderr="ERROR: no match"))
        assert outcome == harness.NOT_RUN
        assert f"pytest exited {code}" in note
        assert fragment in note

    def test_exit_4_is_the_regression_case(self):
        """A typo'd nodeid must never read as a kill."""
        outcome, _ = harness._classify(
            _proc(4, stderr="ERROR: not found: ...::TestGone (no match in any of [...])")
        )
        assert outcome != harness.DEAD

    def test_unknown_code_is_not_run(self):
        outcome, note = harness._classify(_proc(99))
        assert outcome == harness.NOT_RUN
        assert "unrecognized pytest exit code" in note

    def test_note_carries_the_last_output_line(self):
        _, note = harness._classify(_proc(4, stderr="first line\nlast line"))
        assert note.endswith("last line")

    def test_stderr_wins_over_stdout(self):
        _, note = harness._classify(_proc(5, stdout="from stdout", stderr="from stderr"))
        assert "from stderr" in note
        assert "from stdout" not in note

    def test_stdout_used_when_stderr_empty(self):
        _, note = harness._classify(_proc(5, stdout="collected 0 items"))
        assert "collected 0 items" in note

    def test_silent_process_gets_a_placeholder(self):
        _, note = harness._classify(_proc(5))
        assert note.endswith("no output")


class TestApplyMutation:
    """The mutate-run-restore cycle, with pytest mocked out."""

    def _mutation(self, tmp_path, old=b"target\n", new=b"changed\n", body=b"target\n"):
        target = tmp_path / "sample.py"
        target.write_bytes(body)
        return harness.Mutation(
            description="unit",
            target_file=target,
            old_bytes=old,
            new_bytes=new,
            test_filter="tests/does_not_matter.py::test_x",
        )

    def test_absent_literal_does_not_apply(self, tmp_path):
        mutation = self._mutation(tmp_path, old=b"missing\n")
        result = harness.apply_mutation(mutation)
        assert result.outcome == harness.DID_NOT_APPLY
        assert "not found" in result.note

    def test_ambiguous_literal_does_not_apply(self, tmp_path):
        mutation = self._mutation(tmp_path, body=b"target\ntarget\n")
        result = harness.apply_mutation(mutation)
        assert result.outcome == harness.DID_NOT_APPLY
        assert "found 2 occurrences" in result.note

    def test_noop_patch_does_not_apply(self, tmp_path):
        mutation = self._mutation(tmp_path, new=b"target\n")
        result = harness.apply_mutation(mutation)
        assert result.outcome == harness.DID_NOT_APPLY
        assert "byte-identical" in result.note

    def test_file_is_mutated_during_the_run_and_restored_after(
        self, tmp_path, monkeypatch
    ):
        mutation = self._mutation(tmp_path)
        seen: list[bytes] = []

        def fake_run(_test_filter):
            seen.append(mutation.target_file.read_bytes())
            return _proc(1)

        monkeypatch.setattr(harness, "_run_tests", fake_run)
        result = harness.apply_mutation(mutation)

        assert seen == [b"changed\n"], "test ran against the unmutated file"
        assert mutation.target_file.read_bytes() == b"target\n"
        assert result.outcome == harness.DEAD

    def test_surviving_mutant_is_reported(self, tmp_path, monkeypatch):
        mutation = self._mutation(tmp_path)
        monkeypatch.setattr(harness, "_run_tests", lambda _f: _proc(0))
        assert harness.apply_mutation(mutation).outcome == harness.SURVIVED

    def test_file_is_restored_when_the_run_raises(self, tmp_path, monkeypatch):
        mutation = self._mutation(tmp_path)

        def boom(_test_filter):
            raise RuntimeError("pytest blew up")

        monkeypatch.setattr(harness, "_run_tests", boom)
        with pytest.raises(RuntimeError):
            harness.apply_mutation(mutation)
        assert mutation.target_file.read_bytes() == b"target\n"


class TestVerifyRepoRoot:
    def test_real_worktree_passes(self):
        harness._verify_repo_root()

    def test_missing_git_dir_is_a_config_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(harness, "REPO_ROOT", tmp_path)
        with pytest.raises(SystemExit) as excinfo:
            harness._verify_repo_root()
        assert "not a git worktree" in str(excinfo.value)


class TestMainExitCodes:
    """main() must fail on every non-DEAD class, not just SURVIVED."""

    def _run_main(self, monkeypatch, outcomes):
        mutations = [
            harness.Mutation(
                description=f"m{i}",
                target_file=REPO_ROOT / "unused",
                old_bytes=b"a",
                new_bytes=b"b",
                test_filter="x",
            )
            for i, _ in enumerate(outcomes)
        ]
        monkeypatch.setattr(harness, "build_mutations", lambda: mutations)
        pairs = iter(zip(mutations, outcomes, strict=True))
        monkeypatch.setattr(
            harness,
            "apply_mutation",
            lambda _m: harness.Result(*next(pairs)),
        )
        return harness.main()

    def test_all_dead_exits_zero(self, monkeypatch):
        assert self._run_main(monkeypatch, [harness.DEAD, harness.DEAD]) == 0

    @pytest.mark.parametrize(
        "outcome", [harness.SURVIVED, harness.NOT_RUN, harness.DID_NOT_APPLY]
    )
    def test_any_non_dead_outcome_fails(self, monkeypatch, outcome):
        assert self._run_main(monkeypatch, [harness.DEAD, outcome]) == 1

    def test_not_run_is_reported_as_unmeasured(self, monkeypatch, capsys):
        self._run_main(monkeypatch, [harness.NOT_RUN])
        assert "unmeasured rather than killed" in capsys.readouterr().out


class TestMutationsAreRunnable:
    """Regression guards for the two silent-failure classes.

    Literal drift shows up as DID-NOT-APPLY and a renamed test shows up as
    NOT-RUN. Both used to be invisible; these catch them at test time instead
    of at harness time.
    """

    @pytest.mark.parametrize("mutation", harness.build_mutations(), ids=lambda m: m.description[:2])
    def test_target_literal_is_present_exactly_once(self, mutation):
        body = mutation.target_file.read_bytes()
        assert body.count(mutation.old_bytes) == 1, (
            f"{mutation.description}: literal appears "
            f"{body.count(mutation.old_bytes)} times in {mutation.target_file.name}"
        )

    @pytest.mark.parametrize("mutation", harness.build_mutations(), ids=lambda m: m.description[:2])
    def test_patch_changes_the_file(self, mutation):
        assert mutation.old_bytes != mutation.new_bytes

    def test_every_test_filter_collects(self):
        """The bug that started this: a nodeid that resolves to nothing.

        pytest exits 4 on a bad nodeid, which the old harness scored as a kill.
        Collecting each filter proves the nodeid is real before the harness
        ever depends on its exit code.
        """
        filters = sorted({m.test_filter for m in harness.build_mutations()})
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header", *filters],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=REPO_ROOT,
        )
        assert proc.returncode == 0, (
            f"pytest exited {proc.returncode} collecting {filters}:\n"
            f"{proc.stderr or proc.stdout}"
        )
