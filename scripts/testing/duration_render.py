"""Markdown report and GitHub Actions annotations for a duration comparison."""

from __future__ import annotations

from collections.abc import Sequence

from scripts.testing.duration_compare import Comparison, Regression
from scripts.testing.duration_snapshot import Snapshot

TREND_ROWS = 10


def ratio_text(regression: Regression) -> str:
    """``3.00x``, or ``new`` when the baseline was zero seconds."""
    if regression.baseline <= 0:
        return "new"
    return f"{regression.seconds / regression.baseline:.2f}x"


def _partition_rows(snapshot: Snapshot) -> list[str]:
    rows = ["| Partition | Tests | Wall seconds |", "| --- | ---: | ---: |"]
    for name, part in sorted(snapshot.partitions.items()):
        rows.append(f"| `{name}` | {int(part['tests'])} | {part['wall_seconds']:.1f} |")
    return rows


def _slowest_rows(snapshot: Snapshot, top: int) -> list[str]:
    ranked = sorted(snapshot.modules.items(), key=lambda kv: (-kv[1]["seconds"], kv[0]))
    rows = ["| Module | Tests | Seconds |", "| --- | ---: | ---: |"]
    for module, entry in ranked[:top]:
        rows.append(f"| `{module}` | {int(entry['tests'])} | {entry['seconds']:.1f} |")
    return rows


def _comparison_lines(comparison: Comparison, history_size: int) -> list[str]:
    if comparison.comparable == 0:
        return [f"No comparable baseline: {history_size} snapshots in history, "
                "none ran the same tests in any module this run measured."]
    delta = comparison.seconds - comparison.baseline
    lines = [f"{comparison.comparable} modules comparable against {history_size} history "
             f"snapshots: {comparison.seconds:.1f}s now, {comparison.baseline:.1f}s median "
             f"baseline ({delta:+.1f}s)."]
    regressions = ([comparison.suite] if comparison.suite else []) + comparison.modules
    if not regressions:
        return [*lines, "", "No duration regression."]
    lines += ["", "| Regressed | Seconds | Baseline | Ratio | Samples |",
              "| --- | ---: | ---: | ---: | ---: |"]
    lines += [f"| `{r.name}` | {r.seconds:.1f} | {r.baseline:.1f} | {ratio_text(r)} | "
              f"{r.samples} |" for r in regressions]
    return lines


def _trend_rows(history: Sequence[Snapshot], current: Snapshot) -> list[str]:
    out = ["| Commit | Recorded | Tests | Test seconds |", "| --- | --- | ---: | ---: |"]
    for snap in [*history[-(TREND_ROWS - 1):], current]:
        out.append(f"| `{snap.sha[:9]}` | {snap.recorded_at} | {snap.total_tests} | "
                   f"{snap.total_seconds:.1f} |")
    return out


def render_markdown(current: Snapshot, history: Sequence[Snapshot], comparison: Comparison,
                    top: int, note: str | None) -> str:
    lines = ["## Test duration", "", f"{current.total_tests} tests, "
             f"{current.total_seconds:.1f} test seconds across "
             f"{len(current.partitions)} partitions.", ""]
    if note:
        lines += [f"Note: {note}", ""]
    lines += [*_partition_rows(current), "", "### Against the main history", ""]
    lines += [*_comparison_lines(comparison, len(history)), "", f"### Slowest {top} modules", ""]
    lines += [*_slowest_rows(current, top), "", "### Recent snapshots", ""]
    lines += _trend_rows(history, current)
    return "\n".join(lines) + "\n"


def _escape_command_data(text: str) -> str:
    """Escape workflow-command data, since module names come from JUnit input."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def warning_commands(comparison: Comparison) -> list[str]:
    """GitHub Actions warning commands, one per regression."""
    regressions = ([comparison.suite] if comparison.suite else []) + comparison.modules
    return [
        "::warning title=Test duration regression::" + _escape_command_data(
            f"{r.name} took {r.seconds:.1f}s against a {r.baseline:.1f}s median baseline "
            f"({ratio_text(r)}, {r.samples} samples)")
        for r in regressions
    ]
