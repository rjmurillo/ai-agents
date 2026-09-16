#!/usr/bin/env python3
# ruff: noqa: E402
"""Measure a real lefthook hook's latency distribution (REQ-027, epic #5456).

Runs a whole ``lefthook run <hook>`` N times, per REQ-027 AC-01: never with
``--job``, because a standalone per-job run does not predict that job's cost
inside a real hook run (ci-scripts.md MUST-16: 6.83s standalone against
92.87s in a real push, same job, same day). Scheduling (which jobs overlap,
which are piped) is read from ``lefthook.yml`` via
``scripts.ci.lefthook_budget_model`` (ci-scripts.md MUST-17), never inferred
from the summary's per-job arithmetic, which reports a parallel group's
duration as the sum of its members regardless of scheduling.

Never gates (DR1, measurement-only, mirroring
``scripts/metrics/control_plane_baseline.py``'s own DR1 statement): the
only nonzero exits are a dirty tree without ``--allow-dirty`` (1) and a
configuration problem discovered before any hook runs (2: missing/non-git
repo, missing or invalid ``lefthook.yml``, unknown hook, unknown change
class, a missing change-class path, ``--repetitions < 1``, or a missing
lefthook binary). No metric value, including a hook that fails every
repetition, changes the exit code (AC-06, AC-07). This script MUST NOT be
referenced from ``lefthook.yml``, ``scripts/validation/pre_pr*.py``, or any
file under ``.github/workflows/`` (AC-13); doing so would let a measurement
tool decide whether code can ship.

DR4 (reuse over duplication, AC-09): the declared-budget figure and the
piped-sum/parallel-max scheduling walk are imported from
``scripts.ci.lefthook_budget_model`` (``declared_budget``, ``load_config``),
never reimplemented. The summary parser lives in
``scripts/metrics/lefthook_summary.py``, the JSON/markdown writers live in
``scripts/metrics/gate_latency_io.py``, and the change-class table lives in
``scripts/metrics/gate_latency_classes.py``, so this module stays under the
500-line taste-lint ceiling (REQ-027's buy-vs-build section cites that
ceiling as the reason a sibling script was rejected as an extension point).

Security (CWE-59, CWE-78): every subprocess call uses an argument list with
``shell=False``; ``--file`` arguments come only from the fixed
``CHANGE_CLASSES`` table below, never from free-text user input, so no path
escapes into the lefthook subprocess as untrusted data. Output writing
reuses the sibling's ``O_NOFOLLOW`` symlink-refusing pattern (CWE-59) with
mode 0600 (``gate_latency_io.safe_open``).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from typing import Any

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SENTINEL = _PROJECT_ROOT / "scripts" / "validation" / "models.py"
if _SENTINEL.is_file() and str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.ci.lefthook_budget_model import declared_budget, load_config
from scripts.metrics.gate_latency_classes import (
    CHANGE_CLASSES,
    get_change_class_files,
    missing_change_class_paths,
)
from scripts.metrics.gate_latency_io import SymlinkRefusedError, write_json, write_markdown
from scripts.metrics.gate_latency_models import (
    GateLatencyReport,
    HookRun,
    HostProfile,
    LatencySummary,
)
from scripts.metrics.lefthook_summary import parse_summary


def _nearest_rank_percentile(values: list[float], percentile: float) -> float:
    """Nearest-rank percentile, 1-indexed.

    ``sorted_values[max(0, ceil(p / 100 * n) - 1)]``. Hand-verified: for
    ``[1, 2, 3, 4, 5]``, p50 is 3 and p95 is 5; for ``n == 1``, every
    percentile is that one value.
    """
    if not values:
        raise ValueError("cannot compute a percentile of an empty sample")
    ordered = sorted(values)
    n = len(ordered)
    rank = max(0, ceil(percentile / 100 * n) - 1)
    return ordered[rank]


def _percentile_note(n: int) -> str | None:
    """State p95's status as an upper-order statistic when ``n`` is below 20 (AC-05)."""
    if n >= 20:
        return None
    return (
        f"n={n} is below 20: p95 in this report is an upper-order statistic "
        "of the observed samples, not a tail estimate."
    )


