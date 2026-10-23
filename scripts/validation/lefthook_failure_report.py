#!/usr/bin/env python3
"""Run a Lefthook hook and close a failure with the stage, job, and rerun command.

Used by ``lefthook_runner.py`` for ``run <hook>`` (issue #6734, item 5).
``lefthook.yml`` used to set ``output: false``, so a failed hook said "exit status
1" and never named the failing job. It now sets ``output: [failure]``, and
Lefthook lists each failed job. This module forwards Lefthook's output line by
line, reads the failed job names from it, and ends a failed run with one block
that names the hook, each failed job, and the command that reruns just that job.
The job's own output (file, line, finding) is printed unchanged above the block.
A caller that sets ``LEFTHOOK_OUTPUT`` owns the output and gets Lefthook's
behavior untouched (:func:`should_report`).

Standard library only: this runs when the project environment may be broken.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import threading
from collections.abc import Sequence
from typing import IO

OUTPUT_ENV = "LEFTHOOK_OUTPUT"
# Lefthook lists each failed job as "<boxing glove> <name> (<n> seconds)"; an
# unnamed group is "group (<n>)" and is not a job that `--job` can select.
_FAILED_JOB = re.compile(r"^\s*\U0001F94A (?P<name>.+?) \(\d+(?:\.\d+)? seconds?\)\s*$")
_UNNAMED_GROUP = re.compile(r"^group \(\d+\)$")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _redact_url(argument: str) -> str:
    """Return ``argument`` with any URL credential, query, and fragment removed.

    ``scheme://user:token@host`` carries a credential. A password may hold a raw
    ``@``, ``/``, ``?`` or ``#``, and a URL parser would then end the authority
    early and leave part of it in the path. So the cut is textual: everything
    from ``://`` to the last ``@`` in the whole string is dropped, then any query
    or fragment, since either can hold a token too. A path that holds an ``@``
    loses more than it needs to, which is safe. Any non-URL argument is
    returned unchanged.
    """
    scheme, separator, rest = argument.partition("://")
    if not separator or not scheme or any(c.isspace() for c in scheme):
        return argument
    rest = rest.rpartition("@")[2]
    for marker in ("?", "#"):
        rest = rest.partition(marker)[0]
    return f"{scheme}://{rest}"


def should_report(arguments: Sequence[str]) -> bool:
    """Return True for a ``run <hook>`` call whose output this module owns."""
    return _hook_name(arguments) is not None and OUTPUT_ENV not in os.environ


def _hook_name(arguments: Sequence[str]) -> str | None:
    """Return the hook of a ``run <hook> ...`` invocation, else None."""
    if len(arguments) >= 2 and arguments[0] == "run" and not arguments[1].startswith("-"):
        return arguments[1]
    return None


def split_output(text: str) -> tuple[str, list[str]]:
    """Split Lefthook ``failure`` output into the text to show and failed jobs.

    A failed-job line is removed because the report that follows lists the job
    with a rerun command. A line that carries a reason after the name, such as
    ``name: exit status 128`` for a job that never started, stays in the text:
    nothing else says why the job failed. A job name holds no ``": "``
    (``tests/test_lefthook_runner_failure_report.py`` pins that for
    ``lefthook.yml``).
    """
    shown: list[str] = []
    jobs: list[str] = []
    for line in text.splitlines(keepends=True):
        match = _FAILED_JOB.match(_ANSI.sub("", line))
        if match is None:
            shown.append(line)
            continue
        name, separator, _reason = match.group("name").partition(": ")
        if separator:
            shown.append(line)
        if _UNNAMED_GROUP.match(name) is None and name not in jobs:
            jobs.append(name)
    return "".join(shown), jobs


def _rerun_command(
    command: Sequence[str], arguments: Sequence[str], job: str | None, refs: Sequence[str]
) -> str:
    """Return a shell command that reruns the hook, or one job of it.

    A pre-push hook reads its ref lines from stdin, and without them it runs
    nothing and exits 0. The recorded lines are replayed so the rerun fails the
    same way. Git passes the remote URL as a hook argument, and a URL may carry a
    token (``https://user:token@host``), so userinfo is dropped from the printed
    arguments. The rerun still works: the hook uses the remote name.
    """
    hook, rest = arguments[1], [_redact_url(a) for a in arguments[2:]]
    parts = [*command, "run", hook, *(["--job", job] if job else []), *rest]
    rerun = shlex.join(parts)
    if refs:
        return f"printf '%s\\n' {shlex.join(refs)} | {rerun}"
    return rerun


def failure_report(
    command: Sequence[str],
    arguments: Sequence[str],
    status: int,
    jobs: Sequence[str],
    refs: Sequence[str],
) -> str:
    """Return the closing block for a failed ``run <hook>``: stage, job, rerun.

    Every failed job is listed, because a job left out is a failure the reader
    never sees.
    """
    lines = [f"lefthook_runner: {arguments[1]} FAILED (exit {status})"]
    for job in jobs:
        lines.append(f"  job: {job}")
        lines.append(f"  rerun: {_rerun_command(command, arguments, job, refs)}")
    if not jobs:
        lines.append("  job: not reported by Lefthook")
    # A job rerun skips the jobs that ran before it (pre-pr-validation assumes the
    # fast-stage jobs passed), so the whole hook is the rerun to trust before a push.
    lines.append(f"  rerun hook: {_rerun_command(command, arguments, None, refs)}")
    return "\n".join(lines) + "\n"


def _feed_stdin(stream: IO[bytes], data: bytes) -> None:
    """Write the recorded stdin to the child, then close it."""
    try:
        stream.write(data)
    except OSError:
        pass  # The child exited or never read stdin; its exit status is the result.
    finally:
        try:
            stream.close()
        except OSError:
            pass


def run_hook_with_report(command: Sequence[str], arguments: Sequence[str]) -> int:
    """Run ``run <hook>`` with ``failure`` output and report any failed job.

    Output is forwarded line by line as Lefthook writes it, so a job that fails
    early shows its text while slower jobs still run, and an interrupt keeps
    what was already printed.
    """
    hook = arguments[1]
    refs: list[str] = []
    stdin_bytes: bytes | None = None
    if hook == "pre-push" and sys.stdin is not None and not sys.stdin.isatty():
        stdin_bytes = sys.stdin.buffer.read()
        refs = stdin_bytes.decode("utf-8", errors="replace").splitlines()
    sys.stdout.flush()
    process = subprocess.Popen(
        [*command, *arguments],
        stdin=subprocess.PIPE if stdin_bytes is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if stdin_bytes is not None and process.stdin is not None:
        threading.Thread(target=_feed_stdin, args=(process.stdin, stdin_bytes), daemon=True).start()
    jobs: list[str] = []
    try:
        if process.stdout is not None:
            for raw in process.stdout:
                shown, found = split_output(raw.decode("utf-8", errors="replace"))
                jobs.extend(name for name in found if name not in jobs)
                sys.stdout.write(shown)
                sys.stdout.flush()
        status = process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
    if status != 0:
        sys.stderr.write(failure_report(command, arguments, status, jobs, refs))
    return status
