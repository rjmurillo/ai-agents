"""Budget stops, bounds, and fail-open paths of the friction branch (REQ-048 TASK-003).

Covers AC-05, AC-06, AC-14, AC-43, and the event cap (beads aa-te3).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.hooks.friction_nudge_support import (
    THRESHOLD_ENV,
    friction_records,
    run_env,
    write_transcript,
)
from tests.hooks.reflect_nudge_support import HOOK_PATH, REPO_ROOT, human, nudge

RENDERED_HOOK = REPO_ROOT / ".claude" / "hooks" / "Stop" / "invoke_reflect_nudge.py"


def make_clock(*ticks: float) -> Any:
    """A clock that replays ``ticks`` then stays on the last one."""
    queue = list(ticks)
    return lambda: queue.pop(0) if len(queue) > 1 else queue[0]


@pytest.fixture
def both(tmp_path: Path) -> Path:
    """A correction first, then enough friction for tier 1."""
    return write_transcript(tmp_path / "t.jsonl", [human("no, wrong"), *friction_records(6)])


class TestTimeBudget:
    def test_friction_silent_status_names_budget_correction_kept(
        self, both: Path, tmp_path: Path
    ) -> None:
        clock = make_clock(0.0, 0.0, 0.0, 99.0)  # deadline, line 1, line 2, then over budget
        code, out, err = run_env(both, tmp_path / "state", clock=clock)
        assert code == 0
        assert "/reflect" in json.loads(out)["systemMessage"]
        assert "/retrospective" not in out
        assert len(err.strip().splitlines()) == 1
        assert "time budget" in err and "friction skipped" in err

    def test_friction_only_transcript_is_fully_silent_but_reports(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", friction_records(6))
        state = tmp_path / "state"
        code, out, err = run_env(path, state, clock=make_clock(0.0, 0.0, 99.0))
        assert (code, out) == (0, "")
        assert "time budget" in err and not state.exists()

    def test_within_budget_the_same_transcript_nudges(self, both: Path, tmp_path: Path) -> None:
        _, out, err = run_env(both, tmp_path / "state")
        assert "/retrospective" in out and "budget" not in err


class TestByteBudget:
    def test_scan_stops_on_bytes_and_names_it(
        self, both: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original = nudge.open_transcript

        def open_then_shrink(raw: str) -> Any:
            handle = original(raw)
            monkeypatch.setattr(nudge, "MAX_TRANSCRIPT_BYTES", 400)
            return handle

        monkeypatch.setattr(nudge, "open_transcript", open_then_shrink)
        code, out, err = run_env(both, tmp_path / "state")
        assert code == 0 and "/retrospective" not in out
        assert "bytes budget" in err and "friction skipped" in err

    def test_oversized_file_still_fails_open_before_scan(
        self, both: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nudge, "MAX_TRANSCRIPT_BYTES", 10)
        code, out, err = run_env(both, tmp_path / "state")
        assert (code, out) == (0, "") and "too large" in err


class TestEventCap:
    def test_records_over_cap_are_counted_and_friction_skipped(
        self, both: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nudge, "MAX_FRICTION_RECORDS", 5)
        total = 1 + len(friction_records(6))
        _, out, err = run_env(both, tmp_path / "state")
        assert "/retrospective" not in out and "/reflect" in out
        assert f"{total - 5} records over event cap" in err
        assert "events budget" in err

    def test_under_cap_reports_zero_over(self, both: Path, tmp_path: Path) -> None:
        _, _, err = run_env(both, tmp_path / "state")
        assert "0 records over event cap" in err

    def test_malformed_lines_are_counted_in_status(self, tmp_path: Path) -> None:
        path = write_transcript(
            tmp_path / "t.jsonl", friction_records(6), raw_lines=["{broken", "[1]", "nope"]
        )
        _, out, err = run_env(path, tmp_path / "state")
        assert "3 skipped lines" in err and "/retrospective" in out

    def test_records_are_dropped_from_the_result_when_not_collecting(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", friction_records(2))
        handle = nudge.open_transcript(str(path))
        assert handle is not None
        with handle:
            assert nudge.scan_transcript(handle).records == ()


class TestFailOpen:
    def test_classifier_unavailable_keeps_correction_branch(
        self, both: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nudge, "failure_classifier", None)
        code, out, err = run_env(both, tmp_path / "state")
        assert code == 0 and "/reflect" in out and "/retrospective" not in out
        assert "classifier unavailable" in err

    @pytest.mark.parametrize("raw", ["0", "off", " OFF "])
    def test_without_lib_off_still_silences_both_branches(
        self, raw: str, both: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nudge, "failure_classifier", None)
        code, out, err = run_env(both, tmp_path / "s1", {THRESHOLD_ENV: raw})
        assert (code, out, err) == (0, "", "")
        assert not (tmp_path / "s1").exists()

    @pytest.mark.parametrize("raw", ["5", "junk", "-3", "00"])
    def test_without_lib_a_non_off_threshold_keeps_correction(
        self, raw: str, both: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nudge, "failure_classifier", None)
        code, out, err = run_env(both, tmp_path / "s1", {THRESHOLD_ENV: raw})
        assert code == 0 and "/reflect" in out and "/retrospective" not in out
        assert "classifier unavailable" in err

    @pytest.mark.parametrize("broken", ["compute_friction", "collect_record", "partial_budget"])
    def test_classifier_error_keeps_correction(
        self, broken: str, both: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("broken lib")

        monkeypatch.setattr(nudge.failure_classifier, broken, boom)
        code, out, err = run_env(both, tmp_path / "state")
        assert code == 0 and "/reflect" in out and "/retrospective" not in out
        assert "friction skipped" in err

    def test_classifier_crash_exits_zero_through_main(
        self,
        both: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # main() reads os.environ: keep its marker state out of the real home.
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

        def boom(*_a: Any, **_k: Any) -> Any:
            raise RuntimeError("kaput")

        monkeypatch.setattr(nudge.failure_classifier, "compute_friction", boom)
        monkeypatch.setattr(
            sys, "stdin", io.StringIO(json.dumps({"session_id": "s", "transcript_path": str(both)}))
        )
        assert nudge.main() == 0
        captured = capsys.readouterr()
        assert "friction skipped: classifier error" in captured.err
        assert "/reflect" in captured.out

    def test_single_definition_the_hook_holds_no_copy(self) -> None:
        import failure_classifier as fc

        source = HOOK_PATH.read_text(encoding="utf-8")
        assert not hasattr(nudge, "FRICTION_WEIGHTS") and not hasattr(nudge, "DENIAL_MARKERS")
        assert all(marker not in source for marker in fc.DENIAL_MARKERS)
        assert "FRICTION_WEIGHTS" not in source


class TestExitAndNoDecision:
    @pytest.mark.parametrize(
        "env", [{}, {THRESHOLD_ENV: "off"}, {THRESHOLD_ENV: "x"}, {THRESHOLD_ENV: "1"}]
    )
    def test_every_path_returns_zero_without_decision(
        self, env: dict[str, str], both: Path, tmp_path: Path
    ) -> None:
        paths = [both, None, tmp_path / "gone.jsonl"]
        for index, path in enumerate(paths):
            code, out, _ = run_env(path, tmp_path / f"s{index}", env)
            assert code == 0 and "decision" not in out

    @pytest.mark.skipif(os.name == "nt", reason="POSIX state layout")
    def test_rendered_hook_as_a_process(self, both: Path, tmp_path: Path) -> None:
        state = tmp_path / "xdg"
        env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "XDG_STATE_HOME": str(state)}
        stdin = json.dumps({"session_id": "proc-1", "transcript_path": str(both)})
        done = subprocess.run(
            [sys.executable, str(RENDERED_HOOK)],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
            check=False,
        )
        doc = json.loads(done.stdout)
        assert done.returncode == 0
        assert set(doc) == {"systemMessage"}
        assert "/retrospective" in doc["systemMessage"] and "/reflect" in doc["systemMessage"]
