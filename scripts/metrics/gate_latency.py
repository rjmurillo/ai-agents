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
import sys
from pathlib import Path

# A hung hook would otherwise hang the sampler with no diagnostic. Generous
# on purpose: this has to exceed the slowest legitimate hook, and lefthook's
# own per-job timeout: values already bound the individual jobs. A timeout is
# recorded as a failed repetition, never raised past the caller (AC-06).
_HOOK_TIMEOUT_SECONDS = 3600.0

# Recorded in place of a real exit code when the hook is killed on timeout.
_TIMEOUT_EXIT_CODE = -1

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SENTINEL = _PROJECT_ROOT / "scripts" / "validation" / "models.py"
if _SENTINEL.is_file() and str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.metrics.gate_latency_classes import (
    CHANGE_CLASSES,
)
from scripts.metrics.gate_latency_inputs import _resolve_inputs
from scripts.metrics.gate_latency_io import SymlinkRefusedError, write_json, write_markdown
from scripts.metrics.gate_latency_probe import (
    _run_git,
)
from scripts.metrics.gate_latency_sampler import build_report


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
        "--force",
        action="store_true",
        help="Pass lefthook's --force, which runs every job regardless of its glob. "
        "Off by default, and deliberately so: with it on, a change class stops "
        "selecting jobs and only substitutes the file list, so python-type-check "
        "runs mypy over a markdown file and fails. Without it, the jobs whose globs "
        "the class does not match skip with 'no matching push files', which is what "
        "makes a per-change-class measurement mean anything.",
    )
    parser.add_argument(
        "--hook-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="Positional argument git passes the hook, repeatable and order-sensitive. "
        "A pre-push hook receives the remote name then its URL, and lefthook expands "
        "the first into the '{1}' template that push-ref-staleness reads; without it "
        "that job rejects the unexpanded placeholder and the piped hook aborts four "
        "jobs in, so the run measures almost nothing.",
    )
    parser.add_argument(
        "--lefthook-bin",
        help="Path to the lefthook binary. Defaults to the in-repo venv binary, "
        "falling back to 'uv run --frozen lefthook'.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(args_list)

    resolved = _resolve_inputs(args)
    if isinstance(resolved, int):
        return resolved
    repo, files, lefthook_cmd = resolved

    # A bounded git call raises RuntimeError on timeout rather than letting
    # TimeoutExpired escape as a traceback, so route it to the exit-2 path the
    # sibling control_plane_baseline.py uses for the same class of failure.
    try:
        status = _run_git(repo, "status", "--porcelain")
        if status.returncode != 0:
            print(f"error: git status failed: {status.stderr.strip()}", file=sys.stderr)
            return 2
        if status.stdout.strip() and not args.allow_dirty:
            print(
                "error: working tree is dirty; pass --allow-dirty or commit first",
                file=sys.stderr,
            )
            return 1

        command = "scripts/metrics/gate_latency.py " + " ".join(
            _normalized_command_args(args_list)
        )
        report = build_report(
            repo,
            command,
            args.hook,
            args.change_class,
            files,
            args.repetitions,
            lefthook_cmd,
            args.stdin_ref_line,
            tuple(args.hook_arg),
            args.force,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

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
