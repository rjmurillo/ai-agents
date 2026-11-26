"""Tests for scripts/run_with_receipt.py (issue #5851)."""

from __future__ import annotations

import contextlib
import io
import os
import runpy
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_with_receipt as receipt_module
from run_with_receipt import (
    EXIT_EXTERNAL,
    EXIT_USAGE,
    main,
    resolve_out_dir,
)

GITHUB_TOKEN = "ghp_" + "A1b2C3d4E5" * 4  # 40 chars after prefix, matches github-token rule
ARTIFACT_NAME = "20260101T000000-deadbeef.log"
BEARER = "Bearer abcDEF123456xyz+/="
POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-only")


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def run(args: list[str], out_dir: Path, *, inline: int = 16384, timeout: int | None = None) -> int:
    argv = ["run", "--max-inline-bytes", str(inline), "--out-dir", str(out_dir)]
    if timeout is not None:
        argv.extend(["--timeout-seconds", str(timeout)])
    return main([*argv, "--", *args])


class _FakePopen:
    """Popen test double with byte pipes and scripted wait results."""

    def __init__(
        self,
        *,
        stdout: bytes = b"",
        stderr: bytes = b"",
        waits: list[int | BaseException] | None = None,
    ) -> None:
        self.pid = 4321
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.waits = list(waits or [0])
        self.wait_timeouts: list[float | None] = []
        self.kill_calls = 0
        self.returncode: int | None = None

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        result = self.waits.pop(0) if self.waits else 0
        if isinstance(result, BaseException):
            raise result
        self.returncode = int(result)
        return self.returncode

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9


def install_fake_popen(
    monkeypatch: pytest.MonkeyPatch, proc: _FakePopen
) -> list[tuple[tuple[object, ...], dict[str, object]]]:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def factory(*args: object, **kwargs: object) -> _FakePopen:
        calls.append((args, kwargs))
        return proc

    monkeypatch.setattr(receipt_module.subprocess, "Popen", factory)
    return calls


def install_group_fakes(
    monkeypatch: pytest.MonkeyPatch, proc: _FakePopen, *, group_alive_probes: int = 0
) -> list[tuple[int, int]]:
    """Fake process-group support for `proc` and return the signals sent to it.

    The existence probe (signal 0) is not recorded. It reports a live group for
    `group_alive_probes` calls, then a gone group.
    """
    signals: list[tuple[int, int]] = []
    probes = {"left": group_alive_probes}

    def killpg(pgid: int, sig: int) -> None:
        if sig == 0:
            if probes["left"] <= 0:
                raise ProcessLookupError(pgid)
            probes["left"] -= 1
            return
        signals.append((pgid, sig))

    monkeypatch.setattr(receipt_module, "_SUPPORTS_PGROUP", True, raising=False)
    monkeypatch.setattr(receipt_module.os, "killpg", killpg, raising=False)
    monkeypatch.setattr(
        receipt_module.os,
        "getpgid",
        lambda pid: proc.pid if pid == proc.pid else proc.pid + 1,
        raising=False,
    )
    return signals


def install_stubborn_group(
    monkeypatch: pytest.MonkeyPatch, proc: _FakePopen
) -> list[tuple[int, int]]:
    """Fake a group that outlives SIGTERM, with a clock that skips the grace window.

    The group is still there at the end of the window, so the stop must send
    SIGKILL. Returns the signals sent to it.
    """
    signals = install_group_fakes(monkeypatch, proc, group_alive_probes=10_000)
    clock = {"now": 100.0}

    def sleep(seconds: float) -> None:
        clock["now"] += seconds

    monkeypatch.setattr(receipt_module.time, "sleep", sleep)
    monkeypatch.setattr(receipt_module.time, "monotonic", lambda: clock["now"])
    return signals


# A three-level tree for the real-process lifetime tests. The leader starts a
# grandchild in its own process group. Each process writes its pid file only
# after it has installed its SIGTERM disposition, so a pid file means "ready".
#   argv: ROOT MODE [grand]
#   MODE "plain"   default SIGTERM action
#   MODE "cleanup" the grandchild runs a 0.2 s cleanup handler on SIGTERM
#   MODE "ignore"  every process ignores SIGTERM
# Every process sleeps at most 30 s so a leaked tree expires by itself.
TREE_SCRIPT = """
import os, signal, subprocess, sys, time
from pathlib import Path

root, mode = Path(sys.argv[1]), sys.argv[2]
is_grand = sys.argv[3:] == ["grand"]
if mode == "ignore":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if is_grand and mode == "cleanup":
    def on_term(signum, frame):
        time.sleep(0.2)
        (root / "grace-completed").write_text("cleaned")
        os._exit(0)
    signal.signal(signal.SIGTERM, on_term)
if not is_grand:
    subprocess.Popen([sys.executable, __file__, str(root), mode, "grand"])
name = "grand.pid" if is_grand else "child.pid"
(root / name).write_text(str(os.getpid()))
time.sleep(30)
"""

# Runs the wrapper script under a controlled SIGINT disposition: a test runner
# started in the background inherits SIGINT ignored, which would hide the case.
WRAPPER_LAUNCHER = """
import os, runpy, signal, sys
signal.signal(signal.SIGINT, signal.default_int_handler)
sys.argv = sys.argv[1:]
sys.path.insert(0, os.path.dirname(sys.argv[0]))
runpy.run_path(sys.argv[0], run_name="__main__")
"""

# A leader that exits by itself while its grandchild keeps running.
#   argv: ROOT MODE LEADER_EXIT_CODE   (the grandchild gets "grand" instead of the code)
#   MODE "plain"  the grandchild keeps the default SIGTERM action and the output pipes
#   MODE "ignore" the grandchild ignores SIGTERM and keeps the output pipes
#   MODE "quiet"  the grandchild keeps the default action but closes its output pipes
#   MODE "setsid" the grandchild leaves the leader's group and keeps the output pipes
# The leader writes child.pid and exits only once the grandchild is ready. The
# grandchild sleeps at most 30 s so a leaked one expires by itself.
EARLY_EXIT_SCRIPT = """
import os, signal, subprocess, sys, time
from pathlib import Path

root, mode = Path(sys.argv[1]), sys.argv[2]
if sys.argv[3] == "grand":
    if mode == "ignore":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if mode == "setsid":
        os.setsid()
    if mode == "quiet":
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
    (root / "grand.pid").write_text(str(os.getpid()))
    time.sleep(30)
    sys.exit(0)
subprocess.Popen([sys.executable, __file__, str(root), mode, "grand"])
while not (root / "grand.pid").exists():
    time.sleep(0.01)
(root / "child.pid").write_text(str(os.getpid()))
sys.exit(int(sys.argv[3]))
"""


