"""JSON and markdown writers for ``gate_latency.py`` (REQ-027 T5).

Split out so ``scripts/metrics/gate_latency.py`` stays under the project's
500-line taste-lint ceiling (``.claude/rules/code-quality.md``); several
sibling validators document the same split for the same reason (see
``scripts/validation/check_repo_health_report.py`` and
``scripts/validation/index_line_endings_record.py``). Only the I/O boundary
lives here: parsing and sampling stay in ``gate_latency.py`` and
``lefthook_summary.py``.

The symlink-refusing writer mirrors
``scripts/metrics/control_plane_baseline.py``'s ``_safe_open`` (read this
session, lines 591-615): a ``Path.is_symlink()`` pre-check, then an
``os.O_NOFOLLOW``-flagged open (closes the CWE-367 TOCTOU window where the
platform supports the flag), mode 0600, and an ``fchmod`` pass that narrows
a pre-existing file's broader mode. No divergence from the sibling.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.metrics.gate_latency_models import GateLatencyReport, HookRun, LatencySummary

_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


class SymlinkRefusedError(Exception):
    """A caller-supplied output path resolves to a symlink (CWE-59)."""


def safe_open(path: Path) -> int:
    """Open ``path`` for writing, refusing a symlink target (CWE-59). See module docstring."""
    if path.is_symlink():
        raise SymlinkRefusedError(f"refusing to write to symlink target: {path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    if hasattr(os, "fchmod"):  # not available on Windows
        try:
            os.fchmod(fd, 0o600)
        except OSError:
            os.close(fd)
            raise
    return fd


def write_json(report: GateLatencyReport, path: Path) -> None:
    fd = safe_open(path)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(dataclasses.asdict(report), fh, indent=2, sort_keys=True)
        fh.write("\n")


_LOW_N_THRESHOLD = 20


def _summary_table(summaries: list[LatencySummary]) -> list[str]:
    """Render one row per scope, headlining the figure the sample size supports.

    AC-05: below ``_LOW_N_THRESHOLD`` samples the table offers no column
    labelled p95, and leads with the worst observed run instead. The label
    is what gets quoted once a figure leaves the artifact, and this
    repository has already watched ADR-104's single-sample numbers travel
    as planning figures despite the caveats printed beside them. The p95
    value stays in the JSON for anyone who wants the order statistic.
    """
    low_n = any(s.n < _LOW_N_THRESHOLD for s in summaries)
    note = [
        "A `group (N)` row is lefthook's own total for a group, which is the "
        "sum of its members rather than wall clock, so a parallel group can "
        "report more than the whole hook took (ci-scripts.md MUST-17). Those "
        "rows are marked; scheduling comes from `lefthook.yml`, never from "
        "this arithmetic.",
        "",
    ]
    if low_n:
        header = [
            "| scope | kind | n | worst observed of n runs | p50 | min |",
            "|---|---|---|---|---|---|",
        ]
        rows = [
            f"| {s.scope} | {_kind(s)} | {s.n} | {s.max:.3f} | {s.p50:.3f} | {s.min:.3f} |"
            for s in summaries
        ]
        return note + header + rows
    header = ["| scope | kind | n | p50 | p95 | min | max |", "|---|---|---|---|---|---|---|"]
    rows = [
        f"| {s.scope} | {_kind(s)} | {s.n} | {s.p50:.3f} | {s.p95:.3f} | "
        f"{s.min:.3f} | {s.max:.3f} |"
        for s in summaries
    ]
    return note + header + rows


def _kind(summary: LatencySummary) -> str:
    """Name what a row measures, so a group total is not read as a job."""
    if summary.scope == "__hook__":
        return "hook wall clock"
    return "group total (sum)" if summary.is_group else "job"


def _run_table(runs: list[HookRun]) -> list[str]:
    lines = [
        "| repetition | exit_code | wall_clock_seconds | lefthook_reported_seconds "
        "| jobs_parsed | tree_mutated | unknown_status_count |",
        "|---|---|---|---|---|---|---|",
    ]
    for run in runs:
        reported = (
            "N/A"
            if run.lefthook_reported_seconds is None
            else f"{run.lefthook_reported_seconds:.3f}"
        )
        lines.append(
            f"| {run.repetition_index} | {run.exit_code} | {run.wall_clock_seconds:.3f} | "
            f"{reported} | {run.jobs_parsed} | {run.tree_mutated} | {run.unknown_status_count} |"
        )
    return lines


def write_markdown(report: GateLatencyReport, path: Path) -> None:
    fd = safe_open(path)
    declared = (
        "N/A" if report.declared_budget_seconds is None else f"{report.declared_budget_seconds}"
    )
    files_rendered = ", ".join(f"`{f}`" for f in report.files) or "(no files)"
    lines = [
        f"# Gate latency: {report.hook} ({report.change_class})",
        "",
        f"- Commit: `{report.commit_sha}`",
        f"- Captured at: `{report.captured_at}`",
        f"- Repetitions: {report.repetitions}",
        f"- Stdin ref line supplied: {report.stdin_ref_line_supplied}",
        f"- Hook args: {report.hook_args or '(none)'}",
        f"- Forced (glob filtering bypassed): {report.forced}",
        f"- Host: {report.host.platform}, {report.host.cpu_count} CPUs, "
        f"Python {report.host.python_version}",
        "",
        "These figures describe one machine on one date. Per-job scheduling "
        "is not inferred from the per-repetition table below; read "
        "`lefthook.yml` for that (ci-scripts.md MUST-17).",
        "",
        "## Measurement command",
        "",
        "```",
        report.command,
        "```",
        "",
        "## Change class",
        "",
        f"- `{report.change_class}`: {files_rendered}",
        "",
        "## Declared vs measured",
        "",
        f"- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified "
        f"from `lefthook_budget_model.declared_budget`): {declared} seconds",
        "",
    ]
    if report.percentile_note:
        lines += [report.percentile_note, ""]
    lines += ["## Latency by scope", "", *_summary_table(report.summaries), ""]
    lines += ["## Per-repetition runs", "", *_run_table(report.runs), ""]
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
