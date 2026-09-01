"""Deadline and termination behavior of the generated-staleness gate.

Split from ``test_check_generated_staleness.py`` (which keeps the exit-code,
ordering, echo, and wiring tests) when round-5 coverage pushed that module
past the 500-line test file-size ceiling.

Coverage:

- the aggregate budget is positive, and budget + grace fits inside half the
  live ``lefthook.yml`` pre-pr-validation cap, which must also declare the
  cap to the gate via the clamp environment variable;
- an exhausted budget or a spent outer-cap share reports EXTERNAL without
  spawning a child, with a control proving an unspent cap changes nothing;
- expiry lets the child's ``finally`` run (SIGINT), a child that ignores the
  interrupt is killed with a partial-writes warning, and a non-POSIX host
  terminates instead of signaling;
- a malformed clamp variable warns and falls back to the unclamped budget.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.validation.staleness_gate_helpers import (
    REPO_ROOT,
    build_all_ran,
    check_generated_staleness,
    fake_repo,
    no_ambient_outer_cap,  # noqa: F401  (autouse fixture)
)


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

        # The job declares its own cap to the gate so the runtime clamp can
        # key off it (review round 5). The declaration must equal the job's
        # actual timeout, or the clamp bounds against a fiction.
        declared = caps[0].get("env", {}).get(
            check_generated_staleness._OUTER_CAP_ENV
        )
        assert declared is not None, (
            f"pre-pr-validation must declare"
            f" {check_generated_staleness._OUTER_CAP_ENV}"
        )
        assert float(declared) == cap_seconds

    def test_an_exhausted_budget_reports_external_without_running_the_child(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = fake_repo(tmp_path, sync_exit=0, build_exit=0)
        monkeypatch.setattr(check_generated_staleness, "_GATE_BUDGET_SECONDS", -1.0)

        assert check_generated_staleness.main([str(root)]) == 3
        assert not build_all_ran(root)

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

    def test_a_child_that_ignores_the_interrupt_is_killed_with_a_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The escalation branch: a child that shrugs off SIGINT must still be
        # bounded, and the caller must be told the tree may hold partial
        # writes, because that is the one path where cleanup did not run.
        if sys.platform == "win32":
            pytest.skip("POSIX SIGINT path; non-POSIX uses terminate()")
        child = tmp_path / "stubborn_child.py"
        child.write_text(
            "import signal, sys, time\n"
            "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
            "print('armored', flush=True)\n"
            "time.sleep(60)\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            check_generated_staleness, "_TERMINATION_GRACE_SECONDS", 1.0
        )

        code, output = check_generated_staleness._run_check(child, tmp_path, 2.0)

        assert code is None
        assert "ignored the interrupt and was killed" in output
        assert "partial generated writes" in output

    def test_a_non_posix_host_terminates_instead_of_signaling(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Windows has no SIGINT delivery to a child; the fallback is
        # terminate(). This drives the branch with a fake so the suite pins
        # it on every platform: on expiry the non-POSIX path must call
        # terminate() and must not attempt a POSIX signal.
        class FakeProc:
            returncode = None

            def __init__(self) -> None:
                self.calls = 0
                self.terminated = False
                self.signals: list[int] = []

            def communicate(self, timeout: float | None = None) -> tuple[str, str]:
                self.calls += 1
                if self.calls == 1:
                    raise subprocess.TimeoutExpired(cmd=["x"], timeout=timeout or 0.0)
                return ("", "")

            def send_signal(self, sig: int) -> None:
                self.signals.append(sig)

            def terminate(self) -> None:
                self.terminated = True

            def kill(self) -> None:
                return None

        fake = FakeProc()
        monkeypatch.setattr(
            check_generated_staleness.subprocess, "Popen", lambda *a, **k: fake
        )
        monkeypatch.setattr(check_generated_staleness.os, "name", "nt")

        code, _output = check_generated_staleness._run_check(
            tmp_path / "any.py", tmp_path, 1.0
        )

        assert code is None
        assert fake.terminated, "non-POSIX expiry must call terminate()"
        assert fake.signals == [], "non-POSIX expiry must not send POSIX signals"

    def test_a_spent_outer_share_reports_external_without_running_the_child(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The round-5 clamp: the gate's clock starts when the sequence
        # reaches it, after earlier validations spent part of the same outer
        # lefthook timer. When the declared cap leaves less than the grace
        # window, spawning a child would invite the outer SIGKILL mid-write,
        # so the gate must refuse to spawn at all.
        root = fake_repo(tmp_path, sync_exit=0, build_exit=0)
        monkeypatch.setenv(check_generated_staleness._OUTER_CAP_ENV, "1")

        assert check_generated_staleness.main([str(root)]) == 3
        assert not build_all_ran(root)

    def test_an_unspent_outer_cap_leaves_the_gate_running(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Control for the clamp test: a freshly started process under the
        # real declared cap must behave exactly as with no clamp at all.
        root = fake_repo(tmp_path, sync_exit=0, build_exit=0)
        monkeypatch.setenv(check_generated_staleness._OUTER_CAP_ENV, "900")
        monkeypatch.setattr(
            check_generated_staleness, "_PROCESS_START", time.monotonic()
        )

        assert check_generated_staleness.main([str(root)]) == 0
        assert build_all_ran(root)

    def test_a_malformed_outer_cap_warns_and_disables_the_clamp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # A typo in the hook configuration must not block every contributor's
        # push: the clamp only tightens an already-bounded gate, so the
        # failure mode is a loud warning plus the unclamped budget.
        root = fake_repo(tmp_path, sync_exit=0, build_exit=0)
        monkeypatch.setenv(check_generated_staleness._OUTER_CAP_ENV, "banana")

        assert check_generated_staleness.main([str(root)]) == 0
        assert "[WARN]" in capsys.readouterr().err