def start_wrapper(
    tmp_path: Path, script: str, *args: str, timeout: str | None = "30"
) -> subprocess.Popen[bytes]:
    """Start the wrapper on `script ROOT ARGS...`, with a deadline unless `timeout` is None."""
    (tmp_path / "script.py").write_text(script, encoding="utf-8")
    command = [sys.executable, "-c", WRAPPER_LAUNCHER, receipt_module.__file__, "run"]
    if timeout is not None:
        command += ["--timeout-seconds", timeout]
    command += [
        "--out-dir",
        str(tmp_path / "out"),
        "--",
        sys.executable,
        str(tmp_path / "script.py"),
        str(tmp_path),
        *args,
    ]
    return subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pid_alive(pid: int) -> bool:
    """True for a running process. A zombie counts as dead: it has stopped."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return True
    return stat.rpartition(")")[2].split()[0] != "Z"


def pid_reaped(pid: int) -> bool:
    """True once the pid is gone. Unlike `pid_alive`, a zombie awaiting its parent is not gone."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def wait_until(predicate: Callable[[], bool], timeout: float = 10.0) -> bool:
    """Poll `predicate` every 20 ms until it holds or `timeout` seconds pass."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def tree_pids(root: Path) -> tuple[int | None, int | None]:
    return read_pid(root / "child.pid"), read_pid(root / "grand.pid")


def tree_ready(root: Path) -> bool:
    return all(pid is not None for pid in tree_pids(root))


def kill_tree(root: Path) -> None:
    """Test cleanup: SIGKILL whatever a failing test left running."""
    for pid in tree_pids(root):
        if pid is not None and pid_alive(pid):
            os.kill(pid, signal.SIGKILL)


def artifacts(out_dir: Path) -> list[Path]:
    return sorted(out_dir.glob("*.log")) if out_dir.exists() else []


def artifact_from(stdout: str) -> Path:
    line = next(item for item in stdout.splitlines() if item.startswith("artifact: "))
    return Path(line.removeprefix("artifact: "))


class TestSmallOutput:
    def test_passes_through_unchanged_without_artifact(self, tmp_path, capfd):
        code = run(py("import sys; print('hello'); print('oops', file=sys.stderr)"), tmp_path)
        captured = capfd.readouterr()
        assert code == 0
        assert captured.out == "hello\n"
        assert captured.err == "oops\n"
        assert artifacts(tmp_path) == []

    def test_propagates_nonzero_exit(self, tmp_path, capfd):
        code = run(py("import sys; print('x'); sys.exit(7)"), tmp_path)
        assert code == 7
        assert capfd.readouterr().out == "x\n"

    def test_signal_death_maps_to_128_plus_signal(self, tmp_path):
        code = run(py("import os, signal; os.kill(os.getpid(), signal.SIGTERM)"), tmp_path)
        assert code == 128 + 15

    def test_secret_redacted_even_when_small(self, tmp_path, capfd):
        run(py(f"print('{GITHUB_TOKEN}')"), tmp_path)
        out = capfd.readouterr().out
        assert GITHUB_TOKEN not in out
        assert "[redacted: github-token]" in out


class TestLargeOutput:
    def test_truncates_with_receipt_and_saves_full_output(self, tmp_path, capfd):
        code = run(py("print('line-%05d' % 0); [print('x' * 99) for _ in range(2000)]"), tmp_path)
        out = capfd.readouterr().out
        assert code == 0
        assert out.startswith("[output contained")
        assert "exit_code: 0" in out
        assert "truncated: true" in out
        assert "duration_s:" in out
        assert len(out.encode()) < 8000
        saved = artifact_from(out).read_bytes()
        assert f"total_bytes: {len(saved)}" in out
        assert saved.count(b"x" * 99) == 2000

    def test_receipt_reports_exposed_bytes(self, tmp_path, capfd):
        run(py("print('y' * 50000)"), tmp_path)
        out = capfd.readouterr().out
        exposed = int(
            next(i for i in out.splitlines() if i.startswith("exposed_bytes: ")).split(": ")[1]
        )
        assert 0 < exposed < 5000

    def test_just_over_threshold_triggers_receipt_and_not_truncated(self, tmp_path, capfd):
        run(py("print('z' * 99)"), tmp_path, inline=50)
        out = capfd.readouterr().out
        assert "truncated: false" in out
        assert artifacts(tmp_path)

    def test_exactly_at_threshold_passes_through(self, tmp_path, capfd):
        run(py("import sys; sys.stdout.write('a' * 50)"), tmp_path, inline=50)
        assert capfd.readouterr().out == "a" * 50
        assert artifacts(tmp_path) == []

    def test_nonzero_exit_shows_stderr_tail_and_propagates_code(self, tmp_path, capfd):
        script = (
            "import sys\n"
            "print('o' * 40000)\n"
            "print('E-BEGIN', file=sys.stderr)\n"
            "print('boom: disk full', file=sys.stderr)\n"
            "sys.exit(4)\n"
        )
        code = run(py(script), tmp_path)
        out = capfd.readouterr().out
        assert code == 4
        assert "exit_code: 4" in out
        assert "--- stderr tail (nonzero exit) ---" in out
        assert "boom: disk full" in out.split("--- stderr tail")[1]

    def test_zero_exit_has_no_failure_section(self, tmp_path, capfd):
        run(py("print('o' * 40000)"), tmp_path)
        assert "stderr tail" not in capfd.readouterr().out

    def test_mixed_stdout_stderr_keep_arrival_order_in_artifact(self, tmp_path, capfd):
        script = (
            "import sys, time\n"
            "for i in range(6):\n"
            "    stream = sys.stdout if i % 2 == 0 else sys.stderr\n"
            "    stream.write(f'{i}:' + 'p' * 3000 + '\\n'); stream.flush()\n"
            "    time.sleep(0.15)\n"
        )
        run(py(script), tmp_path)
        saved = artifact_from(capfd.readouterr().out).read_text()
        order = [line.split(":")[0] for line in saved.splitlines()]
        assert order == ["0", "1", "2", "3", "4", "5"]

    def test_invalid_utf8_does_not_crash_and_is_replaced(self, tmp_path, capfd):
        script = "import sys; sys.stdout.buffer.write(b'ok\\xff\\xfe' + b'q' * 40000)"
        code = run(py(script), tmp_path)
        out = capfd.readouterr().out
        assert code == 0
        assert "�" in out
        assert "�" in artifact_from(out).read_text(encoding="utf-8")

    def test_invalid_utf8_small_passthrough(self, tmp_path, capfd):
        code = run(py("import sys; sys.stdout.buffer.write(b'a\\xffb')"), tmp_path)
        assert code == 0
        assert capfd.readouterr().out == "a�b"


class TestSecrets:
    def test_secret_absent_from_receipt_and_artifact(self, tmp_path, capfd):
        script = (
            "import sys\n"
            f"print('{GITHUB_TOKEN}')\n"
            f"print('{BEARER}', file=sys.stderr)\n"
            "print('filler' * 10000)\n"
            f"print('{GITHUB_TOKEN}', file=sys.stderr)\n"
            "sys.exit(1)\n"
        )
        run(py(script), tmp_path)
        out = capfd.readouterr().out
        saved = artifact_from(out).read_text()
        for blob in (out, saved):
            assert GITHUB_TOKEN not in blob
            assert "abcDEF123456xyz" not in blob
        assert "[redacted: github-token]" in saved

    def test_secret_in_argv_redacted_in_command_line(self, tmp_path, capfd):
        run(py(f"x = '{GITHUB_TOKEN}'; print('n' * 40000)"), tmp_path)
        out = capfd.readouterr().out
        assert GITHUB_TOKEN not in out
        assert "command:" in out

    def test_exact_env_secret_value_redacted(self, tmp_path, capfd, monkeypatch):
        value = "plainvalue-not-a-known-shape-12345"
        monkeypatch.setenv("MY_SERVICE_TOKEN", value)
        run(py(f"print('{value}'); print('n' * 40000)"), tmp_path)
        out = capfd.readouterr().out
        assert value not in out
        assert value not in artifact_from(out).read_text()

    def test_artifact_permissions_are_private(self, tmp_path, capfd):
        run(py("print('n' * 40000)"), tmp_path / "sub")
        path = artifact_from(capfd.readouterr().out)
        assert (path.stat().st_mode & 0o777) == 0o600


class TestRetrieval:
    def make_artifact(self, tmp_path, capfd) -> tuple[Path, bytes]:
        run(
            py("import sys; sys.stdout.write(''.join(chr(97 + i % 26) for i in range(100000)))"),
            tmp_path,
        )
        path = artifact_from(capfd.readouterr().out)
        return path, path.read_bytes()

    def test_reads_requested_range(self, tmp_path, capfd):
        path, saved = self.make_artifact(tmp_path, capfd)
        code = main(
            ["read", str(path), "--offset", "100", "--length", "50", "--out-dir", str(tmp_path)]
        )
        cap = capfd.readouterr()
        assert code == 0
        assert cap.out == saved[100:150].decode()
        assert "next_offset=150" in cap.err

    def test_reports_end_of_artifact(self, tmp_path, capfd):
        path, saved = self.make_artifact(tmp_path, capfd)
        main(["read", str(path), "--offset", str(len(saved) - 5), "--out-dir", str(tmp_path)])
        assert "end_of_artifact" in capfd.readouterr().err

    def test_caps_oversized_length(self, tmp_path, capfd):
        path, _ = self.make_artifact(tmp_path, capfd)
        main(["read", str(path), "--length", "999999", "--out-dir", str(tmp_path)])
        assert len(capfd.readouterr().out) == 65536

    def test_rejects_path_outside_out_dir(self, tmp_path, capfd):
        outside = tmp_path / ARTIFACT_NAME
        outside.write_text("nope")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        assert main(["read", str(outside), "--out-dir", str(out_dir)]) == EXIT_USAGE
        assert "nope" not in capfd.readouterr().out

    def test_rejects_traversal(self, tmp_path):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (tmp_path / "x.log").write_text("hidden")
        assert (
            main(["read", str(out_dir / ".." / "x.log"), "--out-dir", str(out_dir)]) == EXIT_USAGE
        )

    def test_rejects_symlink_escape(self, tmp_path):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        target = tmp_path / ARTIFACT_NAME
        target.write_text("hidden")
        (out_dir / "20260101T000001-cafebabe.log").symlink_to(target)
        assert (
            main(["read", str(out_dir / "20260101T000001-cafebabe.log"), "--out-dir", str(out_dir)])
            == EXIT_USAGE
        )

    @pytest.mark.parametrize(("offset", "length"), [("-1", "10"), ("0", "0")])
    def test_rejects_bad_range(self, tmp_path, offset, length):
        path = tmp_path / ARTIFACT_NAME
        path.write_text("data")
        argv = [
            "read",
            str(path),
            "--offset",
            offset,
            "--length",
            length,
            "--out-dir",
            str(tmp_path),
        ]
        assert main(argv) == EXIT_USAGE

    def test_missing_artifact_is_external_failure(self, tmp_path):
        assert (
            main(["read", str(tmp_path / ARTIFACT_NAME), "--out-dir", str(tmp_path)])
            == EXIT_EXTERNAL
        )


class TestArgvSafety:
    def test_shell_metacharacters_are_literal_arguments(self, tmp_path, capfd):
        marker = tmp_path / "pwned"
        payload = f"; touch {marker}; echo $(touch {marker}) `touch {marker}` | cat"
        code = run(py("import sys; print(sys.argv[1])") + [payload], tmp_path)
        assert code == 0
        assert capfd.readouterr().out == payload + "\n"
        assert not marker.exists()

    def test_unknown_command_is_external_failure(self, tmp_path, capfd):
        assert run(["/nonexistent/definitely-not-a-binary"], tmp_path) == EXIT_EXTERNAL
        assert "cannot launch" in capfd.readouterr().err

    def test_missing_command_is_usage_error(self, tmp_path, capfd):
        assert main(["run", "--out-dir", str(tmp_path)]) == EXIT_USAGE
        assert "usage" in capfd.readouterr().err

    def test_negative_threshold_is_usage_error(self, tmp_path):
        assert main(["run", "--max-inline-bytes", "-1", "--", "true"]) == EXIT_USAGE

    def test_unknown_subcommand_is_usage_error(self, capfd):
        assert main(["bogus"]) == EXIT_USAGE

    def test_wrapper_flags_after_dashes_belong_to_child(self, tmp_path, capfd):
        code = run(py("import sys; print(sys.argv[1:])") + ["--out-dir", "x"], tmp_path)
        assert code == 0
        assert capfd.readouterr().out == "['--out-dir', 'x']\n"


class TestOutDirResolution:
    def test_explicit_wins_over_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TOOL_OUTPUT_DIR", str(tmp_path / "env"))
        assert resolve_out_dir(str(tmp_path / "flag")) == (tmp_path / "flag").resolve()

    def test_env_used_when_no_flag(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TOOL_OUTPUT_DIR", str(tmp_path / "env"))
        assert resolve_out_dir(None) == (tmp_path / "env").resolve()

    def test_default_is_gitignored_dir_under_repo_root(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TOOL_OUTPUT_DIR", raising=False)
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        assert resolve_out_dir(None) == tmp_path.resolve() / ".project-toolkit/temp/tool-output"

    def test_default_falls_back_to_cwd_without_git(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TOOL_OUTPUT_DIR", raising=False)
        isolated = tmp_path / "iso"
        isolated.mkdir()
        monkeypatch.chdir(isolated)
        if any((p / ".git").exists() for p in (isolated.resolve(), *isolated.resolve().parents)):
            pytest.skip("temp root sits inside a git checkout")
        assert resolve_out_dir(None) == isolated.resolve() / ".project-toolkit/temp/tool-output"


class TestFailureAndEntryPoint:
    def test_unwritable_out_dir_is_external_failure(self, tmp_path, capfd):
        blocker = tmp_path / "file"
        blocker.write_text("x")
        assert run(py("print('n' * 40000)"), blocker / "sub") == EXIT_EXTERNAL
        assert "cannot write artifact" in capfd.readouterr().err

    def test_script_entry_point_propagates_exit_code(self, tmp_path):
        script = Path(__file__).resolve().parents[1] / "scripts" / "run_with_receipt.py"
        result = subprocess.run(
            [sys.executable, str(script), "run", "--out-dir", str(tmp_path), "--"]
            + py("import sys; print('hi'); sys.exit(5)"),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert result.returncode == 5
        assert result.stdout == "hi\n"

    def test_module_executes_as_script(self, tmp_path, monkeypatch):
        script = Path(__file__).resolve().parents[1] / "scripts" / "run_with_receipt.py"
        monkeypatch.setattr(
            sys,
            "argv",
            [str(script), "run", "--out-dir", str(tmp_path), "--"] + py("pass"),
        )
        with pytest.raises(SystemExit) as exc:
            runpy.run_path(str(script), run_name="__main__")
        assert exc.value.code == 0


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

    def test_timeout_allows_fast_child_and_preserves_result(self, tmp_path, capfd):
        code = run(py("print('fast')"), tmp_path, timeout=5)
        assert code == 0
        assert capfd.readouterr().out == "fast\n"
        assert artifacts(tmp_path) == []

    def test_absent_timeout_leaves_process_group_setup_unchanged(self, monkeypatch, tmp_path):
        monkeypatch.setattr(receipt_module, "_SUPPORTS_PGROUP", True, raising=False)
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
        monkeypatch.setattr(receipt_module, "_SUPPORTS_PGROUP", False, raising=False)

        def forbidden_killpg(_pgid, _sig):
            raise AssertionError("killpg must not run without process-group support")

        monkeypatch.setattr(receipt_module.os, "killpg", forbidden_killpg, raising=False)
        code = receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=2)
        assert code == 124
        assert proc.kill_calls == 1

    @POSIX_ONLY
    def test_timeout_falls_back_to_child_kill_when_group_is_gone(self, monkeypatch, tmp_path):
        proc = _FakePopen(waits=[subprocess.TimeoutExpired(["fake"], 2), -9])
        install_fake_popen(monkeypatch, proc)
        monkeypatch.setattr(receipt_module, "_SUPPORTS_PGROUP", True, raising=False)

        def missing_group(_pid):
            raise OSError("gone")

        def forbidden_killpg(_pgid, _sig):
            raise AssertionError("killpg must not run when no group is available")

        monkeypatch.setattr(receipt_module.os, "getpgid", missing_group, raising=False)
        monkeypatch.setattr(receipt_module.os, "killpg", forbidden_killpg, raising=False)
        code = receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=2)
        assert code == 124
        assert proc.kill_calls == 1

    @POSIX_ONLY
    def test_group_signal_ignores_a_group_that_is_already_gone(self, monkeypatch):
        def missing_group(_pgid, _sig):
            raise OSError("gone")

        monkeypatch.setattr(receipt_module.os, "killpg", missing_group, raising=False)
        receipt_module._signal_group(12345, signal.SIGTERM)

    def test_process_group_helpers_are_noops_on_windows(self, monkeypatch):
        monkeypatch.setattr(receipt_module.sys, "platform", "win32")

        def forbidden_killpg(_pgid, _sig):
            raise AssertionError("killpg must not run on Windows")

        monkeypatch.setattr(receipt_module.os, "killpg", forbidden_killpg, raising=False)
        receipt_module._signal_group(12345, signal.SIGTERM)
        assert receipt_module._own_group(12345) is None

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


@pytest.fixture
def default_sigterm():
    """Run with the default SIGTERM action, then put back whatever was there."""
    previous = signal.signal(signal.SIGTERM, signal.SIG_DFL)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


@pytest.fixture
def default_sighup():
    """Run with the default SIGHUP action, then put back whatever was there."""
    previous = signal.signal(signal.SIGHUP, signal.SIG_DFL)
    try:
        yield
    finally:
        signal.signal(signal.SIGHUP, previous)


class TestTimedChildLifetime:
    """Blockers from the round 1 critic: cancellation and the SIGTERM grace window."""

    @POSIX_ONLY
    @pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT], ids=["sigterm", "sigint"])
    def test_cancelled_wrapper_stops_the_timed_child_tree(self, tmp_path, sig):
        (tmp_path / "tree.py").write_text(TREE_SCRIPT, encoding="utf-8")
        wrapper = subprocess.Popen(
            [
                sys.executable,
                "-c",
                WRAPPER_LAUNCHER,
                receipt_module.__file__,
                "run",
                "--timeout-seconds",
                "30",
                "--out-dir",
                str(tmp_path / "out"),
                "--",
                sys.executable,
                str(tmp_path / "tree.py"),
                str(tmp_path),
                "plain",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            child, grand = tree_pids(tmp_path)
            wrapper.send_signal(sig)
            wrapper.wait(timeout=10)
            assert wait_until(lambda: not pid_alive(child) and not pid_alive(grand)), (
                f"timed child tree survived wrapper cancellation by {sig.name}"
            )
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_sigterm_to_wrapper_exits_with_128_plus_signal(self, tmp_path):
        (tmp_path / "tree.py").write_text(TREE_SCRIPT, encoding="utf-8")
        wrapper = subprocess.Popen(
            [
                sys.executable,
                "-c",
                WRAPPER_LAUNCHER,
                receipt_module.__file__,
                "run",
                "--timeout-seconds",
                "30",
                "--out-dir",
                str(tmp_path / "out"),
                "--",
                sys.executable,
                str(tmp_path / "tree.py"),
                str(tmp_path),
                "plain",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            wrapper.send_signal(signal.SIGTERM)
            assert wrapper.wait(timeout=10) == 128 + signal.SIGTERM
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_group_members_get_the_grace_window_after_the_leader_exits(self, tmp_path):
        (tmp_path / "tree.py").write_text(TREE_SCRIPT, encoding="utf-8")
        leader = subprocess.Popen(
            [sys.executable, str(tmp_path / "tree.py"), str(tmp_path), "cleanup"],
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            child, grand = tree_pids(tmp_path)
            receipt_module._terminate_child(leader)
            assert (tmp_path / "grace-completed").read_text(encoding="utf-8") == "cleaned"
            assert not pid_alive(child)
            assert wait_until(lambda: not pid_alive(grand))
        finally:
            leader.kill()
            leader.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_leader_is_reaped_during_the_grace_window(self, tmp_path):
        (tmp_path / "tree.py").write_text(TREE_SCRIPT, encoding="utf-8")
        leader = subprocess.Popen(
            [sys.executable, str(tmp_path / "tree.py"), str(tmp_path), "cleanup"],
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            receipt_module._terminate_child(leader)
            assert leader.returncode == -signal.SIGTERM
        finally:
            leader.kill()
            leader.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_group_that_ignores_sigterm_is_killed_after_the_grace_window(self, tmp_path):
        (tmp_path / "tree.py").write_text(TREE_SCRIPT, encoding="utf-8")
        leader = subprocess.Popen(
            [sys.executable, str(tmp_path / "tree.py"), str(tmp_path), "ignore"],
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            child, grand = tree_pids(tmp_path)
            started = time.monotonic()
            receipt_module._terminate_child(leader)
            elapsed = time.monotonic() - started
            assert wait_until(lambda: not pid_alive(child) and not pid_alive(grand))
            assert receipt_module._TERM_GRACE_S * 0.9 <= elapsed < receipt_module._TERM_GRACE_S + 5
        finally:
            leader.kill()
            leader.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_group_that_exits_on_sigterm_does_not_wait_out_the_window(self, tmp_path):
        leader = subprocess.Popen(
            py("import time; time.sleep(30)"), stdin=subprocess.DEVNULL, start_new_session=True
        )
        try:
            started = time.monotonic()
            receipt_module._terminate_child(leader)
            assert time.monotonic() - started < receipt_module._TERM_GRACE_S
            assert leader.returncode == -signal.SIGTERM
        finally:
            leader.kill()
            leader.wait()

    @POSIX_ONLY
    def test_grace_window_is_spent_while_group_members_remain(self, monkeypatch):
        proc = _FakePopen(waits=[-15])
        signals = install_group_fakes(monkeypatch, proc, group_alive_probes=3)
        sleeps: list[float] = []
        monkeypatch.setattr(receipt_module.time, "sleep", sleeps.append)
        monkeypatch.setattr(receipt_module.time, "monotonic", lambda: 100.0 + len(sleeps) * 0.25)

        receipt_module._terminate_child(proc)

        # The members left inside the window, so the group is empty and gets no SIGKILL.
        assert signals == [(proc.pid, signal.SIGTERM)]
        assert len(sleeps) == 3
        assert all(0 < step <= receipt_module._TERM_GRACE_S for step in sleeps)

    @POSIX_ONLY
    def test_grace_window_ends_at_its_deadline_even_if_members_remain(self, monkeypatch):
        proc = _FakePopen(waits=[-15])
        signals = install_group_fakes(monkeypatch, proc, group_alive_probes=10_000)
        clock = {"now": 100.0}

        def sleep(seconds: float) -> None:
            clock["now"] += seconds

        monkeypatch.setattr(receipt_module.time, "sleep", sleep)
        monkeypatch.setattr(receipt_module.time, "monotonic", lambda: clock["now"])

        receipt_module._terminate_child(proc)

        assert clock["now"] - 100.0 == pytest.approx(receipt_module._TERM_GRACE_S)
        assert signals == [(proc.pid, signal.SIGTERM), (proc.pid, signal.SIGKILL)]

    @POSIX_ONLY
    def test_interrupt_while_waiting_stops_a_timed_group(self, monkeypatch, tmp_path):
        proc = _FakePopen(waits=[KeyboardInterrupt(), -15])
        signals = install_stubborn_group(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)

        with pytest.raises(KeyboardInterrupt):
            receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30)

        assert signals == [(proc.pid, signal.SIGTERM), (proc.pid, signal.SIGKILL)]

    def test_interrupt_while_waiting_stops_the_child_without_group_support(
        self, monkeypatch, tmp_path
    ):
        proc = _FakePopen(waits=[KeyboardInterrupt()])
        install_fake_popen(monkeypatch, proc)
        monkeypatch.setattr(receipt_module, "_SUPPORTS_PGROUP", False, raising=False)

        with pytest.raises(KeyboardInterrupt):
            receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30)

        assert proc.kill_calls == 1

    def test_interrupt_without_a_deadline_leaves_the_child_alone(self, monkeypatch, tmp_path):
        proc = _FakePopen(waits=[KeyboardInterrupt()])
        install_fake_popen(monkeypatch, proc)
        signals = install_group_fakes(monkeypatch, proc)

        with pytest.raises(KeyboardInterrupt):
            receipt_module.run_command(["fake"], 16384, tmp_path)

        assert signals == []
        assert proc.kill_calls == 0

    @POSIX_ONLY
    def test_timed_run_turns_sigterm_into_system_exit_then_restores_default(
        self, monkeypatch, tmp_path, default_sigterm
    ):
        seen: list[object] = []

        class Probe(_FakePopen):
            def wait(self, timeout: float | None = None) -> int:
                seen.append(signal.getsignal(signal.SIGTERM))
                return super().wait(timeout)

        proc = Probe(waits=[0])
        install_group_fakes(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)
        assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0

        handler = seen[0]
        assert callable(handler)
        with pytest.raises(SystemExit) as info:
            handler(signal.SIGTERM, None)
        assert info.value.code == 128 + signal.SIGTERM
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL

    def test_run_without_a_deadline_leaves_the_sigterm_action_alone(
        self, monkeypatch, tmp_path, default_sigterm
    ):
        seen: list[object] = []

        class Probe(_FakePopen):
            def wait(self, timeout: float | None = None) -> int:
                seen.append(signal.getsignal(signal.SIGTERM))
                return super().wait(timeout)

        install_fake_popen(monkeypatch, Probe(waits=[0]))
        assert receipt_module.run_command(["fake"], 16384, tmp_path) == 0
        assert seen == [signal.SIG_DFL]

    def test_timed_run_keeps_a_caller_installed_sigterm_handler(self, monkeypatch, tmp_path):
        def custom(_signum, _frame):
            return None

        previous = signal.signal(signal.SIGTERM, custom)
        try:
            proc = _FakePopen(waits=[0])
            install_group_fakes(monkeypatch, proc)
            install_fake_popen(monkeypatch, proc)
            assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0
            assert signal.getsignal(signal.SIGTERM) is custom
        finally:
            signal.signal(signal.SIGTERM, previous)

    def test_timed_run_off_the_main_thread_skips_the_sigterm_handler(self, monkeypatch, tmp_path):
        proc = _FakePopen(waits=[0])
        install_group_fakes(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)
        outcome: dict[str, object] = {}

        def work() -> None:
            try:
                outcome["code"] = receipt_module.run_command(
                    ["fake"], 16384, tmp_path, timeout_seconds=30
                )
            except BaseException as exc:
                outcome["error"] = exc

        thread = threading.Thread(target=work)
        thread.start()
        thread.join(timeout=10)
        assert outcome == {"code": 0}

    def test_timed_run_without_group_support_skips_the_sigterm_handler(
        self, monkeypatch, tmp_path, default_sigterm
    ):
        monkeypatch.setattr(receipt_module, "_SUPPORTS_PGROUP", False, raising=False)
        seen: list[object] = []

        class Probe(_FakePopen):
            def wait(self, timeout: float | None = None) -> int:
                seen.append(signal.getsignal(signal.SIGTERM))
                return super().wait(timeout)

        install_fake_popen(monkeypatch, Probe(waits=[0]))
        assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0
        assert seen == [signal.SIG_DFL]


class TestTimedGroupStopOnEveryExit:
    """Round 2 findings: a timed run leaves no group member running, on any exit path."""

    @POSIX_ONLY
    @pytest.mark.parametrize("leader_code", [0, 5])
    def test_leader_exit_before_the_deadline_stops_the_grandchild(self, tmp_path, leader_code):
        wrapper = start_wrapper(tmp_path, EARLY_EXIT_SCRIPT, "plain", str(leader_code))
        try:
            started = time.monotonic()
            assert wrapper.wait(timeout=20) == leader_code
            assert time.monotonic() - started < 20
            assert tree_ready(tmp_path)
            _, grand = tree_pids(tmp_path)
            assert wait_until(lambda: not pid_alive(grand), timeout=5), (
                "a grandchild outlived the timed wrapper after the leader exited early"
            )
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_grandchild_that_ignores_sigterm_is_killed_after_an_early_leader_exit(self, tmp_path):
        started = time.monotonic()
        wrapper = start_wrapper(tmp_path, EARLY_EXIT_SCRIPT, "ignore", "0")
        try:
            assert wrapper.wait(timeout=20) == 0
            elapsed = time.monotonic() - started
            _, grand = tree_pids(tmp_path)
            assert grand is not None
            assert wait_until(lambda: not pid_alive(grand), timeout=5), (
                "a grandchild that ignores SIGTERM survived the grace window"
            )
            # SIGTERM was ignored, so the whole grace window was spent before SIGKILL,
            # and the 30 s deadline was never reached.
            assert receipt_module._TERM_GRACE_S * 0.9 <= elapsed < 20
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_sigterm_while_the_group_is_being_stopped_still_kills_the_grandchild(self, tmp_path):
        wrapper = start_wrapper(tmp_path, EARLY_EXIT_SCRIPT, "ignore", "0")
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            child, grand = tree_pids(tmp_path)
            # The leader is reaped by the wrapper, so its wait is over. The grandchild
            # is in the leader's group, ignores SIGTERM, and holds the output pipes, so
            # the wrapper is now inside its SIGTERM grace window. The pipes stay open
            # until the SIGKILL at the end of that window, so no drain starts before it.
            assert wait_until(lambda: pid_reaped(child))
            wrapper.send_signal(signal.SIGTERM)
            assert wrapper.wait(timeout=20) == 128 + signal.SIGTERM
            assert wait_until(lambda: not pid_alive(grand), timeout=5), (
                "SIGTERM during the early-exit stop left the grandchild running"
            )
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_sighup_to_a_timed_wrapper_stops_the_tree_and_exits_129(self, tmp_path):
        wrapper = start_wrapper(tmp_path, TREE_SCRIPT, "plain")
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            child, grand = tree_pids(tmp_path)
            wrapper.send_signal(signal.SIGHUP)
            assert wrapper.wait(timeout=20) == 128 + signal.SIGHUP == 129
            assert wait_until(lambda: not pid_alive(child) and not pid_alive(grand)), (
                "timed child tree survived SIGHUP to the wrapper"
            )
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_untimed_run_leaves_a_surviving_grandchild_alone(self, tmp_path):
        wrapper = start_wrapper(tmp_path, EARLY_EXIT_SCRIPT, "quiet", "0", timeout=None)
        try:
            assert wrapper.wait(timeout=20) == 0
            _, grand = tree_pids(tmp_path)
            assert grand is not None
            assert pid_alive(grand), "an untimed run stopped a grandchild"
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_empty_group_at_exit_is_neither_signalled_nor_waited_on(self, monkeypatch, tmp_path):
        signals: list[tuple[int, int]] = []
        stops: list[int | None] = []
        real_killpg = os.killpg
        real_terminate = receipt_module._terminate_child

        def killpg(pgid: int, sig: int) -> None:
            if sig != 0:
                signals.append((pgid, sig))
            real_killpg(pgid, sig)

        def terminate(proc, pgid=None) -> None:
            stops.append(pgid)
            real_terminate(proc, pgid)

        monkeypatch.setattr(receipt_module.os, "killpg", killpg)
        monkeypatch.setattr(receipt_module, "_terminate_child", terminate)

        started = time.monotonic()
        assert receipt_module.run_command(py("pass"), 16384, tmp_path, timeout_seconds=30) == 0
        elapsed = time.monotonic() - started

        # An empty group costs one existence probe: no stop sequence, so no signal
        # and no grace window. The time bound is loose and only catches a stalled
        # return; the stop count is the exact check.
        assert stops == []
        assert signals == []
        assert elapsed < 20

    @POSIX_ONLY
    def test_group_stop_after_the_leader_exits_uses_the_group_captured_at_spawn(
        self, monkeypatch, tmp_path
    ):
        proc = _FakePopen(waits=[0])
        signals = install_stubborn_group(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)
        lookups: list[int] = []

        def getpgid(pid: int) -> int:
            if pid != proc.pid:
                return proc.pid + 1
            lookups.append(pid)
            if len(lookups) > 1:
                raise ProcessLookupError(pid)
            return proc.pid

        monkeypatch.setattr(receipt_module.os, "getpgid", getpgid, raising=False)

        assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0

        assert signals == [(proc.pid, signal.SIGTERM), (proc.pid, signal.SIGKILL)]
        assert lookups == [proc.pid]

    @POSIX_ONLY
    def test_timed_run_turns_sighup_into_system_exit_then_restores_default(
        self, monkeypatch, tmp_path, default_sighup
    ):
        seen: list[object] = []

        class Probe(_FakePopen):
            def wait(self, timeout: float | None = None) -> int:
                seen.append(signal.getsignal(signal.SIGHUP))
                return super().wait(timeout)

        proc = Probe(waits=[0])
        install_group_fakes(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)
        assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0

        handler = seen[0]
        assert callable(handler)
        with pytest.raises(SystemExit) as info:
            handler(signal.SIGHUP, None)
        assert info.value.code == 128 + signal.SIGHUP
        assert signal.getsignal(signal.SIGHUP) is signal.SIG_DFL

    @POSIX_ONLY
    def test_sighup_action_is_restored_after_an_interrupted_timed_run(
        self, monkeypatch, tmp_path, default_sighup
    ):
        proc = _FakePopen(waits=[KeyboardInterrupt(), -15])
        install_group_fakes(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)

        with pytest.raises(KeyboardInterrupt):
            receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30)

        assert signal.getsignal(signal.SIGHUP) is signal.SIG_DFL

    @POSIX_ONLY
    @pytest.mark.parametrize("kind", ["ignored", "custom"])
    def test_timed_run_keeps_a_caller_chosen_sighup_action(self, monkeypatch, tmp_path, kind):
        def custom(_signum, _frame):
            return None

        chosen = signal.SIG_IGN if kind == "ignored" else custom
        previous = signal.signal(signal.SIGHUP, chosen)
        try:
            proc = _FakePopen(waits=[0])
            install_group_fakes(monkeypatch, proc)
            install_fake_popen(monkeypatch, proc)
            assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0
            assert signal.getsignal(signal.SIGHUP) is chosen
        finally:
            signal.signal(signal.SIGHUP, previous)

    def test_timed_run_without_sighup_on_the_platform_still_installs_sigterm(
        self, monkeypatch, tmp_path, default_sigterm
    ):
        monkeypatch.delattr(receipt_module.signal, "SIGHUP", raising=False)
        proc = _FakePopen(waits=[0])
        install_group_fakes(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)
        seen: list[object] = []
        real_wait = proc.wait

        def wait(timeout: float | None = None) -> int:
            seen.append(signal.getsignal(signal.SIGTERM))
            return real_wait(timeout)

        monkeypatch.setattr(proc, "wait", wait)

        assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0

        assert callable(seen[0])
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL


class TestPostSpawnWindowAndStoppedGroup:
    """Round 3 findings: no unguarded window after spawn, no signal to a stopped group."""

    @POSIX_ONLY
    @pytest.mark.parametrize("window", ["Capture", "_own_group"])
    def test_cancel_between_spawn_and_the_guard_still_stops_the_child(
        self, monkeypatch, tmp_path, default_sigterm, window
    ):
        spawned: list[subprocess.Popen[bytes]] = []
        real_popen = subprocess.Popen
        fired: list[bool] = []
        real_target = getattr(receipt_module, window)

        def popen(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            spawned.append(proc)
            return proc

        def cancel_once(*args, **kwargs):
            # A SIGTERM that lands right after the child was spawned.
            if not fired:
                fired.append(True)
                signal.raise_signal(signal.SIGTERM)
            return real_target(*args, **kwargs)

        monkeypatch.setattr(receipt_module.subprocess, "Popen", popen)
        monkeypatch.setattr(receipt_module, window, cancel_once)
        try:
            with pytest.raises(SystemExit) as info:
                receipt_module.run_command(
                    py("import time; time.sleep(20)"), 16384, tmp_path, timeout_seconds=30
                )
            assert info.value.code == 128 + signal.SIGTERM
            assert len(spawned) == 1
            assert spawned[0].poll() is not None, (
                "a cancel after spawn left the timed child running"
            )
        finally:
            for proc in spawned:
                if proc.poll() is None:
                    with contextlib.suppress(OSError):
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()

    @POSIX_ONLY
    def test_group_that_dies_on_sigterm_at_the_deadline_gets_no_sigkill(
        self, monkeypatch, tmp_path
    ):
        signals: list[tuple[int, int]] = []
        real_killpg = os.killpg

        def killpg(pgid: int, sig: int) -> None:
            if sig != 0:
                signals.append((pgid, sig))
            real_killpg(pgid, sig)

        monkeypatch.setattr(receipt_module.os, "killpg", killpg)

        code = receipt_module.run_command(
            py("import time; time.sleep(30)"), 16384, tmp_path, timeout_seconds=1
        )

        assert code == receipt_module.EXIT_TIMEOUT
        assert [sig for _, sig in signals] == [signal.SIGTERM]
        assert len({pgid for pgid, _ in signals}) == 1

    @POSIX_ONLY
    @pytest.mark.parametrize(
        ("waits", "probes", "expected"),
        [
            ([0], 0, []),
            ([0], 1, [signal.SIGTERM]),
            ([subprocess.TimeoutExpired("fake", 30), -15], 1, [signal.SIGTERM]),
        ],
        ids=["group-found-empty", "group-stopped-by-sigterm", "group-stopped-at-the-deadline"],
    )
    def test_cancel_after_the_group_is_stopped_sends_no_further_signal(
        self, monkeypatch, tmp_path, waits, probes, expected
    ):
        proc = _FakePopen(waits=waits)
        signals = install_group_fakes(monkeypatch, proc, group_alive_probes=probes)
        install_fake_popen(monkeypatch, proc)

        class CancelOnJoin(threading.Thread):
            def join(self, timeout: float | None = None) -> None:
                raise KeyboardInterrupt

        monkeypatch.setattr(receipt_module.threading, "Thread", CancelOnJoin)

        with pytest.raises(KeyboardInterrupt):
            receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30)

        assert signals == [(proc.pid, sig) for sig in expected]

    @POSIX_ONLY
    def test_cancel_during_the_early_exit_probe_still_stops_the_group(self, monkeypatch, tmp_path):
        # The leader exited by itself. A cancel at the first probe of its group
        # comes before any stop ran, so the unwind must still run the stop. If the
        # stopped flag were set before the stop, the group would be left alive.
        proc = _FakePopen(waits=[0])
        signals = install_group_fakes(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)
        probes: list[int] = []

        def group_alive(pgid: int) -> bool:
            probes.append(pgid)
            if len(probes) == 1:
                raise KeyboardInterrupt
            return False

        monkeypatch.setattr(receipt_module, "_group_alive", group_alive)

        with pytest.raises(KeyboardInterrupt):
            receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30)

        assert signals == [(proc.pid, signal.SIGTERM)]

    @POSIX_ONLY
    def test_sigterm_during_the_pipe_drain_exits_promptly(self, tmp_path):
        # The grandchild leaves the leader's group and keeps the output pipes, so
        # the wrapper sits in its pipe drain once the leader is reaped.
        wrapper = start_wrapper(tmp_path, EARLY_EXIT_SCRIPT, "setsid", "0")
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            child, _ = tree_pids(tmp_path)
            assert child is not None
            assert wait_until(lambda: pid_reaped(child))
            assert wrapper.poll() is None, "the wrapper did not wait for the held pipes"
            sent = time.monotonic()
            wrapper.send_signal(signal.SIGTERM)
            assert wrapper.wait(timeout=20) == 128 + signal.SIGTERM
            assert time.monotonic() - sent < receipt_module._PIPE_DRAIN_GRACE_S
            # The leader's group is empty: the grandchild left it.
            with pytest.raises(ProcessLookupError):
                os.killpg(child, 0)
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)


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


@pytest.fixture
def default_cancel_signals():
    """Run with the default SIGTERM, SIGHUP, and Ctrl-C actions, then put back what was there."""
    defaults = {
        signal.SIGTERM: signal.SIG_DFL,
        signal.SIGHUP: signal.SIG_DFL,
        signal.SIGINT: signal.default_int_handler,
    }
    previous = {sig: signal.signal(sig, handler) for sig, handler in defaults.items()}
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


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

    monkeypatch.setattr(receipt_module.subprocess, "Popen", CancellingPopen)


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

        monkeypatch.setattr(receipt_module.signal, "signal", install_then_cancel)

        with pytest.raises(SystemExit) as caught:
            with receipt_module._cancel_signals_raise():
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

        monkeypatch.setattr(receipt_module.signal, "signal", restore_then_cancel)

        with pytest.raises(SystemExit) as caught:
            with receipt_module._cancel_signals_raise():
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
        real_capture = receipt_module.Capture

        def popen(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            spawned.append(proc)
            return proc

        def capture(*args, **kwargs):
            seen.append(signal.getsignal(signal.SIGINT))
            signal.raise_signal(sig)
            return real_capture(*args, **kwargs)

        monkeypatch.setattr(receipt_module.subprocess, "Popen", popen)
        monkeypatch.setattr(receipt_module, "Capture", capture)
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

        monkeypatch.setattr(receipt_module.subprocess, "Popen", ProbePopen)

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

        monkeypatch.setattr(receipt_module.subprocess, "Popen", NoisyPopen)
        try:
            code = receipt_module.run_command(py("pass"), 16384, tmp_path, timeout_seconds=30)

            assert code == 0
            assert sorted(calls) == sorted(CANCEL_SIGNALS)
            assert all(signal.getsignal(sig) is caller_handler for sig in CANCEL_SIGNALS)
        finally:
            stop_spawned(spawned)


class TestRedactionBypasses:
    def receipt_command(self, tmp_path, capfd, extra: list[str]) -> str:
        run(py("print('n' * 40000)") + extra, tmp_path)
        out = capfd.readouterr().out
        return next(i for i in out.splitlines() if i.startswith("command: "))

    @pytest.mark.parametrize(
        "extra",
        [
            ["--token", "plainsecretvalue99"],
            ["--password=plainsecretvalue99"],
            ["--api-key", "plainsecretvalue99"],
            ["-H", "Authorization: Basic plainsecretvalue99"],
            ["https://user:plainsecretvalue99@example.com/x"],
        ],
    )
    def test_secret_flag_values_absent_from_command_echo(self, tmp_path, capfd, extra):
        assert "plainsecretvalue99" not in self.receipt_command(tmp_path, capfd, extra)

    def test_short_env_secret_value_redacted(self, tmp_path, capfd, monkeypatch):
        monkeypatch.setenv("DB_PASSWORD", "hunter2")
        run(py("print('pw=hunter2')"), tmp_path)
        assert "hunter2" not in capfd.readouterr().out
        run(py("print('pw=hunter2'); print('n' * 40000)"), tmp_path)
        out = capfd.readouterr().out
        assert "hunter2" not in out
        assert "hunter2" not in artifact_from(out).read_text()

    def test_secret_split_across_read_boundary_redacted(self, tmp_path, capfd):
        script = (
            "import sys, time\n"
            f"t = '{GITHUB_TOKEN}'\n"
            "sys.stdout.write('a' * 100 + ' ' + t[:20]); sys.stdout.flush()\n"
            "time.sleep(0.3)\n"
            "sys.stdout.write(t[20:] + ' ' + 'b' * 40000); sys.stdout.flush()\n"
        )
        run(py(script), tmp_path)
        out = capfd.readouterr().out
        assert GITHUB_TOKEN not in out
        assert GITHUB_TOKEN not in artifact_from(out).read_text()

    def test_read_redacts_even_a_planted_unredacted_artifact(self, tmp_path, capfd):
        planted = tmp_path / ARTIFACT_NAME
        planted.write_text(f"leak {GITHUB_TOKEN}\n")
        assert main(["read", str(planted), "--out-dir", str(tmp_path)]) == 0
        assert GITHUB_TOKEN not in capfd.readouterr().out

    def test_secret_in_invalid_utf8_stream_redacted(self, tmp_path, capfd):
        script = (
            f"import sys; sys.stdout.buffer.write(b'\\xff {GITHUB_TOKEN} \\xfe' + b'q' * 40000)"
        )
        run(py(script), tmp_path)
        out = capfd.readouterr().out
        assert GITHUB_TOKEN not in out
        assert GITHUB_TOKEN not in artifact_from(out).read_text(encoding="utf-8")

    def test_no_temp_file_left_beside_artifact(self, tmp_path, capfd):
        run(py("print('n' * 40000)"), tmp_path)
        capfd.readouterr()
        assert [p.suffix for p in tmp_path.iterdir()] == [".log"]

    def test_grandchild_holding_pipe_does_not_hang(self, tmp_path, capfd):
        script = (
            "import subprocess, sys\n"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "print('done')\n"
        )
        assert run(py(script), tmp_path) == 0
        assert capfd.readouterr().out == "done\n"


class TestSecondReviewBypasses:
    def test_read_refuses_arbitrary_file_even_with_matching_out_dir(self, tmp_path, capfd):
        victim = tmp_path / "passwd"
        victim.write_text("root:x:0:0\n")
        assert main(["read", str(victim), "--out-dir", str(tmp_path)]) == EXIT_USAGE
        assert "root:x" not in capfd.readouterr().out

    def test_read_refuses_non_artifact_log_name(self, tmp_path):
        other = tmp_path / "app.log"
        other.write_text("data")
        assert main(["read", str(other), "--out-dir", str(tmp_path)]) == EXIT_USAGE

    def test_token_split_across_stdout_writes_with_stderr_between(self, tmp_path, capfd):
        script = (
            "import sys, time\n"
            f"t = '{GITHUB_TOKEN}'\n"
            "sys.stdout.write('k ' + t[:20]); sys.stdout.flush()\n"
            "time.sleep(0.3)\n"
            "sys.stderr.write('interleaved\\n'); sys.stderr.flush()\n"
            "time.sleep(0.3)\n"
            "sys.stdout.write(t[20:] + '\\n' + 'b' * 40000); sys.stdout.flush()\n"
        )
        run(py(script), tmp_path)
        out = capfd.readouterr().out
        saved = artifact_from(out).read_text()
        for blob in (out, saved):
            assert GITHUB_TOKEN[:20] not in blob
            assert GITHUB_TOKEN[20:] not in blob

    @pytest.mark.parametrize(
        "name", ["GITHUB_PAT", "NPM_AUTH", "OPENAI_KEY", "SESSION_COOKIE", "DB_CONNECTION"]
    )
    def test_more_env_secret_names_redacted_by_value(self, tmp_path, capfd, monkeypatch, name):
        monkeypatch.setenv(name, "opaque-value-9988")
        run(py("print('v=opaque-value-9988')"), tmp_path)
        assert "opaque-value-9988" not in capfd.readouterr().out

    def test_name_equals_secret_operand_masked_in_command_echo(self, tmp_path, capfd):
        run(py("print('n' * 40000)") + ["API_TOKEN=plainsecretvalue99"], tmp_path)
        assert "plainsecretvalue99" not in capfd.readouterr().out

    def test_launch_error_message_is_redacted(self, tmp_path, capfd):
        run([f"/nonexistent/{GITHUB_TOKEN}"], tmp_path)
        assert GITHUB_TOKEN not in capfd.readouterr().err


class TestThirdReviewBypasses:
    @pytest.mark.parametrize(
        "flag", ["--key", "--private-key", "--access-key", "--passphrase", "--pat"]
    )
    def test_more_secret_flags_masked(self, tmp_path, capfd, flag):
        run(py("print('n' * 40000)") + [flag, "plainsecretvalue99"], tmp_path)
        assert "plainsecretvalue99" not in capfd.readouterr().out

    def test_pem_block_interleaved_with_stderr_is_redacted(self, tmp_path, capfd):
        script = (
            "import sys, time\n"
            "lines = ['-----BEGIN RSA PRIVATE KEY-----', 'MIIEowIBAAKCAQEAsecretbody1',"
            " 'secretbody2', '-----END RSA PRIVATE KEY-----']\n"
            "for line in lines:\n"
            "    sys.stdout.write(line + '\\n'); sys.stdout.flush(); time.sleep(0.1)\n"
            "    sys.stderr.write('log line\\n'); sys.stderr.flush(); time.sleep(0.1)\n"
            "print('n' * 40000)\n"
        )
        run(py(script), tmp_path)
        out = capfd.readouterr().out
        saved = artifact_from(out).read_text()
        for blob in (out, saved):
            assert "secretbody" not in blob
            assert "MIIEow" not in blob
