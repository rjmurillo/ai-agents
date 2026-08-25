#!/usr/bin/env python3
"""Unified shift-left validation runner for pre-PR checks.

Runs all local validations before creating a pull request.
Executes validations in optimized order (fast checks first).

Validation sequence:
    1. Session End (for latest session log)
    2. Pester Tests (all unit tests)
    3. Markdown Lint (auto-fix and validate)
    4. Workflow YAML (validate GitHub Actions workflows)
    5. Design Review Frontmatter (validate DESIGN-REVIEW YAML frontmatter)
    6. Build Command Exit Gates (PR #1887 retrospective Layer 2)
    7. Canonical Citation Check (heuristic mirror-claim citation; soft warn)
    7b. Spec Contradiction Check (PR/issue vs committed frontmatter; advisory)
    8. YAML Style (check YAML style with yamllint) [skip if --quick]
    9. Path Normalization (check for absolute paths) [skip if --quick, requires PS1]
   10. Traceability (validate spec links)
   11. Planning Artifacts (validate planning consistency) [skip if --quick, requires PS1]
   12. Agent Drift (detect semantic drift) [skip if --quick, requires PS1]

Exit codes follow ADR-035:
    0 - Success (all validations passed)
    1 - Logic error (one or more validations failed)
    2 - Config error (environment or configuration issue)

Decomposition (issue #2223): the individual validations live in sibling
``checks_*`` modules grouped by area, and this file is the thin runner plus a
facade that re-exports the validators callers and tests import by name. The
runner calls the same validators in the same order with the same exit
semantics; the imports below keep ``from scripts.validation.pre_pr import X``
working for callers and tests.

The facade is not exhaustive. Measured on this tree, 15 validators that
``pre_pr_sequence`` imports have no re-export here (``validate_traceability``,
``validate_count_ratchets``, ``validate_mypy_changed_files`` and 12 others),
so ``from scripts.validation.pre_pr import X`` fails for them. That gap
predates this file's ADR work and is tracked in issue #5272; do not read the
imports below as a promise of full coverage.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# Shared infrastructure (subprocess wrapper, SKIP signal, base-ref helpers).
from active_plan_closeout import validate_active_plan_closeout

# Ratcheted ADR lifecycle gate (issue #5191) and the ADR link-integrity gate
# (issue #5197). Both are re-exported here so
# ``from scripts.validation.pre_pr import validate_adr_lifecycle`` and the
# matching ``validate_adr_links`` import both resolve; the ordered row that
# RUNS each belongs in ``pre_pr_sequence._SEQUENCE``, which is where the
# sequence moved in issue #3073. ``check_adr_links`` was wired into that
# sequence in this PR without the re-export, breaking the second import until
# this line was added (Copilot, PR #5209).
#
# This claim covers these two validators only. It is not evidence the facade
# re-exports every validator: 15 others that ``pre_pr_sequence`` imports are
# still missing from it, a pre-existing gap tracked in issue #5272 (see the
# module docstring above).
from check_adr_lifecycle import validate_adr_lifecycle
from check_adr_links import validate_adr_links
from check_doc_interpreter_portability import (
    validate_doc_interpreter_portability,
)
from check_nested_tests import validate_no_nested_tests
from check_subprocess_encoding import validate_subprocess_encoding
from check_test_tree_writes import validate_test_tree_writes
from check_unreachable_code import validate_unreachable_code
from checks_common import (
    MissingScriptSkip,
    _gh_base_ref,
    _reset_gh_base_cache,
    _resolve_branch_base_ref,
    _run_build_script_gate,
    _run_subprocess,
)

# Area check modules. Each ``validate_*`` is re-exported below so existing
# imports of ``scripts.validation.pre_pr`` continue to resolve (issue #2223).
from checks_coverage import (
    validate_review_marker,
)
from checks_dash import (
    _branch_markdown_files,
    _find_dash_violations,
    _is_vendored,
    _print_dash_violations,
    validate_dash_prohibition,
)
from checks_plugin import (
    _is_linked_worktree,
    validate_colocated_skill_tests,
    validate_copilot_agent_frontmatter,
    validate_hook_anchoring,
    validate_install_parity,
    validate_lefthook_installed,
    validate_plugin_version_bump,
    validate_shipped_skill_routes,
    validate_workflow_local_run,
)
from checks_spec import (
    validate_agent_catalog,
    validate_build_gates,
    validate_canonical_citations,
    validate_model_pins,
    validate_orchestrator_citations,
    validate_skill_md_portability,
    validate_skill_shells,
    validate_spec_contradiction,
    validate_spec_id_uniqueness,
    validate_sync_registry,
    validate_vendor_portability,
)
from checks_tooling import (
    _find_latest_session_log,
    _markdown_lint_targets,
    validate_agent_drift,
    validate_ci_dependency_pins,
    validate_copilot_version_pin,
    validate_markdown_lint,
    validate_path_normalization,
    validate_planning_artifacts,
    validate_session_end,
    validate_workflow_yaml,
    validate_yaml_style,
)
from pre_pr_sequence import run_all_validations
from stale_script_refs import validate_stale_script_refs
from validate_argument_hint import validate_argument_hint

# Frontmatter parsing and DESIGN-REVIEW validation live in sibling modules
# (issue #2223). Re-exported here so ``_parse_yaml_frontmatter`` and
# ``validate_design_review_frontmatter`` stay importable from ``pre_pr``.
from validate_design_review import (
    _BLOCKING_STATUSES,
    _REQUIRED_FRONTMATTER_FIELDS,
    _VALID_PRIORITIES,
    _VALID_STATUSES,
    validate_design_review_frontmatter,
)
from validate_no_orphaned_build_deferrals import (
    validate_no_orphaned_build_deferrals,
)
from validate_python_syntax import validate_python_syntax
from yaml_utils import _parse_yaml_frontmatter


@dataclass
class ValidationRecord:
    """Result of a single validation step."""

    name: str
    status: str  # PASS, FAIL, SKIP
    duration: float = 0.0
    message: str = ""


@dataclass
class ValidationState:
    """Tracks overall validation results."""

    results: list[ValidationRecord] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0


def run_validation(
    name: str,
    state: ValidationState,
    callback: Callable[[], bool],
    skip: bool = False,
) -> bool:
    """Run a validation and track results. Returns True on pass/skip."""
    state.total += 1

    if skip:
        print(f"[SKIP] {name} (skipped due to --quick flag)")
        state.skipped += 1
        state.results.append(ValidationRecord(name=name, status="SKIP", message="Skipped"))
        return True

    print()
    print(f"=== {name} ===")
    print("[RUNNING] Starting validation...")

    start = time.monotonic()
    success = False
    skipped = False
    message = ""

    try:
        success = callback()
        message = "Validation passed" if success else "Validation failed"
    except MissingScriptSkip as exc:
        skipped = True
        success = True  # SKIP does not count as failure for the gate
        message = f"Skipped: {exc}"
    except Exception as exc:
        success = False
        message = f"Validation error: {exc}"

    duration = time.monotonic() - start

    if skipped:
        state.skipped += 1
        status_label = "SKIP"
    elif success:
        state.passed += 1
        status_label = "PASS"
    else:
        state.failed += 1
        status_label = "FAIL"

    state.results.append(
        ValidationRecord(
            name=name,
            status=status_label,
            duration=duration,
            message=message,
        )
    )

    print()
    print(f"[{status_label}] {name} completed in {duration:.2f}s")
    if status_label == "FAIL":
        print(f"Error: {message}")
    elif status_label == "SKIP":
        print(f"Note: {message}")

    return success


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with env var defaults."""
    parser = argparse.ArgumentParser(
        description="Unified shift-left validation runner for pre-PR checks.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        default=os.environ.get("QUICK_MODE", "").lower() in ("true", "1"),
        help="Skip slow validations (path normalization, planning, drift)",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        default=os.environ.get("SKIP_TESTS", "").lower() in ("true", "1"),
        help="Skip Pester unit tests (use sparingly)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Run with verbose output",
    )
    parser.add_argument(
        "--markdown-lint-only",
        action="store_true",
        help="Run only markdownlint against positional markdown files",
    )
    parser.add_argument(
        "markdown_files",
        nargs="*",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Determine repo root (parent of scripts/)
    repo_root = Path(__file__).resolve().parent.parent.parent
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2

    # Scope the gh PR-base cache to this invocation (item 3, round 2 review):
    # branch/HEAD is a proxy for "did the local checkout change", not for
    # "did the remote PR change", so a stale answer from a prior in-process
    # invocation (a retry, or a test harness calling main() repeatedly) must
    # not leak into this one. Runs before both the fast path below and the
    # full gate sequence so every gh-querying gate in this run is covered.
    _reset_gh_base_cache()

    if args.markdown_lint_only:
        return 0 if validate_markdown_lint(repo_root, args.markdown_files) else 1
    if args.markdown_files:
        parser.error("markdown files can only be passed with --markdown-lint-only")

    quick = args.quick
    mode = "Quick (fast checks only)" if quick else "Full"
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    print()
    print("=== Pre-PR Validation Runner ===")
    print(f"Repository: {repo_root}")
    print(f"Mode: {mode}")
    print(f"Started: {now}")
    print()

    state = ValidationState()
    start_time = time.monotonic()

    # The ordered validation sequence lives in
    # ``pre_pr_sequence.run_all_validations`` so this module stays under the
    # size ceiling (Issue #3073). ``run_validation`` and ``state`` are passed
    # in because the sequence must not import ``pre_pr`` (it runs as
    # ``__main__``); it imports validators from the ``checks_*`` modules.
    run_all_validations(repo_root, args, state, run_validation)
    total_duration = time.monotonic() - start_time

    # Summary
    print()
    print("=== Validation Summary ===")
    print(f"Duration: {total_duration:.2f}s")
    print(f"Total Validations: {state.total}")
    print(f"Passed: {state.passed}")
    print(f"Failed: {state.failed}")
    print(f"Skipped: {state.skipped}")
    print()

    print("=== Detailed Results ===")
    print()
    for record in state.results:
        duration_str = f" ({record.duration:.2f}s)" if record.duration > 0 else ""
        print(f"[{record.status}] {record.name}{duration_str}")

    print()

    if state.failed > 0:
        print(f"RESULT: {state.failed} validation(s) failed")
        print()
        print("Fix suggestions:")
        print("  1. Review error messages above for specific issues")
        print("  2. Run individual validation scripts for more details")
        print("  3. See .agents/SHIFT-LEFT.md for workflow documentation")
        print()
        return 1

    print("RESULT: All validations passed")
    print()
    # When running as a lefthook job (SKIP_AUTOFIX=1), pre_pr.py is one parallel
    # job among several. Printing success guidance is false: this job only
    # validated its own subset and has no visibility into sibling jobs
    # (python-tests, ratchets) that may still be running or may have failed.
    # Issue #4506.
    if os.environ.get("SKIP_AUTOFIX") == "1":
        print("pre_pr validations passed (push outcome depends on sibling hook jobs).")
    else:
        print("Pre-PR checks passed. Verify the push landed before opening a PR:")
        print("  git rev-parse HEAD")
        print("  git ls-remote origin <branch>")
        print("The two commands must report the same SHA.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
