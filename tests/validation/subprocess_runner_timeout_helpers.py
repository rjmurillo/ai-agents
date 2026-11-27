"""Shared timeout fakes for the subprocess runner tests."""

from __future__ import annotations

import subprocess

# A child that flushes its streams, then sleeps well past any test timeout. The
# 1-second wrapper timeout fires first, so the sleep duration only has to exceed
# it comfortably; the test never waits the full sleep.
_TIMEOUT_SECONDS = 1
_CHILD_SLEEP = 30


class _TimedOutPopen:
    """Fake ``Popen`` whose first ``communicate`` times out.

    Lets a test control the exact ``stdout``/``stderr`` types the exception
    carries, including the ``str`` values only the Windows
    kill-then-communicate path produces (unreachable on the POSIX CI host).
    ``drained`` is what the post-kill ``communicate`` returns; ``None`` makes
    that second call time out again, as it does when a grandchild escaped the
    group and still holds the pipe.
    """

    pid = 0
    returncode = -9

    def __init__(
        self,
        output: bytes | str | None,
        stderr: bytes | str | None,
        drained: tuple[str, str] | None = ("", ""),
    ) -> None:
        self._output = output
        self._stderr = stderr
        self._drained = drained
        self.calls = 0
        self.killed = False
        self.stdout = None
        self.stderr = None

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        self.calls += 1
        if self.calls == 1 or self._drained is None:
            raise subprocess.TimeoutExpired(
                cmd=["fake"], timeout=_TIMEOUT_SECONDS, output=self._output, stderr=self._stderr
            )
        return self._drained

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def __enter__(self) -> _TimedOutPopen:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _fake_popen(proc: _TimedOutPopen) -> object:
    def _factory(*_args: object, **_kwargs: object) -> _TimedOutPopen:
        return proc

    return _factory


# Spawns a grandchild that sleeps, records its pid, flushes a marker, then sleeps
# itself. ``{extra}`` lets a test change how the grandchild is launched.
_GRANDCHILD_PARENT = (
    "import subprocess, sys, time;"
    "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']{extra});"
    "open(sys.argv[1], 'w').write(str(g.pid));"
    "sys.stdout.write('PARENT-READY');sys.stdout.flush();"
    "time.sleep(60)"
)