def _smallest_scope_n(summaries: list[LatencySummary], fallback: int) -> int:
    """The smallest per-scope sample count, which is what AC-05's threshold reads.

    Keying the note off ``repetitions`` alone would miss the case that
    matters: a hook that aborts part-way leaves a late job with fewer
    samples than the run count, so a 20-repetition report could carry a
    p95 for a job observed three times with no note attached.
    """
    return min((summary.n for summary in summaries), default=fallback)


def _build_summaries(runs: list[HookRun]) -> list[LatencySummary]:
    """Fold every run's samples into one ``LatencySummary`` per scope.

    ``__hook__`` is scored on the sampler's own ``wall_clock_seconds``
    (AC-03: the end-to-end clock, kept separate from lefthook's
    self-reported total, which is recorded per run but not itself
    summarized). Sorting is alphabetical, which places ``__hook__`` first
    (``_`` sorts before any letter).
    """
    by_scope: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        by_scope["__hook__"].append(run.wall_clock_seconds)
        for sample in run.samples:
            by_scope[sample.name].append(sample.seconds)
    return [
        LatencySummary(
            scope=scope,
            n=len(values),
            p50=_nearest_rank_percentile(values, 50),
            p95=_nearest_rank_percentile(values, 95),
            min=min(values),
            max=max(values),
        )
        for scope, values in sorted(by_scope.items())
    ]


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _tree_digest(repo: Path) -> str:
    """Hash ``git status --porcelain`` so two moments can be compared for drift (AC-12)."""
    porcelain = _run_git(repo, "status", "--porcelain").stdout
    return hashlib.sha256(porcelain.encode("utf-8")).hexdigest()


