"""The `count-ratchets` pre-push subcommand of git_hook_policy (issue #7070).

The job moved behind `git_hook_policy.py` so a managed container bounds it.
These tests pin the handler's contract:

- positive: a passing registry exits 0 and receives the clamped deadline.
- negative: a failing registry exits 1.
- edge: an absent `uv` (MissingScriptSkip) exits 2, matching
  `checks_ratchet.main`; outside a container the deadline is unchanged.
- registry: an explicit deadline reaches the concurrent runner, None falls
  back to `_AGGREGATE_TIMEOUT_SECONDS` read at call time, and setup time is
  spent from the deadline.
- reporting: a deadline hit names the deadline and temp storage, not a count
  violation; a real violation and a signaled child keep the count message.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import checks_ratchet
import git_hook_policy
from checks_common import MissingScriptSkip

_Results = dict[str, tuple[int, str, str]]


def _run(argv: list[str]) -> int:
    args = git_hook_policy.build_parser().parse_args(argv)
    return int(args.handler(args))


class TestCountRatchetsHandler:
    def test_passing_registry_exits_zero_with_the_clamped_deadline(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        seen: list[tuple[Path, float | None]] = []

        def fake_validate(root: Path, deadline: float | None = None) -> bool:
            seen.append((root, deadline))
            return True

        monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda _s: 150.0)
        monkeypatch.setattr(checks_ratchet, "validate_count_ratchets", fake_validate)

        assert _run(["--repo-root", str(tmp_path), "count-ratchets"]) == 0
        assert seen == [(tmp_path.resolve(), 150.0)]

    def test_outside_a_container_the_deadline_is_the_registry_constant(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        seen: list[float | None] = []

        def fake_validate(_root: Path, deadline: float | None = None) -> bool:
            seen.append(deadline)
            return True

        monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda s: s)
        monkeypatch.setattr(checks_ratchet, "validate_count_ratchets", fake_validate)

        assert _run(["--repo-root", str(tmp_path), "count-ratchets"]) == 0
        assert seen == [float(checks_ratchet._AGGREGATE_TIMEOUT_SECONDS)]

    def test_failing_registry_exits_one(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda s: s)
        monkeypatch.setattr(
            checks_ratchet, "validate_count_ratchets", lambda _root, _deadline=None: False
        )

        assert _run(["--repo-root", str(tmp_path), "count-ratchets"]) == 1

    def test_missing_uv_exits_two_and_names_the_cause(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def raise_skip(_root: Path, _deadline: float | None = None) -> bool:
            raise MissingScriptSkip("uv is not on PATH")

        monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda s: s)
        monkeypatch.setattr(checks_ratchet, "validate_count_ratchets", raise_skip)

        assert _run(["--repo-root", str(tmp_path), "count-ratchets"]) == 2
        assert "uv is not on PATH" in capsys.readouterr().err

    def test_the_real_container_clamp_is_below_the_watchdog(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """In a container the deadline must fire before the watchdog does.

        Runs the real clamp with container detection forced on, so a change to
        the clamp rule fails here. Setup is inside the deadline (see
        TestRegistryDeadlineParameter), so this margin is the whole margin.
        """
        import run_workflow_local_test

        monkeypatch.setattr(run_workflow_local_test, "_is_remote_container", lambda: True)
        clamped = git_hook_policy._container_clamped(
            float(checks_ratchet._AGGREGATE_TIMEOUT_SECONDS)
        )
        assert clamped < float(checks_ratchet._AGGREGATE_TIMEOUT_SECONDS)
        assert clamped < git_hook_policy.CONTAINER_PROCESS_CEILING_SECONDS

    def test_a_clamped_deadline_is_announced(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda _s: 150.0)
        monkeypatch.setattr(
            checks_ratchet, "validate_count_ratchets", lambda _root, _deadline=None: True
        )

        assert _run(["--repo-root", str(tmp_path), "count-ratchets"]) == 0
        assert "deadline clamped 600s -> 150s" in capsys.readouterr().err

    def test_an_unclamped_deadline_prints_no_clamp_line(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda s: s)
        monkeypatch.setattr(
            checks_ratchet, "validate_count_ratchets", lambda _root, _deadline=None: True
        )

        assert _run(["--repo-root", str(tmp_path), "count-ratchets"]) == 0
        assert "clamped" not in capsys.readouterr().err


class TestRegistryDeadlineParameter:
    @pytest.fixture
    def stubbed(self, monkeypatch: pytest.MonkeyPatch) -> list[float]:
        monkeypatch.setattr(checks_ratchet.shutil, "which", lambda _name: "/usr/bin/uv")
        monkeypatch.setattr(checks_ratchet, "_prepare_base_oid", lambda _root: "a" * 40)
        deadlines: list[float] = []

        def fake_run(_root: Path, _oid: str, deadline_seconds: float) -> dict:
            deadlines.append(deadline_seconds)
            return {r.job_name: (0, "", "") for r in checks_ratchet.RATCHETS}

        monkeypatch.setattr(checks_ratchet, "_run_ratchets", fake_run)
        return deadlines

    def test_explicit_deadline_reaches_the_runner(self, stubbed: list[float]) -> None:
        assert checks_ratchet.validate_count_ratchets(REPO_ROOT, 42.0) is True
        assert len(stubbed) == 1
        assert 41.0 < stubbed[0] <= 42.0

    def test_none_falls_back_to_the_patched_constant(
        self, stubbed: list[float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(checks_ratchet, "_AGGREGATE_TIMEOUT_SECONDS", 7)
        assert checks_ratchet.validate_count_ratchets(REPO_ROOT) is True
        assert len(stubbed) == 1
        assert 6.0 < stubbed[0] <= 7.0

    def test_setup_time_is_spent_from_the_deadline(
        self, stubbed: list[float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A slow base-ref fetch must not push the gate past the watchdog."""
        clock = iter([100.0, 130.0, 131.0, 131.0, 131.0])
        monkeypatch.setattr(checks_ratchet.time, "monotonic", lambda: next(clock))

        assert checks_ratchet.validate_count_ratchets(REPO_ROOT, 150.0) is True
        assert stubbed == [120.0]


