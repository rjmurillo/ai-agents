"""Windows pipe-reader regression tests."""

from __future__ import annotations

import contextlib
import subprocess
import sys
import time
from pathlib import Path
from typing import cast

import pytest

from scripts.validation.windows_pipes import _communicate_windows
from tests.validation.subprocess_runner_helpers import POSIX_ONLY, kill_if_alive, read_pid


@POSIX_ONLY
def test_windows_pipe_reader_returns_bytes_written_before_a_pipe_stays_open(
    tmp_path: Path,
) -> None:
    """A descendant holding the pipe cannot erase output already flushed."""
    pid_file = tmp_path / "grandchild.pid"
    body = (
        "import subprocess,sys,time;"
        "g=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'],"
        "stdout=sys.stdout,stderr=sys.stderr,start_new_session=True);"
        "open(sys.argv[1],'w').write(str(g.pid));"
        "sys.stdout.write('PARTIAL-OUT');sys.stdout.flush();"
        "time.sleep(20)"
    )
    proc = subprocess.Popen(  # subprocess-encoding: strict-ok
        [sys.executable, "-c", body, str(pid_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    grandchild = 0
    try:
        with pytest.raises(subprocess.TimeoutExpired) as caught:
            _communicate_windows(proc, timeout=0.5)
        output = caught.value.output
        assert isinstance(output, bytes)
        assert b"PARTIAL-OUT" in output
    finally:
        grandchild = read_pid(pid_file) if pid_file.exists() else 0
        kill_if_alive(grandchild)
        kill_if_alive(proc.pid)
        with contextlib.suppress(Exception):
            proc.wait(timeout=2)


def test_decode_pipe_bytes_uses_text_mode_universal_newlines() -> None:
    from scripts.validation.windows_pipes import _decode_pipe_bytes

    assert _decode_pipe_bytes(b"a\r\nb\rc\n") == "a\nb\nc\n"


def test_windows_wait_uses_bounded_slices(monkeypatch) -> None:
    waits: list[float | None] = []

    class _Proc:
        args = ["child"]
        stdout = None
        stderr = None

        def wait(self, timeout: float = 0.0) -> int:
            waits.append(timeout)
            if len(waits) < 3:
                raise subprocess.TimeoutExpired(self.args, timeout)
            return 0

    monkeypatch.setattr(time, "monotonic", iter([0.0, 0.05, 0.1, 0.14, 0.15]).__next__)
    proc = cast(subprocess.Popen[str], _Proc())
    stdout, stderr = _communicate_windows(proc, timeout=1.0)

    assert (stdout, stderr) == ("", "")
    assert waits == [0.1, 0.1, 0.1]