def _git_rev_parse_head(repo: Path) -> str:
    result = _run_git(repo, "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _host_profile() -> HostProfile:
    return HostProfile(
        captured_at=datetime.now(UTC).isoformat(),
        cpu_count=os.cpu_count() or 1,
        platform=platform.platform(),
        python_version=platform.python_version(),
    )


def _load_lefthook_config(repo: Path) -> dict[str, Any] | None:
    """Parse ``repo``'s ``lefthook.yml``, or ``None`` if absent or invalid.

    Delegates to the shared ``lefthook_budget_model.load_config`` (AC-09);
    only the null-safety this script's exit-code contract needs is new
    here, mirroring ``control_plane_baseline.py``'s ``_lefthook_config``.
    """
    try:
        return load_config(repo / "lefthook.yml")
    except (OSError, yaml.YAMLError, AssertionError):
        return None


def _resolve_lefthook_command(repo: Path, override: str | None) -> list[str] | None:
    """Resolve the lefthook invocation prefix, or ``None`` if nothing is runnable.

    An explicit ``--lefthook-bin`` wins if it resolves (a file path, or a
    name found on ``PATH``). Otherwise this repository's own venv binary at
    ``.venv/bin/lefthook`` is used directly (verified this session: lefthook
    2.1.12). Failing that, ``uv run --frozen lefthook`` is the fallback,
    used only when ``uv`` itself resolves; if none of the three resolves,
    the caller reports "missing lefthook binary" (AC-07).
    """
    if override:
        if Path(override).is_file():
            return [override]
        resolved = shutil.which(override)
        return [resolved] if resolved else None
    venv_bin = repo / ".venv" / "bin" / "lefthook"
    if venv_bin.is_file():
        return [str(venv_bin)]
    uv_bin = shutil.which("uv")
    return ["uv", "run", "--frozen", "lefthook"] if uv_bin else None


def _run_repetition(
    repo: Path,
    lefthook_cmd: list[str],
    hook: str,
    files: tuple[str, ...],
    repetition_index: int,
    stdin_ref_line: str | None = None,
) -> HookRun:
    """Run one whole-hook lefthook invocation and parse its summary (AC-01 to AC-03).

    A hook that fails (non-zero exit) is data, not a sampler error: the
    exit code is recorded and the caller runs the remaining repetitions
    regardless (AC-06).

    ``stdin_ref_line`` is the text git feeds a real pre-push hook on stdin
    (``<local ref> <local sha> <remote ref> <remote sha>``). Several
    pre-push jobs in this repository declare ``use_stdin: true``, and with
    empty stdin those jobs can take an early exit, which would understate
    their cost in exactly the figure this script exists to report. The
    caller supplies the line or it is absent; this module never synthesises
    one, because a fabricated ref line would measure a push that did not
    happen. It reaches the subprocess through ``input=``, never through the
    argument list, so it is not an injection surface on a call that already
    runs with ``shell=False``.
    """
    file_args: list[str] = []
    for rel in files:
        file_args += ["--file", rel]
    cmd = [
        *lefthook_cmd,
        "run",
        hook,
        "--no-tty",
        "--colors",
        "off",
        "--force",
        "--no-stage-fixed",
        *file_args,
    ]
    digest_before = _tree_digest(repo)
    start = time.perf_counter()
    result = subprocess.run(
        cmd,
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        input="" if stdin_ref_line is None else stdin_ref_line.rstrip("\n") + "\n",
    )
    wall_clock_seconds = time.perf_counter() - start
    digest_after = _tree_digest(repo)
    samples, reported_seconds = parse_summary(result.stdout)
    unknown_status_count = sum(1 for sample in samples if sample.status == "unknown")
    return HookRun(
        repetition_index=repetition_index,
        exit_code=result.returncode,
        wall_clock_seconds=wall_clock_seconds,
        lefthook_reported_seconds=reported_seconds,
        jobs_parsed=len(samples),
        tree_mutated=digest_before != digest_after,
        unknown_status_count=unknown_status_count,
        samples=samples,
    )


def build_report(
    repo: Path,
    command: str,
    hook: str,
    change_class: str,
    files: tuple[str, ...],
    repetitions: int,
    lefthook_cmd: list[str],
    stdin_ref_line: str | None = None,
) -> GateLatencyReport:
    """Run every repetition and fold the results into one report."""
    runs = [
        _run_repetition(repo, lefthook_cmd, hook, files, index, stdin_ref_line)
        for index in range(repetitions)
    ]
    summaries = _build_summaries(runs)
    exclusions: list[dict[str, str]] = []
    config = _load_lefthook_config(repo)
    declared_seconds: float | None = None
    if config is not None and hook in config:
        declared_seconds, _rows = declared_budget(config, hook)
    else:
        exclusions.append(
            {
                "field": "declared_budget_seconds",
                "reason": "lefthook.yml unreadable or missing this hook at report time",
            }
        )
    return GateLatencyReport(
        commit_sha=_git_rev_parse_head(repo),
        captured_at=datetime.now(UTC).isoformat(),
        command=command,
        hook=hook,
        change_class=change_class,
        files=list(files),
        repetitions=repetitions,
        host=_host_profile(),
        runs=runs,
        summaries=summaries,
        declared_budget_seconds=declared_seconds,
        percentile_note=_percentile_note(_smallest_scope_n(summaries, repetitions)),
        stdin_ref_line_supplied=stdin_ref_line is not None,
        exclusions=exclusions,
    )


def _normalized_command_args(args_list: list[str]) -> list[str]:
    """Replace the ``--repo`` value with the portable token ``<repo>``.

    Mirrors ``control_plane_baseline.py``'s helper of the same name and the
    same reason: a committed ``command`` field should read the same on any
    clean checkout, not carry one author's absolute path.
    """
    result: list[str] = []
    skip_next = False
    for tok in args_list:
        if skip_next:
            result.append("<repo>")
            skip_next = False
        elif tok == "--repo":
            result.append(tok)
            skip_next = True
        elif tok.startswith("--repo="):
            result.append("--repo=<repo>")
        else:
            result.append(tok)
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sample real lefthook gate latency. Measurement only; never gates (DR1)."
    )
    parser.add_argument("--repo", default=".", help="Path to the git repository to measure.")
    parser.add_argument("--hook", required=True, help="The lefthook hook to run, e.g. pre-commit.")
    parser.add_argument(
        "--repetitions", type=int, default=3, help="Whole-hook repetitions to run."
    )
    parser.add_argument(
        "--change-class",
        default="none",
        help=f"Named file list passed via --file. One of: {', '.join(sorted(CHANGE_CLASSES))}.",
    )
    parser.add_argument("--json", help="Write the JSON report to this path.")
    parser.add_argument("--markdown", help="Write the markdown report to this path.")
    parser.add_argument(
        "--allow-dirty", action="store_true", help="Allow measuring a dirty working tree."
    )
    parser.add_argument(
        "--stdin-ref-line",
        help="Text fed to the hook on stdin, as git feeds a real pre-push hook "
        "('<local ref> <local sha> <remote ref> <remote sha>'). Jobs declaring "
        "use_stdin: true can exit early on empty stdin, which understates their "
        "cost. Omit it and empty stdin is sent; either way the report records "
        "which was used, so a faithful capture is distinguishable from a bare one.",
    )
    parser.add_argument(
        "--lefthook-bin",
        help="Path to the lefthook binary. Defaults to the in-repo venv binary, "
        "falling back to 'uv run --frozen lefthook'.",
    )
    return parser


