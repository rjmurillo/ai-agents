"""Windows pipe-reader regression tests."""

from __future__ import annotations

import contextlib
import subprocess
import sys
from pathlib import Path

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
