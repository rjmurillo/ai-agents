"""Tests for scripts/run_with_receipt.py: deadline and timeout validation (issue #5851)."""

from __future__ import annotations

import signal
import subprocess
import time

import pytest

from tests.run_with_receipt_helpers import (
    EXIT_USAGE,
    GITHUB_TOKEN,
    POSIX_ONLY,
    _FakePopen,
    artifact_from,
    artifacts,
    child_module,
    install_fake_popen,
    install_group_fakes,
    install_stubborn_group,
    main,
    py,
    receipt_module,
    run,
)


class TestTimeoutDeadline:
    def test_run_help_lists_timeout_option(self, capfd):
        assert main(["run", "--help"]) == 0
        assert "--timeout-seconds" in capfd.readouterr().out

    @pytest.mark.parametrize("value", ["0", "-2", "1.5", "abc"])
    def test_rejects_non_positive_or_non_integer_timeouts(self, tmp_path, value):
        argv = [
            "run",
            "--timeout-seconds",
            value,
            "--out-dir",
            str(tmp_path),
            "--",
            "true",
        ]
        assert main(argv) == EXIT_USAGE

    @pytest.mark.parametrize("value", ["4294968", "1" + "0" * 306, "1" + "0" * 309])
    def test_rejects_too_large_timeout_before_launch(self, monkeypatch, tmp_path, capsys, value):
        def forbidden_run_command(*args, **kwargs):
            raise AssertionError("the command was launched")

        monkeypatch.setattr(receipt_module, "run_command", forbidden_run_command)
        argv = [
            "run",
            "--timeout-seconds",
            value,
            "--out-dir",
            str(tmp_path),
            "--",
            "true",
        ]
        assert main(argv) == EXIT_USAGE
        assert "too large" in capsys.readouterr().err

    def test_timeout_bound_uses_windows_dword_milliseconds(self):
        assert child_module.MAX_TIMEOUT_SECONDS * 1000 <= 0xFFFFFFFF
        assert (child_module.MAX_TIMEOUT_SECONDS + 1) * 1000 > 0xFFFFFFFF

    @pytest.mark.parametrize("timeout", [4294968, 10**306, 10**309])
    def test_run_command_rejects_oversized_timeout_before_launch(
        self, monkeypatch, tmp_path, timeout
    ):
        def forbidden_popen(*args, **kwargs):
            raise AssertionError("the command was launched")

        monkeypatch.setattr(child_module.subprocess, "Popen", forbidden_popen)
        with pytest.raises(ValueError, match="too large"):
            receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=timeout)

    def test_timeout_allows_fast_child_and_preserves_result(self, tmp_path, capfd):
        code = run(py("print('fast')"), tmp_path, timeout=5)
        assert code == 0
        assert capfd.readouterr().out == "fast\n"
        assert artifacts(tmp_path) == []

    def test_output_thread_startup_finishes_before_the_child_launches(self, monkeypatch, tmp_path):
        proc = _FakePopen(waits=[subprocess.TimeoutExpired(["fake"], 2), -9])
        install_fake_popen(monkeypatch, proc)
        monkeypatch.setattr(child_module, "_SUPPORTS_PGROUP", False, raising=False)
        clock = {"now": 100.0}
        monkeypatch.setattr(child_module.time, "monotonic", lambda: clock["now"])
        real_thread = child_module.threading.Thread
        delayed = {"done": False}

        class SlowFirstStart(real_thread):
            def start(self):
                if not delayed["done"]:
                    delayed["done"] = True
                    clock["now"] += 1.4
                super().start()

        monkeypatch.setattr(child_module.threading, "Thread", SlowFirstStart)

        assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=2) == 124
        assert proc.wait_timeouts[0] == pytest.approx(2)

    def test_slow_output_thread_startup_cannot_pass_an_over_deadline_result(
        self, monkeypatch, tmp_path, capfd
    ):
        real_thread = child_module.threading.Thread
        delayed = {"done": False}

        class SlowFirstStart(real_thread):
            def start(self):
                if not delayed["done"]:
                    delayed["done"] = True
                    time.sleep(1.4)
                super().start()

        monkeypatch.setattr(child_module.threading, "Thread", SlowFirstStart)
        script = "import time; time.sleep(1.2); print('over-deadline')"

        code = receipt_module.run_command(py(script), 16384, tmp_path, timeout_seconds=1)

        assert code == child_module.EXIT_TIMEOUT
        assert "over-deadline" not in capfd.readouterr().out

    def test_fast_child_still_passes_when_output_thread_startup_is_slow(
        self, monkeypatch, tmp_path, capfd
    ):
        real_thread = child_module.threading.Thread
        delayed = {"done": False}

        class SlowFirstStart(real_thread):
            def start(self):
                if not delayed["done"]:
                    delayed["done"] = True
                    time.sleep(1.4)
                super().start()

        monkeypatch.setattr(child_module.threading, "Thread", SlowFirstStart)
        script = "import time; time.sleep(0.2); print('fast')"

        assert receipt_module.run_command(py(script), 16384, tmp_path, timeout_seconds=1) == 0
        assert capfd.readouterr().out == "fast\n"

    def test_absent_timeout_leaves_process_group_setup_unchanged(self, monkeypatch, tmp_path):
        monkeypatch.setattr(child_module, "_SUPPORTS_PGROUP", True, raising=False)
        proc = _FakePopen(waits=[0])
        calls = install_fake_popen(monkeypatch, proc)
        assert receipt_module.run_command(["fake"], 16384, tmp_path) == 0
        assert "start_new_session" not in calls[0][1]

    @POSIX_ONLY
    def test_timeout_kills_process_group_and_returns_124(self, monkeypatch, tmp_path, capfd):
        proc = _FakePopen(
            stdout=b"partial\n",
            waits=[subprocess.TimeoutExpired(["fake"], 2), -15],
        )
        calls = install_fake_popen(monkeypatch, proc)
        signals = install_stubborn_group(monkeypatch, proc)

        code = receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=2)

        assert code == 124
        assert calls[0][1]["start_new_session"] is True
        assert proc.wait_timeouts[0] == 2
        assert signals == [(proc.pid, signal.SIGTERM), (proc.pid, signal.SIGKILL)]
        assert capfd.readouterr().out == "partial\n"

    def test_timeout_without_process_group_support_kills_child_only(self, monkeypatch, tmp_path):
        proc = _FakePopen(waits=[subprocess.TimeoutExpired(["fake"], 2), -9])
        install_fake_popen(monkeypatch, proc)
        monkeypatch.setattr(child_module, "_SUPPORTS_PGROUP", False, raising=False)

        def forbidden_killpg(_pgid, _sig):
            raise AssertionError("killpg must not run without process-group support")

        monkeypatch.setattr(child_module.os, "killpg", forbidden_killpg, raising=False)
        code = receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=2)
        assert code == 124
        assert proc.kill_calls == 1

    @POSIX_ONLY
    def test_timeout_group_stop_does_not_depend_on_leader_group_lookup(self, monkeypatch, tmp_path):
        proc = _FakePopen(waits=[subprocess.TimeoutExpired(["fake"], 2), -9])
        install_fake_popen(monkeypatch, proc)
        signals = install_stubborn_group(monkeypatch, proc)

        def missing_group(_pid):
            raise OSError("gone")

        monkeypatch.setattr(child_module.os, "getpgid", missing_group, raising=False)
        code = receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=2)
        assert code == 124
        assert signals == [(proc.pid, signal.SIGTERM), (proc.pid, signal.SIGKILL)]
        assert proc.kill_calls == 0

    @POSIX_ONLY
    def test_group_signal_ignores_a_group_that_is_already_gone(self, monkeypatch):
        def missing_group(_pgid, _sig):
            raise OSError("gone")

        monkeypatch.setattr(child_module.os, "killpg", missing_group, raising=False)
        child_module._signal_group(12345, signal.SIGTERM)

    def test_process_group_helpers_are_noops_on_windows(self, monkeypatch):
        monkeypatch.setattr(child_module.sys, "platform", "win32")

        def forbidden_killpg(_pgid, _sig):
            raise AssertionError("killpg must not run on Windows")

        monkeypatch.setattr(child_module.os, "killpg", forbidden_killpg, raising=False)
        child_module._signal_group(12345, signal.SIGTERM)
        assert child_module._own_group(12345) is None

    @POSIX_ONLY
    def test_cleanup_waits_are_bounded_when_child_ignores_term(self, monkeypatch, tmp_path):
        proc = _FakePopen(
            waits=[
                subprocess.TimeoutExpired(["fake"], 2),
                subprocess.TimeoutExpired(["fake"], 1),
                subprocess.TimeoutExpired(["fake"], 1),
            ]
        )
        install_fake_popen(monkeypatch, proc)
        signals = install_stubborn_group(monkeypatch, proc)

        code = receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=2)

        assert code == 124
        assert signals == [(proc.pid, signal.SIGTERM), (proc.pid, signal.SIGKILL)]
        assert proc.wait_timeouts == [2, 1.0, 1.0]

    @POSIX_ONLY
    def test_timeout_receipt_marks_timeout_redacts_and_writes_artifact(
        self, monkeypatch, tmp_path, capfd
    ):
        payload = (GITHUB_TOKEN + "\n").encode() + b"x" * 40000
        proc = _FakePopen(
            stdout=payload,
            waits=[subprocess.TimeoutExpired(["fake"], 2), -15],
        )
        install_fake_popen(monkeypatch, proc)
        install_group_fakes(monkeypatch, proc)

        code = receipt_module.run_command(["fake"], 100, tmp_path, timeout_seconds=2)

        out = capfd.readouterr().out
        assert code == 124
        assert "exit_code: 124" in out
        assert "timeout: true" in out
        assert GITHUB_TOKEN not in out
        saved = artifact_from(out).read_text(encoding="utf-8")
        assert GITHUB_TOKEN not in saved
        assert "x" * 100 in saved

    @POSIX_ONLY
    def test_natural_exit_124_receipt_omits_timeout_marker(self, monkeypatch, tmp_path, capfd):
        proc = _FakePopen(stdout=b"x" * 100, waits=[124])
        install_fake_popen(monkeypatch, proc)
        install_group_fakes(monkeypatch, proc)

        code = receipt_module.run_command(["fake"], 1, tmp_path, timeout_seconds=2)

        out = capfd.readouterr().out
        assert code == 124
        assert "exit_code: 124" in out
        assert "timeout: true" not in out