def _validate_repo_and_repetitions(args: argparse.Namespace) -> tuple[Path, int] | int:
    """Guard clauses that need no file I/O beyond ``repo`` itself (AC-07 exit-2)."""
    repo = Path(args.repo).resolve()
    if not repo.is_dir() or not (repo / ".git").exists():
        print(f"error: not a git repository: {repo}", file=sys.stderr)
        return 2
    if args.repetitions < 1:
        print(f"error: --repetitions must be >= 1, got {args.repetitions}", file=sys.stderr)
        return 2
    return repo, args.repetitions


def _validate_hook(repo: Path, hook: str) -> dict[str, Any] | int:
    """Load ``lefthook.yml`` and confirm ``hook`` names a real hook (AC-07 exit-2)."""
    config = _load_lefthook_config(repo)
    if config is None:
        print("error: missing or invalid lefthook.yml", file=sys.stderr)
        return 2
    hook_cfg = config.get(hook)
    if not isinstance(hook_cfg, dict) or "jobs" not in hook_cfg:
        print(f"error: unknown hook: {hook}", file=sys.stderr)
        return 2
    return config


def _validate_change_class(repo: Path, change_class: str) -> tuple[str, ...] | int:
    """Resolve ``change_class`` to its file list and confirm every path exists (AC-08)."""
    files = get_change_class_files(change_class)
    if files is None:
        print(f"error: unknown change class: {change_class}", file=sys.stderr)
        return 2
    missing = missing_change_class_paths(repo, files)
    if missing:
        print(
            f"error: change class {change_class!r} names a missing path: {missing[0]}",
            file=sys.stderr,
        )
        return 2
    return files


def _resolve_inputs(args: argparse.Namespace) -> tuple[Path, tuple[str, ...], list[str]] | int:
    """Run every exit-2 guard clause and resolve what a repetition needs to run.

    Returns the exit code to use on the first failure, or ``(repo, files,
    lefthook_cmd)`` once every AC-07 exit-2 condition has cleared. The
    exit-1 dirty-tree check stays in ``main``: it needs the resolved
    ``repo`` from here first, and it is a different exit code (AC-07)
    reported for a different reason (a tree state, not a configuration
    problem).
    """
    resolved = _validate_repo_and_repetitions(args)
    if isinstance(resolved, int):
        return resolved
    repo, _repetitions = resolved

    hook_result = _validate_hook(repo, args.hook)
    if isinstance(hook_result, int):
        return hook_result

    files = _validate_change_class(repo, args.change_class)
    if isinstance(files, int):
        return files

    lefthook_cmd = _resolve_lefthook_command(repo, args.lefthook_bin)
    if lefthook_cmd is None:
        print("error: lefthook binary not found", file=sys.stderr)
        return 2

    return repo, files, lefthook_cmd


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(args_list)

    resolved = _resolve_inputs(args)
    if isinstance(resolved, int):
        return resolved
    repo, files, lefthook_cmd = resolved

    status = _run_git(repo, "status", "--porcelain")
    if status.returncode != 0:
        print(f"error: git status failed: {status.stderr.strip()}", file=sys.stderr)
        return 2
    if status.stdout.strip() and not args.allow_dirty:
        print("error: working tree is dirty; pass --allow-dirty or commit first", file=sys.stderr)
        return 1

    command = "scripts/metrics/gate_latency.py " + " ".join(_normalized_command_args(args_list))
    report = build_report(
        repo,
        command,
        args.hook,
        args.change_class,
        files,
        args.repetitions,
        lefthook_cmd,
        args.stdin_ref_line,
    )

    try:
        if args.json:
            write_json(report, Path(args.json))
        if args.markdown:
            write_markdown(report, Path(args.markdown))
    except SymlinkRefusedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
