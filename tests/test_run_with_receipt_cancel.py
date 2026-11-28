"""Tests for scripts/run_with_receipt.py: cancellation while the child is spawned (issue #5851)."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from tests.run_with_receipt_helpers import (
    EXIT_EXTERNAL,
    POSIX_ONLY,
    child_module,
    default_cancel_signals,  # noqa: F401
    pid_reaped,
    py,
    receipt_module,
)


def test_cancel_signal_parametrization_collects_without_sighup(tmp_path):
    """Collection on a platform without SIGHUP still sees the untimed tests."""
    plugin = tmp_path / "no_sighup_plugin.py"
    marker = tmp_path / "sighup-deleted"
    plugin.write_text(
        '''"""Hide SIGHUP while pytest collects tests."""
import os
import signal
from pathlib import Path

_saved = None


def pytest_collection():
    global _saved
    if hasattr(signal, "SIGHUP"):
        _saved = signal.SIGHUP
        delattr(signal, "SIGHUP")
    Path(os.environ["NO_SIGHUP_MARKER"]).write_text("collection ran", encoding="utf-8")


def pytest_collection_finish():
    global _saved
    if _saved is not None:
        signal.SIGHUP = _saved
        _saved = None
''',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["NO_SIGHUP_MARKER"] = str(marker)
    pythonpath = [str(tmp_path)]
    if env.get("PYTHONPATH"):
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    child_temp = tmp_path / "child-pytest"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--collect-only",
            "-p",
            "no_sighup_plugin",
            "-p",
            "no:testmon",
            "--basetemp",
            str(child_temp / "tmp"),
            "-o",
            f"cache_dir={child_temp / 'cache'}",
            str(Path(__file__).resolve()),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert marker.exists()
    assert result.returncode == 0, result.stdout[-4000:]
    assert " collected in " in result.stdout


# What a cancel looks like to the caller of `run_command`, per signal. Ctrl-C raises
# KeyboardInterrupt, which ends a real wrapper by SIGINT (returncode -2).
CANCEL_SIGNAL_NAMES = tuple(
    name for name in ("SIGTERM", "SIGHUP", "SIGINT") if hasattr(signal, name)
)
CANCEL_SIGNALS = [getattr(signal, name) for name in CANCEL_SIGNAL_NAMES]
CANCEL_SIGNAL_IDS = [name.lower() for name in CANCEL_SIGNAL_NAMES]
CANCEL_RESULT = {
    sig: "interrupt" if name == "SIGINT" else f"exit {128 + sig}"
    for name, sig in zip(CANCEL_SIGNAL_NAMES, CANCEL_SIGNALS, strict=True)
}


def run_and_describe(argv: list[str], out_dir: Path) -> str:
    """Run `argv` with a deadline and name how a cancel ended it."""
    try:
        code = receipt_module.run_command(argv, 16384, out_dir, timeout_seconds=30)
    except SystemExit as exc:
        return f"exit {exc.code}"
    except KeyboardInterrupt:
        return "interrupt"
    return f"returned {code}"


def install_cancelling_popen(
    monkeypatch: pytest.MonkeyPatch, sig: int, point: str, spawned: list[int]
) -> None:
    """Replace Popen with one that delivers `sig` to this process at `point`.

    before-exec  before the fork, inside Popen
    after-fork   after the child exists, before Popen's own code finishes
    init-return  after the whole of Popen ran, just before it returns
    Every spawned pid is appended to `spawned`.
    """

    class CancellingPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if point == "init-return":
                signal.raise_signal(sig)

        def _execute_child(self, *args, **kwargs):
            if point == "before-exec":
                signal.raise_signal(sig)
            super()._execute_child(*args, **kwargs)
            spawned.append(self.pid)
            if point == "after-fork":
                signal.raise_signal(sig)

    monkeypatch.setattr(child_module.subprocess, "Popen", CancellingPopen)


def stop_spawned(spawned: list[int]) -> None:
    """Test cleanup by pid: kill and reap what a failing test left running."""
    for pid in spawned:
        if not pid_reaped(pid):
            with contextlib.suppress(OSError):
                os.killpg(pid, signal.SIGKILL)
            with contextlib.suppress(OSError):
                os.waitpid(pid, 0)


def assert_cancel_handlers_restored() -> None:
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
    assert signal.getsignal(signal.SIGHUP) is signal.SIG_DFL
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


@POSIX_ONLY
@pytest.mark.usefixtures("default_cancel_signals")
class TestCancelDuringSpawn:
    """Round 4 finding: a cancel inside Popen, after the fork, must still stop the child."""

    def test_cancel_during_handler_installation_leaves_no_handler_installed(self, monkeypatch):
        real_signal = signal.signal
        fired = False

        def install_then_cancel(sig, handler):
            nonlocal fired
            previous = real_signal(sig, handler)
            if sig == signal.SIGHUP and not fired:
                fired = True
                signal.raise_signal(signal.SIGTERM)
            return previous

        monkeypatch.setattr(child_module.signal, "signal", install_then_cancel)

        with pytest.raises(SystemExit) as caught:
            with child_module._cancel_signals_raise():
                pass

        assert fired
        assert caught.value.code == 128 + signal.SIGTERM
        assert_cancel_handlers_restored()

    def test_cancel_during_handler_restoration_is_delivered_after_handlers_are_restored(
        self, monkeypatch
    ):
        real_signal = signal.signal
        fired = False

        def restore_then_cancel(sig, handler):
            nonlocal fired
            previous = real_signal(sig, handler)
            if sig == signal.SIGTERM and handler is signal.SIG_DFL and not fired:
                fired = True
                signal.raise_signal(signal.SIGHUP)
            return previous

        monkeypatch.setattr(child_module.signal, "signal", restore_then_cancel)

        with pytest.raises(SystemExit) as caught:
            with child_module._cancel_signals_raise():
                pass

        assert fired
        assert caught.value.code == 128 + signal.SIGHUP
        assert_cancel_handlers_restored()

    @pytest.mark.parametrize("point", ["before-exec", "after-fork", "init-return"])
    @pytest.mark.parametrize("sig", CANCEL_SIGNALS, ids=CANCEL_SIGNAL_IDS)
    def test_cancel_inside_popen_stops_the_child_group(self, monkeypatch, tmp_path, sig, point):
        spawned: list[int] = []
        install_cancelling_popen(monkeypatch, sig, point, spawned)
        try:
            result = run_and_describe(py("import time; time.sleep(20)"), tmp_path)

            assert result == CANCEL_RESULT[sig]
            assert len(spawned) == 1
            assert pid_reaped(spawned[0]), "a cancel inside Popen left the timed child running"
            with pytest.raises(ProcessLookupError):
                os.killpg(spawned[0], 0)
            assert_cancel_handlers_restored()
        finally:
            stop_spawned(spawned)

    @pytest.mark.parametrize("sig", CANCEL_SIGNALS, ids=CANCEL_SIGNAL_IDS)
    def test_launch_failure_with_a_held_cancel_delivers_the_cancel(
        self, monkeypatch, tmp_path, sig
    ):
        spawned: list[int] = []
        install_cancelling_popen(monkeypatch, sig, "before-exec", spawned)

        result = run_and_describe(["/nonexistent/run-with-receipt-no-such-command"], tmp_path)

        assert result == CANCEL_RESULT[sig]
        assert spawned == []
        assert_cancel_handlers_restored()

    def test_launch_failure_without_a_cancel_reports_as_before(self, tmp_path, capsys):
        code = receipt_module.run_command(
            ["/nonexistent/run-with-receipt-no-such-command"], 16384, tmp_path, timeout_seconds=30
        )

        assert code == EXIT_EXTERNAL
        assert "cannot launch" in capsys.readouterr().err
        assert_cancel_handlers_restored()

    @pytest.mark.parametrize("sig", CANCEL_SIGNALS, ids=CANCEL_SIGNAL_IDS)
    def test_cancel_after_the_spawn_behaves_as_before(self, monkeypatch, tmp_path, sig):
        # Control: a cancel outside the spawn window is not held. Its handler is
        # the plain one, and it stops the child through the guard as it always did.
        spawned: list[subprocess.Popen[bytes]] = []
        real_popen = subprocess.Popen
        seen: list[object] = []
        real_capture = child_module.Capture

        def popen(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            spawned.append(proc)
            return proc

        def capture(*args, **kwargs):
            seen.append(signal.getsignal(signal.SIGINT))
            signal.raise_signal(sig)
            return real_capture(*args, **kwargs)

        monkeypatch.setattr(child_module.subprocess, "Popen", popen)
        monkeypatch.setattr(child_module, "Capture", capture)
        try:
            result = run_and_describe(py("import time; time.sleep(20)"), tmp_path)

            assert result == CANCEL_RESULT[sig]
            assert seen == [signal.default_int_handler]
            assert len(spawned) == 1
            assert spawned[0].poll() is not None
            assert_cancel_handlers_restored()
        finally:
            for proc in spawned:
                if proc.poll() is None:
                    with contextlib.suppress(OSError):
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()

    def test_ctrl_c_is_held_only_while_the_child_is_spawned(self, monkeypatch, tmp_path):
        inside: list[object] = []
        outside: list[object] = []

        class ProbePopen(subprocess.Popen):
            def _execute_child(self, *args, **kwargs):
                inside.append(signal.getsignal(signal.SIGINT))
                super()._execute_child(*args, **kwargs)

            def wait(self, timeout=None):
                outside.append(signal.getsignal(signal.SIGINT))
                return super().wait(timeout)

        monkeypatch.setattr(child_module.subprocess, "Popen", ProbePopen)

        assert receipt_module.run_command(py("pass"), 16384, tmp_path, timeout_seconds=30) == 0

        assert inside and inside[0] is not signal.default_int_handler
        assert callable(inside[0])
        assert outside[0] is signal.default_int_handler
        assert_cancel_handlers_restored()

    def test_handlers_the_caller_installed_are_neither_replaced_nor_held(
        self, monkeypatch, tmp_path
    ):
        calls: list[int] = []

        def caller_handler(signum: int, _frame: object) -> None:
            calls.append(signum)

        for sig in CANCEL_SIGNALS:
            signal.signal(sig, caller_handler)
        spawned: list[int] = []

        class NoisyPopen(subprocess.Popen):
            def _execute_child(self, *args, **kwargs):
                super()._execute_child(*args, **kwargs)
                spawned.append(self.pid)
                for sig in CANCEL_SIGNALS:
                    signal.raise_signal(sig)

        monkeypatch.setattr(child_module.subprocess, "Popen", NoisyPopen)
        try:
            code = receipt_module.run_command(py("pass"), 16384, tmp_path, timeout_seconds=30)

            assert code == 0
            assert sorted(calls) == sorted(CANCEL_SIGNALS)
            assert all(signal.getsignal(sig) is caller_handler for sig in CANCEL_SIGNALS)
        finally:
            stop_spawned(spawned)
