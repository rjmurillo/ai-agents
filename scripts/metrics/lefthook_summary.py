"""Parse lefthook's own per-job summary block (REQ-027 T1).

lefthook 2.1.12 prints a plain-text summary at the end of a hook run, for
example::

    summary: (done in 0.19 seconds)
    (checkmark) security-suppressions-staged (0.19 seconds)

``--colors off`` does not strip every escape sequence: a divider line above
the summary still carries a truecolor SGR sequence
(``\x1b[38;2;56;56;56m``), so every line is stripped of ANSI escapes before
parsing. This module reads only a job's name, duration, and pass/fail
status. It never infers scheduling (which jobs overlapped, which were
piped) from the summary's arithmetic: ci-scripts.md MUST-17 records that a
parallel group's reported duration is the sum of its members regardless of
scheduling, so that arithmetic carries no scheduling information. Callers
that need scheduling read it from ``lefthook.yml`` via
``scripts.ci.lefthook_budget_model``.

Verified this session against lefthook 2.1.12, two independent real runs,
not taken from documentation: ``lefthook run pre-merge-commit --no-tty
--colors off --force --no-stage-fixed`` against this repository's own
``lefthook.yml`` printed ``✓ security-suppressions-staged (0.20
seconds)`` (pass, exit 0); a disposable throwaway repo with a two-job
``pre-commit`` (one ``exit 0``, one ``exit 1``) printed ``✓ good-job``
and ``✗ bad-job`` (exit 1). U+2714 U+FE0F ("heavy check mark" plus the
emoji-style variation selector), used in an earlier draft of this module on
the strength of an unverified claim, was not reproduced in either capture.
Classification therefore reads the base codepoint rather than the exact
string, so a bare U+2713 or U+2714 (with or without the variation selector)
or U+2705 all read as pass, and U+2717, U+2716, U+2718, or U+274C all read
as fail; anything else is "unknown". Keeping every plausible synonym rather
than only the two measured codepoints is deliberate: a future lefthook
version or a differently-configured terminal could render a different
member of the same glyph family, and ``classify_marker`` returning
"unknown" for that case is surfaced (never silently absorbed) by the
per-run ``unknown_status_count`` in ``gate_latency.HookRun``. The raw
marker string is kept on every sample regardless of classification, so a
reader can see exactly what lefthook printed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_SUMMARY_LINE_RE = re.compile(r"^summary:\s+\(done in (?P<seconds>[0-9.]+)\s+seconds?\)\s*$")
_JOB_LINE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<marker>\S+)\s+(?P<name>.+?)\s+\((?P<seconds>[0-9.]+)\s+seconds?\)\s*$"
)

_PASS_BASE_MARKERS = frozenset({"✓", "✔", "✅"})
_FAIL_BASE_MARKERS = frozenset({"✗", "✖", "✘", "❌"})


@dataclass(frozen=True, slots=True)
class JobSample:
    """One job's duration as lefthook reported it inside one hook run (REQ-027 O2).

    ``depth`` is the summary line's leading-whitespace length: lefthook
    indents a group's member rows under the group's own row, so a group
    total and its member jobs both appear in the parsed sample list, and
    ``depth`` is how a reader tells them apart (ci-scripts.md MUST-17: this
    module records depth, it never uses it to infer scheduling).
    """

    name: str
    seconds: float
    status: str
    marker: str
    depth: int
    is_group: bool = False


def classify_marker(marker: str) -> str:
    """Classify a summary line's status marker as pass, fail, or unknown.

    Reads the base codepoint, ignoring a trailing variation selector
    (U+FE0F), so ``"✓"`` (captured, this repository's own
    pre-merge-commit run) and ``"✔"`` or ``"✔️"``
    (undocumented here, but a plausible variant on another lefthook build
    or terminal) all read as pass instead of only one exact string.
    """
    base = marker[0] if marker else ""
    if base in _PASS_BASE_MARKERS:
        return "pass"
    if base in _FAIL_BASE_MARKERS:
        return "fail"
    return "unknown"


def parse_summary(stdout: str) -> tuple[list[JobSample], float | None]:
    """Parse lefthook's summary block out of a hook run's raw stdout.

    Returns ``([], None)`` when no ``summary:`` line is found in the
    (ANSI-stripped) text. A malformed or absent summary never raises: it
    yields zero samples, so the caller's own ``jobs_parsed`` count exposes
    the gap instead of the sampler crashing mid-run.
    """
    text = _ANSI_ESCAPE_RE.sub("", stdout)
    lines = text.splitlines()
    reported_seconds: float | None = None
    summary_index: int | None = None
    for index, line in enumerate(lines):
        match = _SUMMARY_LINE_RE.match(line)
        if match is not None:
            reported_seconds = float(match.group("seconds"))
            summary_index = index
            break
    if summary_index is None:
        return [], None

    samples: list[JobSample] = []
    for line in lines[summary_index + 1 :]:
        if not line.strip():
            continue
        match = _JOB_LINE_RE.match(line)
        if match is None:
            break
        marker = match.group("marker")
        samples.append(
            JobSample(
                name=match.group("name"),
                seconds=float(match.group("seconds")),
                status=classify_marker(marker),
                marker=marker,
                depth=len(match.group("indent")),
            )
        )
    # lefthook prints a group's own row above its members, indented one level
    # less. That row's duration is the SUM of its members, not wall clock, so a
    # parallel group routinely reports more than the whole hook took
    # (ci-scripts.md MUST-17). Marking it here, where the ordering is still
    # available, is what lets a reader tell a group total from a leaf job once
    # the samples are folded and the ordering is gone.
    return _mark_groups(samples), reported_seconds


def _mark_groups(samples: list[JobSample]) -> list[JobSample]:
    """Flag every row whose successor is indented deeper than it."""
    marked: list[JobSample] = []
    for index, sample in enumerate(samples):
        following = samples[index + 1] if index + 1 < len(samples) else None
        is_group = following is not None and following.depth > sample.depth
        marked.append(
            JobSample(
                name=sample.name,
                seconds=sample.seconds,
                status=sample.status,
                marker=sample.marker,
                depth=sample.depth,
                is_group=is_group,
            )
        )
    return marked
