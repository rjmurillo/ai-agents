#!/usr/bin/env python3
"""CodeQL pre-step for /review's security axis (ADR-041 amendment 2026-11-09).

Rules file: ``.project-toolkit/analysis/adr-041-review-caller-rules.md``. This
script runs only when the ``security`` axis is selected. It prints one JSON object
on stdout; ``outcome`` is one of:

    CURRENT       Tier 1 alerts were read for the reviewed HEAD
    CLEAN         guarded local scan: exit 0, zero results, fresh SARIF
    FINDINGS      guarded local scan: exit 1, at least one result, fresh SARIF
    STALE         Tier 1 analyzed a different head, or the tree is dirty
    NOT ANALYZED  Tier 1 has no analysis for the pull request merge ref
    SKIPPED       nothing was read; ``reason`` says why

``status_line`` is the text for the review output. STALE, NOT ANALYZED, and SKIPPED
are never clean. ``alerts`` holds ``{rule_id, path, line}`` and nothing else:
no message and no rule name from the results.

Order of work:

1. Scanner-input guard (``codeql_scanner_guard.py``). A diff that touches a guarded
   path ends the step with ``SKIPPED (scanner inputs modified)`` and reads no result.
2. With ``--pull-request``: Tier 1 alerts through the github skill's
   ``get_pr_code_scanning_alerts.py``. Its outcome is final.
3. Without one: the guarded local scan (``codeql_local_scan.py``), unless
   ``--unattended`` is set, or ``CI`` or ``GITHUB_ACTIONS`` is in the environment.

Input only: the outcome never sets a verdict. The security axis confirms or rejects
each alert against the diff.

Exit codes (ADR-035):
    0  an outcome was produced, including SKIPPED
    2  usage error (bad flag value, such as a non-positive --pull-request)

A directory that is not a git repository is not a usage error: the step prints a
SKIPPED outcome ("diff could not be computed") and exits 0.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).absolute().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import codeql_scanner_guard as guard  # noqa: E402
from codeql_local_scan import LocalScanOutcome, run_local_scan  # noqa: E402

READER_TIMEOUT_SECONDS = 180
_SKILLS_DIR = _HERE.parent.parent
_READER_DIR = _SKILLS_DIR / "github" / "scripts" / "pr"
_READER = _READER_DIR / "get_pr_code_scanning_alerts.py"
_WRAPPER = _SKILLS_DIR / "codeql-scan" / "scripts" / "invoke_codeql_scan.py"
_TIER1_OUTCOMES = frozenset({"CURRENT", "STALE", "NOT ANALYZED", "SKIPPED"})
_UNATTENDED_ENV = ("CI", "GITHUB_ACTIONS")


def skipped(reason: str, **extra: Any) -> dict[str, Any]:
    """Build a SKIPPED outcome. ``reason`` is always a fixed string."""
    return {
        "outcome": "SKIPPED",
        "reason": reason,
        "status_line": f"CodeQL: SKIPPED ({reason})",
        "alerts": [],
        **extra,
    }


def is_unattended(flag: bool, environ: dict[str, str] | None = None) -> bool:
    """True when the run must not use the local scan.

    ``--unattended`` is the contract. ``CI`` and ``GITHUB_ACTIONS`` also count:
    nobody is at the keyboard there, whatever the caller remembered to pass.
    """
    env = os.environ if environ is None else environ
    return flag or any(env.get(name) for name in _UNATTENDED_ENV)


def read_tier1(
    pull_request: int, head: str, clean: bool, files: list[str], reader: Path = _READER
) -> dict[str, Any]:
    """Run the Tier 1 reader and return its ``Data`` as the outcome.

    Any failure to run or parse the reader is ``SKIPPED``: the reader's own JSON is
    the only evidence of a read, and none means nothing was read.
    """
    command = [
        sys.executable,
        str(reader),
        "--pull-request",
        str(pull_request),
        "--head-sha",
        head,
        "--tree-state",
        "clean" if clean else "dirty",
        "--changed-files-from",
        "-",
        "--output-format",
        "json",
    ]
    try:
        result = subprocess.run(
            command,
            input="\n".join(files),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=READER_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return skipped("Tier 1 reader could not run")
    return _outcome_from_reader(result.stdout)


def _outcome_from_reader(stdout: str) -> dict[str, Any]:
    try:
        envelope = json.loads(stdout)
    except ValueError:
        return skipped("Tier 1 reader gave no JSON")
    data = envelope.get("Data") if isinstance(envelope, dict) else None
    if not isinstance(data, dict) or data.get("outcome") not in _TIER1_OUTCOMES:
        return skipped("Tier 1 reader output was not an outcome")
    outcome = dict(data)
    outcome.setdefault("alerts", [])
    outcome["source"] = "tier1"
    return outcome


def _load_scope_helpers() -> Any | None:
    """Import the github skill's scope helpers, the one reduction both sources use."""
    if not _READER_DIR.is_dir():
        return None
    if str(_READER_DIR) not in sys.path:
        sys.path.insert(0, str(_READER_DIR))
    try:
        import code_scanning_scope
    except ImportError:
        return None
    return code_scanning_scope


