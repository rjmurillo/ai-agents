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
   10. Planning Artifacts (validate planning consistency) [skip if --quick, requires PS1]
   11. Agent Drift (detect semantic drift) [skip if --quick, requires PS1]

Exit codes follow ADR-035:
    0 - Success (all validations passed)
    1 - Logic error (one or more validations failed)
    2 - Config error (environment or configuration issue)

Decomposition (issue #2223): the individual validations live in sibling
``checks_*`` modules grouped by area, and this file is the thin runner plus a
facade that re-exports every validator. The runner calls the same validators in
the same order with the same exit semantics; the imports below keep
``from scripts.validation.pre_pr import X`` working for callers and tests.
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
from checks_common import (  # noqa: E402, F401
    MissingScriptSkip,
    _gh_base_ref,
    _resolve_branch_base_ref,
    _run_build_script_gate,
    _run_subprocess,
)

# Area check modules. Each ``validate_*`` is re-exported below so existing
# imports of ``scripts.validation.pre_pr`` continue to resolve (issue #2223).
from checks_coverage import (  # noqa: E402, F401
    validate_command_bundle_coverage,
    validate_review_marker,
)
from checks_dash import (  # noqa: E402, F401
    _branch_markdown_files,
    _find_dash_violations,
    _is_vendored,
    _print_dash_violations,
    validate_dash_prohibition,
)
from checks_plugin import (  # noqa: E402, F401
    _is_linked_worktree,
    validate_copilot_agent_frontmatter,
    validate_git_hooks_installed,
    validate_hook_anchoring,
    validate_install_parity,
    validate_plugin_version_bump,
    validate_workflow_local_run,
)
from checks_spec import (  # noqa: E402, F401
    validate_agent_catalog,
    validate_build_gates,
    validate_canonical_citations,
    validate_orchestrator_citations,
    validate_spec_contradiction,
    validate_spec_id_uniqueness,
    validate_sync_registry,
    validate_vendor_portability,
)
from checks_tooling import (  # noqa: E402, F401
    _find_latest_session_log,
    _markdown_lint_targets,
    validate_agent_drift,
    validate_markdown_lint,
    validate_path_normalization,
    validate_pester_tests,
    validate_planning_artifacts,
    validate_session_end,
    validate_workflow_yaml,
    validate_yaml_style,
)

# Frontmatter parsing and DESIGN-REVIEW validation live in sibling modules
# (issue #2223). Re-exported here so ``_parse_yaml_frontmatter`` and
# ``validate_design_review_frontmatter`` stay importable from ``pre_pr``.
from validate_design_review import (  # noqa: E402, F401
    _BLOCKING_STATUSES,
    _REQUIRED_FRONTMATTER_FIELDS,
    _VALID_PRIORITIES,
    _VALID_STATUSES,
    validate_design_review_frontmatter,
)
from yaml_utils import _parse_yaml_frontmatter  # noqa: E402, F401


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

    # 1. Session End
    run_validation(
        "Session End Validation",
        state,
        lambda: validate_session_end(repo_root),
    )

    # 2. Pester Tests
    if not args.skip_tests:
        run_validation(
            "Pester Unit Tests",
            state,
            lambda: validate_pester_tests(repo_root, args.verbose),
        )
    else:
        print("[SKIP] Pester Unit Tests (skipped via --skip-tests)")
        state.total += 1
        state.skipped += 1

    # 3. Markdown Lint
    run_validation(
        "Markdown Linting",
        state,
        lambda: validate_markdown_lint(repo_root),
    )

    # 3.5 Workflow YAML
    run_validation(
        "Workflow YAML Validation",
        state,
        lambda: validate_workflow_yaml(repo_root),
    )

    # 3.6 Design Review Frontmatter
    run_validation(
        "Design Review Frontmatter",
        state,
        lambda: validate_design_review_frontmatter(repo_root),
    )

    # 3.7 Build Command Exit Gates (PR #1887 retrospective Layer 2)
    run_validation(
        "Build Command Exit Gates",
        state,
        lambda: validate_build_gates(repo_root),
    )

    # 3.75 Spec ID Uniqueness (Issue #2068)
    run_validation(
        "Spec ID Uniqueness",
        state,
        lambda: validate_spec_id_uniqueness(repo_root),
    )

    # 3.76 Vendor Portability (no new hard-coded upstream-only paths; Issue #2050)
    run_validation(
        "Vendor Portability",
        state,
        lambda: validate_vendor_portability(repo_root),
    )

    # 3.77 Sync Registry Provenance (Issue #1909)
    run_validation(
        "Sync Registry Provenance",
        state,
        lambda: validate_sync_registry(repo_root),
    )

    # 3.78 Agent Catalog Drift (docs/agent-catalog.md vs templates/agents/; #1904)
    run_validation(
        "Agent Catalog Drift",
        state,
        lambda: validate_agent_catalog(repo_root),
    )

    # 3.8 Canonical Citation Check (heuristic; soft warn unless
    # STRICT_CANONICAL_CHECK=1; PR #1887 retrospective Layer 4)
    run_validation(
        "Canonical Citation Check",
        state,
        lambda: validate_canonical_citations(repo_root),
    )

    # 3.82 Orchestrator Citation Check (Issue #1966). Fails when a backtick
    # path citation in .claude/commands/pr-quality/all.md points to a file
    # that no longer exists.
    run_validation(
        "Orchestrator Citation Check",
        state,
        lambda: validate_orchestrator_citations(repo_root),
    )

    # 3.85 Em/en-dash branch-wide check (Issue #1923, REQ-006-AC7)
    run_validation(
        "Em/en-dash Prohibition",
        state,
        lambda: validate_dash_prohibition(repo_root),
    )

    # 3.87 Spec Contradiction Check (advisory; Issue #1920). Catches the
    # PR #1897 round-7 loop (linked issue claims one model tier, committed
    # agent frontmatter ships another) locally instead of after each push.
    run_validation(
        "Spec Contradiction Check",
        state,
        lambda: validate_spec_contradiction(repo_root),
    )

    # 3.9 YAML Style (skip if quick)
    run_validation(
        "YAML Style Validation",
        state,
        lambda: validate_yaml_style(repo_root),
        skip=quick,
    )

    # 4. Path Normalization (skip if quick)
    run_validation(
        "Path Normalization",
        state,
        lambda: validate_path_normalization(repo_root),
        skip=quick,
    )

    # 5. Planning Artifacts (skip if quick)
    run_validation(
        "Planning Artifacts",
        state,
        lambda: validate_planning_artifacts(repo_root),
        skip=quick,
    )

    # 6. Agent Drift (skip if quick)
    run_validation(
        "Agent Drift Detection",
        state,
        lambda: validate_agent_drift(repo_root),
        skip=quick,
    )

    # 6b. Install Parity (changed-together sibling check; cheap, always on)
    run_validation(
        "Install Parity (agents and rules)",
        state,
        lambda: validate_install_parity(repo_root),
    )

    # 6c. Plugin Version Bump (source change requires a plugin.json bump; #2118)
    run_validation(
        "Plugin Version Bump",
        state,
        lambda: validate_plugin_version_bump(repo_root),
    )

    # 6c2. Hook Anchoring (Claude + Copilot plugin hooks.json must anchor to the
    # plugin root; bare paths regressed Copilot CLI in #2205, same trap on Claude)
    run_validation(
        "Hook Anchoring (Claude + Copilot)",
        state,
        lambda: validate_hook_anchoring(repo_root),
    )

    # 6c3. Copilot agent frontmatter must parse as YAML (#2491-#2496): an unquoted
    # description embedding colon-bearing examples makes Copilot fail to load the agent.
    run_validation(
        "Copilot Agent Frontmatter",
        state,
        lambda: validate_copilot_agent_frontmatter(repo_root),
    )

    # 6d. Git Hooks Installed (local clone must run the canonical .githooks;
    # a desynced hooksPath bypasses the pre-push guards). Skipped under CI.
    run_validation(
        "Git Hooks Installed",
        state,
        lambda: validate_git_hooks_installed(repo_root),
    )

    # 6e. Workflow Local Run (actionlint + gh act dry-run for changed workflows)
    run_validation(
        "Workflow Local Run",
        state,
        lambda: validate_workflow_local_run(repo_root),
    )

    # 7. Command-Skill Bundle Coverage (advisory by default; SPEC-005 AC-14)
    run_validation(
        "Command-Skill Bundle Coverage",
        state,
        lambda: validate_command_bundle_coverage(repo_root),
    )

    # 7b. Review Marker (advisory by default; /ship blocks, Issue #1938).
    # Reports whether HEAD carries a SHA-bound Reviewed-By: /review@... marker.
    run_validation(
        "Review Marker (SHA-bound /review)",
        state,
        lambda: validate_review_marker(repo_root),
    )

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
    print("Ready to create pull request!")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
