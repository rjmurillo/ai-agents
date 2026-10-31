"""Guards for the scanner gate's subprocess boundary and time budget.

Split from ``test_check_plugin_scanner_score.py``, which covers the gate's
verdicts. These tests start real child processes.

Coverage:

- positive: ``_run`` returns a child's output; the shared budget caps each
  step and fits inside the lefthook cap with the post-kill drain added.
- negative: a spent budget is an external error (exit 3); a timeout kills the
  child's whole process group, grandchildren included.
- edge: a group that exits between the timeout and the kill is tolerated; a
  descendant that left the group (``setsid``) cannot hold the gate past the
  bounded drain.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_plugin_scanner_score as gate

_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX")


def _spawner(pid_file: Path, *, new_session: bool) -> str:
    """A child that starts a 60s grandchild, records its pid, then sleeps."""
    return (
        "import subprocess, sys, time\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],"
        f" start_new_session={new_session})\n"
        f"open({str(pid_file)!r}, 'w').write(str(p.pid))\n"
        "time.sleep(60)\n"
    )


def _is_gone(pid: int) -> bool:
    """True when ``pid`` no longer exists or is a zombie awaiting its reaper."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as stat:
            return stat.read().split()[2] == "Z"
    except (FileNotFoundError, ProcessLookupError):
        # The process vanished between open and read: ESRCH, not ENOENT.
        return True


def _kill_quietly(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def test_spent_budget_is_external_error() -> None:
    deadline = gate.Deadline(0)
    with pytest.raises(gate.GateError) as exc:
        deadline.remaining()
    assert exc.value.exit_code == 3


def test_budget_caps_each_step() -> None:
    assert gate.Deadline(100).remaining(gate.GIT_TIMEOUT_SECONDS) == gate.GIT_TIMEOUT_SECONDS
    assert gate.Deadline(5).remaining(gate.GIT_TIMEOUT_SECONDS) <= 5


def test_budget_fits_inside_the_lefthook_cap() -> None:
    """The script must report its own timeout before lefthook kills it at 3m."""
    hook = (REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8")
    job = hook[hook.index("- name: plugin-scanner") :]
    assert job.splitlines()[1].strip() == "timeout: 3m"
    assert gate.TOTAL_BUDGET_SECONDS + gate.DRAIN_SECONDS < 180


def test_run_returns_output(tmp_path: Path) -> None:
    result = gate._run([sys.executable, "-c", "print('hi')"], tmp_path, 30)
    assert result.returncode == 0
    assert result.stdout.strip() == b"hi"


@_POSIX_ONLY
def test_run_timeout_kills_the_whole_process_group(tmp_path: Path) -> None:
    """A grandchild (the scanner under uv) must not outlive the timeout."""
    pid_file = tmp_path / "grandchild.pid"
    with pytest.raises(subprocess.TimeoutExpired):
        gate._run([sys.executable, "-c", _spawner(pid_file, new_session=False)], tmp_path, 2)
    grandchild = int(pid_file.read_text(encoding="utf-8"))
    for _ in range(50):
        if _is_gone(grandchild):
            break
        time.sleep(0.1)
    else:
        _kill_quietly(grandchild)
        pytest.fail(f"grandchild {grandchild} survived the timeout")


@_POSIX_ONLY
def test_run_timeout_tolerates_a_group_that_already_exited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def gone(_pid: int, _sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(gate.os, "killpg", gone)
    with pytest.raises(subprocess.TimeoutExpired):
        gate._run([sys.executable, "-c", "import time; time.sleep(0.5)"], tmp_path, 0.1)


@_POSIX_ONLY
def test_run_timeout_does_not_wait_on_a_child_that_left_the_group(tmp_path: Path) -> None:
    """A descendant in its own session keeps the pipes open; the kill cannot reach it."""
    pid_file = tmp_path / "escaped.pid"
    started = time.monotonic()
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            gate._run([sys.executable, "-c", _spawner(pid_file, new_session=True)], tmp_path, 1)
        assert time.monotonic() - started < 1 + gate.DRAIN_SECONDS + 5
    finally:
        if pid_file.is_file():
            _kill_quietly(int(pid_file.read_text(encoding="utf-8")))
