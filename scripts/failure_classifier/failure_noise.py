"""Failed shell calls that are the agent's own doing, or a verdict, not a gap.

``workaround_candidates`` looks for a failure in a process, script, skill, or
tool that a later call got past. Most failed calls in a session are not that.
``is_self_inflicted`` names the kinds that are safe to tell apart by pattern:

- the agent's inline program or scratch script crashed;
- the command failed on a file it had just written (a probe under edit);
- a scratch file the agent meant to write first was missing;
- the target already existed, so a rerun of the agent's own step failed;
- the output is a verdict line (``[FAIL] ...``): the tool worked and said no;
- a safety check denied the command.

Each pattern was seen in local transcripts on 2026-11-28. A miss here leaves a
noisy lead in the report; a wrong match drops a real one.

Stdlib only, plus ``command_shape``.
"""

from __future__ import annotations

import posixpath
import re

from scripts.failure_classifier.command_shape import shell_write_targets

SCAN_MAX_CHARS = 20_000
SCRATCH_PATH_MARKERS: tuple[str, ...] = ("/scratch/", "/tmp/")

_SCRATCH = "(?:" + "|".join(re.escape(marker) for marker in SCRATCH_PATH_MARKERS) + ")"
# A traceback frame in ``<string>`` or ``<stdin>`` (``python -c``, a heredoc), or
# in a file under a scratch path.
_OWN_CODE_CRASH = re.compile(
    r'File "(?:<(?:string|stdin)>|[^"\n]{0,400}' + _SCRATCH + r'[^"\n]{0,400})", line \d+'
)
_MISSING_SCRATCH_FILE = re.compile(
    r"(?m)^.{0,400}" + _SCRATCH + r".{0,400}(?:No such file or directory|cannot access)"
    r"|^.{0,200}(?:No such file or directory|cannot access).{0,400}" + _SCRATCH
)
_ALREADY_EXISTS = re.compile(r"\balready exists\b")
_VERDICT_LINE = re.compile(r"(?m)^\s*(?:\x1b\[[\d;]*m)?\[FAIL\]")
_SAFETY_DENIAL = "denied this command"


def is_self_inflicted(command: str, error: str) -> bool:
    """True when the failed ``command`` with output ``error`` is not a gap."""
    text = error[:SCAN_MAX_CHARS]
    if (
        _OWN_CODE_CRASH.search(text)
        or _MISSING_SCRATCH_FILE.search(text)
        or _ALREADY_EXISTS.search(text)
        or _VERDICT_LINE.search(text)
        or _SAFETY_DENIAL in text
    ):
        return True
    written = {posixpath.basename(target) for target in shell_write_targets(command)}
    return any(len(name) >= 4 and name in text for name in written)
