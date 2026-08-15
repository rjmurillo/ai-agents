"""The pre-PR sequence asks CI's generated-staleness question (issue #5079).

Two claims are separable and both need pinning.

The gate's own logic: ``main`` exits non-zero when a generator check reports
drift, exits zero with an examined count when both are clean, fails closed when
a checked script is absent, and stops at the first failure so a stale
``.claude/lib/`` never produces a meaningless ``build_all`` verdict.

The wiring: ``pre_pr_sequence`` reaches that logic. Unit tests on the validator
cannot see whether any caller invokes it, which is the shape that let
``check_skill_md_portability.py`` ship unwired (#4252), so the wiring class
below drives the real sequence and spies on the rebindable module attribute
that ``_root_only`` resolves at call time.

Coverage:

- positive: both checks clean gives exit 0 and prints the examined count.
- negative: a drift report gives exit 1; a missing script gives config exit 2;
  a non-directory root gives exit 2; a killed child gives external exit 3;
  removing the gate from ``_SEQUENCE`` fails the wiring test.
- edge: a failing first check leaves the second unrun, asserted on a marker
  file the second stub would have written.
"""

from __future__ import annotations

import io
import subprocess
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way production imports (issue #2223): prepend ``scripts/validation``
# to ``sys.path`` and import by bare name.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_generated_staleness
import pre_pr_sequence

GATE_NAME = "Generated Artifact Staleness"


def _stub(path: Path, body: str) -> None:
    """Write an executable-by-interpreter stub at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"import sys\n{body}\n", encoding="utf-8")


def _fake_repo(tmp_path: Path, sync_exit: int, build_exit: int) -> Path:
    """A root holding stubs at the two real script paths the gate invokes."""
    _stub(tmp_path / "scripts" / "sync_plugin_lib.py", f"sys.exit({sync_exit})")
    _stub(
        tmp_path / "build" / "scripts" / "build_all.py",
        "from pathlib import Path\n"
        "Path(__file__).with_name('build_all_ran.marker').write_text('1')\n"
        f"sys.exit({build_exit})",
    )
    return tmp_path


def _build_all_ran(repo_root: Path) -> bool:
    return (repo_root / "build" / "scripts" / "build_all_ran.marker").is_file()


class TestExitCodes:
    """A detected violation must reach the caller as a non-zero exit."""

    def test_a_clean_tree_exits_zero(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path, sync_exit=0, build_exit=0)

        assert check_generated_staleness.main([str(root)]) == 0

    def test_a_clean_run_reports_the_examined_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _fake_repo(tmp_path, sync_exit=0, build_exit=0)

        check_generated_staleness.main([str(root)])

        assert "2 generator check(s) examined" in capsys.readouterr().out

    def test_build_all_staleness_exits_one(self, tmp_path: Path) -> None:
        # build_all.py --check exits 2 on staleness; the gate maps every
        # non-zero child exit onto ADR-035 exit 1.
        root = _fake_repo(tmp_path, sync_exit=0, build_exit=2)

        assert check_generated_staleness.main([str(root)]) == 1

    def test_sync_drift_exits_one(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path, sync_exit=1, build_exit=0)

        assert check_generated_staleness.main([str(root)]) == 1

    def test_an_absent_script_is_a_config_error_not_drift(
        self, tmp_path: Path
    ) -> None:
        # The module's exit table promises 2 for an absent script: the gate
        # could not run and the script needs restoring, where the drift remedy
        # (regenerate and commit) would be the wrong action.
        root = _fake_repo(tmp_path, sync_exit=0, build_exit=0)
        (root / "build" / "scripts" / "build_all.py").unlink()

        assert check_generated_staleness.main([str(root)]) == 2

    def test_a_root_that_is_not_a_directory_is_a_config_error(
        self, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nope"

        assert check_generated_staleness.main([str(missing)]) == 2

    def test_a_killed_child_is_an_external_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ADR-035: a timeout kill means the tree was never scored, which is
        # external (3), not drift (1). The stub sleeps past a 1s cap.
        root = _fake_repo(tmp_path, sync_exit=0, build_exit=0)
        _stub(
            root / "scripts" / "sync_plugin_lib.py",
            "import time\ntime.sleep(30)\nsys.exit(0)",
        )
        monkeypatch.setattr(check_generated_staleness, "_GATE_BUDGET_SECONDS", 1.0)

        assert check_generated_staleness.main([str(root)]) == 3

    def test_a_killed_child_keeps_the_output_it_already_flushed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The timeout branch must preserve TimeoutExpired.stdout/.stderr and
        # append the kill marker, not discard the diagnosis the child already
        # emitted.
        root = _fake_repo(tmp_path, sync_exit=0, build_exit=0)

        class FakeProc:
            returncode = None

            def __init__(self) -> None:
                self.calls = 0

            def communicate(self, timeout: float | None = None) -> tuple[str, str]:
                self.calls += 1
                if self.calls == 1:
                    raise subprocess.TimeoutExpired(
                        cmd=["sync"],
                        timeout=timeout or 0.0,
                        output=b"partial diagnosis\n",
                        stderr=None,
                    )
                return ("late tail\n", "")

            def send_signal(self, _sig: int) -> None:
                return None

            def terminate(self) -> None:
                return None

            def kill(self) -> None:
                return None

        monkeypatch.setattr(
            check_generated_staleness.subprocess, "Popen", lambda *a, **k: FakeProc()
        )
        code, output = check_generated_staleness._run_check(
            root / "scripts" / "sync_plugin_lib.py", root, 1.0
        )

        assert code is None
        assert "partial diagnosis" in output
        assert "late tail" in output
        assert "exceeded 1.0s" in output


class TestBoundedGracefulTermination:
    """The gate is bounded as a whole, and expiry preserves child cleanup."""

    def test_the_gate_budget_is_positive_and_shared(self) -> None:
        # An unbounded child stalls pre_pr.py indefinitely for callers not
        # under the lefthook job cap (reliability review on PR #5088). The
        # budget is one aggregate so the worst case is the budget, not the
        # budget times the row count.
        assert check_generated_staleness._GATE_BUDGET_SECONDS > 0

    def test_budget_plus_grace_fits_inside_the_lefthook_cap(self) -> None:
        # lefthook kills the whole pre-pr-validation process tree at its cap,
        # without the SIGINT path, so the gate's worst case (budget + grace)
        # must leave the rest of the sequence room inside that cap. Parsed
        # from the live lefthook.yml so a cap change breaks this loudly.
        import yaml

        config = yaml.safe_load((REPO_ROOT / "lefthook.yml").read_text())

        def _jobs(node: object) -> list[dict]:
            found: list[dict] = []
            if isinstance(node, dict):
                if "jobs" in node:
                    for item in node["jobs"]:
                        found.extend(_jobs(item))
                if isinstance(node.get("group"), dict):
                    found.extend(_jobs(node["group"]))
                if "name" in node:
                    found.append(node)
            return found

        jobs = _jobs(config.get("pre-push", {}))
        caps = [j for j in jobs if j.get("name") == "pre-pr-validation"]
        assert caps, "pre-pr-validation job not found in lefthook.yml"
        timeout = caps[0]["timeout"]
        assert isinstance(timeout, str) and timeout.endswith("m")
        cap_seconds = int(timeout[:-1]) * 60

        worst_case = (
            check_generated_staleness._GATE_BUDGET_SECONDS
            + check_generated_staleness._TERMINATION_GRACE_SECONDS
        )
        assert worst_case <= cap_seconds / 2, (
            f"gate worst case {worst_case}s must leave at least half of the"
            f" {cap_seconds}s pre-pr-validation cap for the rest of the"
            f" sequence"
        )

    def test_an_exhausted_budget_reports_external_without_running_the_child(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _fake_repo(tmp_path, sync_exit=0, build_exit=0)
        monkeypatch.setattr(check_generated_staleness, "_GATE_BUDGET_SECONDS", -1.0)

        assert check_generated_staleness.main([str(root)]) == 3
        assert not _build_all_ran(root)

    def test_expiry_lets_the_child_finally_run(self, tmp_path: Path) -> None:
        # The whole point of graceful termination: SIGKILL would skip the
        # child's finally (which is what restores build_all's snapshot), but
        # SIGINT raises KeyboardInterrupt so the finally runs. The stub
        # mirrors that shape: it sleeps past the deadline and writes a marker
        # from its finally. The marker existing proves cleanup ran.
        if sys.platform == "win32":
            pytest.skip("POSIX SIGINT path; non-POSIX uses terminate()")
        child = tmp_path / "cleanup_child.py"
        marker = tmp_path / "cleanup_ran.marker"
        child.write_text(
            "import sys, time\n"
            "try:\n"
            "    time.sleep(30)\n"
            "finally:\n"
            f"    open({str(marker)!r}, 'w').write('1')\n",
            encoding="utf-8",
        )

        code, output = check_generated_staleness._run_check(child, tmp_path, 1.0)

        assert code is None
        assert marker.is_file(), "the child's finally never ran"
        assert "exceeded 1.0s" in output
        assert "honored the interrupt" in output


class TestGeneratorOrder:
    """sync before build, per .claude/rules/generated-artifacts.md."""

    def test_sync_is_checked_before_build_all(self) -> None:
        labels = [label for label, _ in check_generated_staleness._CHECKS]

        assert labels == ["sync_plugin_lib.py --check", "build_all.py --check"]

    def test_a_failing_sync_leaves_build_all_unrun(self, tmp_path: Path) -> None:
        # The isolating assertion is the point: pytest would pass on the exit
        # code alone even if build_all ran first and its verdict was compared
        # against a stale .claude/lib.
        root = _fake_repo(tmp_path, sync_exit=1, build_exit=0)

        assert check_generated_staleness.main([str(root)]) == 1
        assert not _build_all_ran(root)

    def test_the_control_run_does_reach_build_all(self, tmp_path: Path) -> None:
        # Without this control, the assertion above would pass against a gate
        # that never invokes build_all at all.
        root = _fake_repo(tmp_path, sync_exit=0, build_exit=0)

        check_generated_staleness.main([str(root)])

        assert _build_all_ran(root)


def _drive(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[Path]]:
    """Run the real sequence with a spy bound over the validator.

    ``_root_only`` resolves the validator out of ``globals()`` at call time
    rather than capturing it at import, so rebinding the module attribute is
    what makes this observable. Returns the emitted gate names and the repo
    roots the spy was handed.
    """
    seen: list[Path] = []

    def spy(repo_root: Path) -> bool:
        seen.append(repo_root)
        return True

    monkeypatch.setattr(pre_pr_sequence, "validate_generated_staleness", spy)

    names: list[str] = []

    def fake_run_validation(
        name: str,
        _state: SimpleNamespace,
        callback: Callable[[], bool],
        skip: bool = False,
    ) -> bool:
        names.append(name)
        if name == GATE_NAME and not skip:
            callback()
        return True

    args = SimpleNamespace(quick=False, skip_tests=False, verbose=False)
    state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
    with redirect_stdout(io.StringIO()):
        pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)
    return names, seen


class TestSequenceWiring:
    """pre_pr.py must reach the validator, not merely be able to."""

    def test_the_sequence_emits_the_staleness_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names, _seen = _drive(monkeypatch)

        assert GATE_NAME in names

    def test_the_gate_calls_the_validator_with_the_repo_root(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _names, seen = _drive(monkeypatch)

        assert seen == [REPO_ROOT]

    def test_the_gate_runs_after_the_deferral_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Different questions about the same file, and the deferral gate is the
        # one a reader is likely to mistake for this one. Keeping them adjacent
        # is the documented placement.
        names, _seen = _drive(monkeypatch)

        assert names.index(GATE_NAME) == names.index("Orphaned Build Deferrals") + 1