class TestTimeoutIsNotACountViolation:
    """Issue #7070: a deadline hit must not read as N count failures."""

    @pytest.fixture
    def run_with(self, monkeypatch: pytest.MonkeyPatch) -> Callable[[_Results], None]:
        monkeypatch.setattr(checks_ratchet.shutil, "which", lambda _name: "/usr/bin/uv")
        monkeypatch.setattr(checks_ratchet, "_prepare_base_oid", lambda _root: "a" * 40)

        def apply(results: _Results) -> None:
            full = {r.job_name: (0, "", "") for r in checks_ratchet.RATCHETS}
            full.update(results)
            monkeypatch.setattr(checks_ratchet, "_run_ratchets", lambda *_a: full)

        return apply

    def test_timeouts_name_the_deadline_not_the_counts(
        self, run_with: Callable[[_Results], None], capsys: pytest.CaptureFixture[str]
    ) -> None:
        first, second = (r.job_name for r in checks_ratchet.RATCHETS[:2])
        run_with(
            {
                first: (-1, "", "Command timed out after 84s"),
                second: (-1, "", checks_ratchet._DEADLINE_EXHAUSTED),
            }
        )

        assert checks_ratchet.validate_count_ratchets(REPO_ROOT, 85.0) is False
        err = capsys.readouterr().err
        assert "did not finish inside the 85s deadline" in err
        assert f"{first}, {second}" in err
        assert "TMPDIR" in err
        assert "remove the violations" not in err

    def test_a_real_violation_keeps_the_count_message(
        self, run_with: Callable[[_Results], None], capsys: pytest.CaptureFixture[str]
    ) -> None:
        name = checks_ratchet.RATCHETS[0].job_name
        run_with({name: (1, "REGRESSION", "")})

        assert checks_ratchet.validate_count_ratchets(REPO_ROOT, 85.0) is False
        err = capsys.readouterr().err
        assert "remove the violations" in err
        assert "did not finish" not in err

    def test_a_signaled_child_is_a_failure_not_a_timeout(
        self, run_with: Callable[[_Results], None], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A -1 with no timeout marker is SIGHUP, so it stays a failure."""
        name = checks_ratchet.RATCHETS[0].job_name
        run_with({name: (-1, "", "")})

        assert checks_ratchet.validate_count_ratchets(REPO_ROOT, 85.0) is False
        err = capsys.readouterr().err
        assert "did not finish" not in err
        assert "count ratchet(s) failed" in err

    def test_mixed_results_report_both_classes(
        self, run_with: Callable[[_Results], None], capsys: pytest.CaptureFixture[str]
    ) -> None:
        slow, bad = (r.job_name for r in checks_ratchet.RATCHETS[:2])
        run_with({slow: (-1, "", "Command timed out after 84s"), bad: (1, "", "")})

        assert checks_ratchet.validate_count_ratchets(REPO_ROOT, 85.0) is False
        err = capsys.readouterr().err
        assert f"deadline: {slow}." in err
        assert f"failed: {bad}." in err

    def test_a_passing_run_reports_its_wall_time(
        self, run_with: Callable[[_Results], None], capsys: pytest.CaptureFixture[str]
    ) -> None:
        run_with({})

        assert checks_ratchet.validate_count_ratchets(REPO_ROOT, 85.0) is True
        out = capsys.readouterr().out
        assert f"count ratchets: {len(checks_ratchet.RATCHETS)} entries in" in out
        assert "against a 85s deadline" in out