def local_outcome(scan: LocalScanOutcome, files: list[str]) -> dict[str, Any]:
    """Turn a local scan result into the pre-step outcome."""
    langs = ", ".join(scan.languages)
    if scan.outcome == "SKIPPED":
        return skipped(scan.reason, source="local")
    if scan.outcome == "CLEAN":
        return {
            "outcome": "CLEAN",
            "source": "local",
            "status_line": f"CodeQL: CLEAN (local scan: {langs})",
            "alerts": [],
        }
    return _findings_outcome(scan, files, langs)


def _findings_outcome(scan: LocalScanOutcome, files: list[str], langs: str) -> dict[str, Any]:
    helpers = _load_scope_helpers()
    if helpers is None:
        return skipped("scope helpers not found", source="local")
    try:
        scoped = helpers.scope_sarif_results(scan.results, helpers.normalize_changed_files(files))
    except helpers.SkipError:
        return skipped("a SARIF result had an unexpected shape", source="local")
    attached = len(scoped["alerts"]) + scoped["attached_omitted"]
    line = (
        f"CodeQL: FINDINGS (local scan: {langs}; {attached} in diff files, "
        f"{scoped['other_total']} elsewhere, {scoped['counts']['invalid_rule_id']} "
        "dropped for rule id)"
    )
    return {"outcome": "FINDINGS", "source": "local", "status_line": line, **scoped}


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Run the guard, then the preferred source, and return the outcome."""
    try:
        root = guard.repo_toplevel(Path(args.repo_root))
        head = guard.head_sha(root)
        clean = guard.tree_is_clean(root)
        base_ref = guard.resolve_base_ref(root, args.base_branch)
        files = guard.changed_files(root, base_ref)
        links = guard.changed_symlinks(root, base_ref)
    except guard.GitError:
        return skipped("diff could not be computed")
    touched = guard.guarded_paths(files, links)
    if touched:
        return skipped(
            "scanner inputs modified", guarded_paths=[guard.display(p) for p in touched[:20]]
        )
    if args.pull_request is not None:
        return read_tier1(args.pull_request, head, clean, files)
    if is_unattended(args.unattended):
        return skipped("unattended run, no pull request")
    scan = run_local_scan(root, _WRAPPER, head, clean, guard.languages_for(files))
    return local_outcome(scan, files)


_HELP_EPILOG = """\
examples:
  %(prog)s --base-branch main --pull-request 123
  %(prog)s --base-branch main
  %(prog)s --base-branch main --unattended

exit codes:
  0  an outcome was produced (read "outcome"; SKIPPED is an outcome)
  2  usage error (bad flag value, such as a non-positive --pull-request)

outcome is CURRENT, CLEAN, FINDINGS, STALE, NOT ANALYZED, or SKIPPED. STALE,
NOT ANALYZED, and SKIPPED are never clean.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read CodeQL results for /review's security axis under the ADR-041 rules.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-branch",
        help="Default branch the diff is taken against (default: origin/HEAD's target)",
    )
    parser.add_argument(
        "--pull-request",
        type=int,
        help="Open pull request for the reviewed branch. Omit before one exists",
    )
    parser.add_argument(
        "--unattended",
        action="store_true",
        help="No human is present (headless /ship, schedule). Never use the local scan",
    )
    parser.add_argument("--repo-root", default=".", help="Directory inside the repository")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.pull_request is not None and args.pull_request < 1:
        print("codeql_prestep: --pull-request must be a positive integer", file=sys.stderr)
        return 2
    print(json.dumps(run(args), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
