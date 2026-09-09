#!/usr/bin/env python3
"""Unified shift-left validation runner for pre-PR checks.

Runs all local validations before creating a pull request.
Executes validations in optimized order (fast checks first).

The ordered gate list is ``_SEQUENCE`` in ``pre_pr_sequence``. Read it there.
This docstring deliberately keeps no second copy: the 12-row list it used to
carry had drifted to describe a 63-gate sequence, and named a Pester stage and
three "requires PS1" gates that are Python ports run through
``_run_python_validator`` in a repository tracking zero ``.ps1`` files.
``.agents/devops/SHIFT-LEFT.md`` documents the same rule and the
command that prints the live sequence.

Exit codes follow ADR-035, chosen by the worst state that blocked the gate
(``scripts/validation/evidence.py:exit_code_for``, issue #5635):
    0 - Success (nothing blocked)
    1 - Logic error (a FAIL, or an UNKNOWN whose evidence was unreadable)
    2 - Config error (a bad repository root, or a SKIP the policy refused)
    3 - External (a BLOCKED gate: a dependency or service was unavailable)

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
import json
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
from check_citation_freshness import validate_citation_freshness
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
    validate_colocated_skill_tests,
    validate_copilot_agent_frontmatter,
    validate_hook_anchoring,
    validate_install_parity,
    validate_lefthook_installed,
    validate_plugin_version_bump,
    validate_shipped_skill_routes,
    validate_workflow_local_run,
)
from checks_portability import (
    validate_skill_contract_tests,
    validate_skill_md_exec_portability,
    validate_skill_resolver_anchoring,
    validate_skill_script_portability,
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

# The typed evidence contract (issue #5635). Imported by its PACKAGE path, not
# flat like the ``checks_*`` siblings above, because ``EvidenceState`` identity
# has to survive the two ways this directory is imported: a flat ``import
# evidence`` and a package ``import scripts.validation.evidence`` produce two
# distinct enum classes, and every ``is`` comparison across that seam returns
# False. Tests import the package path, so production code must too. Same
# convention as ``scripts.validation.models``.
from scripts.validation.evidence import (
    REASON_ALREADY_RUN,
    REASON_QUICK_MODE,
    REASON_SCRIPT_ABSENT,
    REASON_VALIDATOR_RAISED,
    AggregateOutcome,
    CheckOutcome,
    EvidenceState,
    GateResult,
    aggregate,
    coerce_outcome,
    default_pre_pr_policy,
    exit_code_for,
)

# The verdict reporters, extracted for the same size ceiling that produced
# ``pre_pr_sequence`` (issue #3073). Package path, for the ``EvidenceState``
# identity reason stated above. The private aliases keep ``pre_pr``'s existing
# surface: ``main`` looks these up as module globals, so
# ``patch.object(pre_pr, "_write_summary_json")`` in
# tests/validation/test_pre_pr_evidence_states.py still intercepts the call.
from scripts.validation.pre_pr_report import (
    print_blocking_guidance as _print_blocking_guidance,
)
from scripts.validation.pre_pr_report import (
    print_result_line as _print_result_line,
)
from scripts.validation.pre_pr_report import (
    write_summary_json as _write_summary_json,
)

#: The gate this runner enforces. PASS always passes; the one exception is
#: SKIP, which .agents/devops/SHIFT-LEFT.md already documented as
#: non-blocking before issue #5635. BLOCKED and UNKNOWN block.
_POLICY = default_pre_pr_policy()


@dataclass
class ValidationRecord:
    """Result of a single validation step.

    ``status`` is the :class:`EvidenceState` value as a bare string, kept for
    the many callers and tests that read ``record.status`` against ``"PASS"``.
    ``outcome`` is the typed evidence behind it: the reason code, the scope, the
    revision, and the counts (issue #5635).
    """

    name: str
    status: str  # PASS, FAIL, SKIP, BLOCKED, UNKNOWN
    duration: float = 0.0
    message: str = ""
    outcome: CheckOutcome | None = None


_COUNTER_FOR_STATE: dict[EvidenceState, str] = {
    EvidenceState.PASS: "passed",
    EvidenceState.FAIL: "failed",
    EvidenceState.SKIP: "skipped",
    EvidenceState.BLOCKED: "blocked",
    EvidenceState.UNKNOWN: "unknown",
}


@dataclass
class ValidationState:
    """Tracks overall validation results.

    ``blocked`` and ``unknown`` are separate counters rather than folded into
    ``passed``: before issue #5635 a gate that could not run and a gate whose
    evidence was unreadable both incremented ``passed``, which is the defect
    this contract removes.
    """

    results: list[ValidationRecord] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    blocked: int = 0
    unknown: int = 0

    def record(self, name: str, outcome: CheckOutcome) -> CheckOutcome:
        """Append one gate's outcome and update the counter for its state.

        Every gate lands here, including the ones the sequence short-circuits,
        so no child state is lost from the summary.
        """
        self.total += 1
        self.results.append(
            ValidationRecord(
                name=name,
                status=outcome.state.value,
                duration=outcome.duration_seconds,
                message=outcome.detail,
                outcome=outcome,
            )
        )
        counter = _COUNTER_FOR_STATE[outcome.state]
        setattr(self, counter, getattr(self, counter) + 1)
        return outcome

    def outcomes(self) -> tuple[CheckOutcome, ...]:
        """Return the typed outcomes recorded so far, in run order."""
        return tuple(record.outcome for record in self.results if record.outcome is not None)


def run_validation(
    name: str,
    state: ValidationState,
    callback: Callable[[], GateResult],
    skip: bool = False,
) -> bool:
    """Run one validation, record its typed outcome, and report whether it passed.

    Returns True when the outcome does not block the gate under
    :func:`default_pre_pr_policy`, so a SKIP still returns True and a BLOCKED or
    UNKNOWN does not. The exit code is decided in :func:`main` from the recorded
    outcomes, not from this return value.
    """
    if skip:
        outcome = CheckOutcome.skipped(
            name, reason=REASON_QUICK_MODE, detail="Skipped due to --quick flag"
        )
        print(f"[SKIP] {name} (skipped due to --quick flag)")
        state.record(name, outcome)
        return True

    print()
    print(f"=== {name} ===")
    print("[RUNNING] Starting validation...")

    start = time.monotonic()
    try:
        outcome = coerce_outcome(name, callback())
    except MissingScriptSkip as exc:
        outcome = CheckOutcome.skipped(
            name, reason=REASON_SCRIPT_ABSENT, detail=f"Skipped: {exc}"
        )
    except Exception as exc:
        # FAIL rather than UNKNOWN: this preserves the pre-#5635 exit behavior
        # for a raising validator. The reason code is what changed, so a reader
        # can tell a crash from a real finding without reading the log.
        outcome = CheckOutcome.failed(
            name, reason=REASON_VALIDATOR_RAISED, detail=f"Validation error: {exc}"
        )

    outcome = outcome.with_duration(time.monotonic() - start)
    state.record(name, outcome)

    print()
    examined = "" if outcome.examined is None else f" (examined {outcome.examined})"
    print(
        f"[{outcome.state.value}] {name} completed in "
        f"{outcome.duration_seconds:.2f}s{examined}"
    )
    if outcome.state is not EvidenceState.PASS:
        # Only a non-PASS row earns the full evidence line. Printing it for
        # every gate would bury the handful that need reading, and a PASS has
        # already said the one thing a reader wants: it proved its contract.
        print(f"  {outcome.summary_line()}")
        label = "Error" if outcome.state is EvidenceState.FAIL else "Note"
        print(f"{label}: {outcome.detail}")

    return _POLICY.accepts(outcome)


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
        help="Skip the slow gates (YAML style, path normalization, planning, drift)",
    )
    parser.add_argument(
        "--markdown-lint-only",
        action="store_true",
        help="Run only markdownlint against positional markdown files",
    )
    parser.add_argument(
        "--summary-json",
        default=os.environ.get("PRE_PR_SUMMARY_JSON", ""),
        metavar="PATH",
        help=(
            "Write the machine-readable run summary (per-gate state, reason code, "
            "scope, counts, and the gate policy) to PATH. Defaults to "
            "$PRE_PR_SUMMARY_JSON."
        ),
    )
    parser.add_argument(
        "markdown_files",
        nargs="*",
        help=argparse.SUPPRESS,
    )
    return parser


def _print_summary(summary: AggregateOutcome, state: ValidationState) -> None:
    """Print the per-state counts and one line per gate.

    Every non-``PASS`` line carries its reason code and scope, so a reader can
    tell a gate that did not apply from one whose base ref would not resolve
    without opening the log above (issue #5635).
    """
    counts = summary.counts()
    print()
    print("=== Validation Summary ===")
    print(f"Duration: {summary.duration_seconds:.2f}s")
    print(f"Total Validations: {state.total}")
    for label in ("PASS", "FAIL", "SKIP", "BLOCKED", "UNKNOWN"):
        print(f"{label}: {counts[label]}")
    print()

    print("=== Detailed Results ===")
    print()
    for record in state.results:
        duration_str = f" ({record.duration:.2f}s)" if record.duration > 0 else ""
        if record.outcome is None or record.outcome.state is EvidenceState.PASS:
            print(f"[{record.status}] {record.name}{duration_str}")
            continue
        print(
            f"[{record.status}] {record.name}{duration_str} "
            f"reason={record.outcome.reason} {record.outcome.detail}".rstrip()
        )
    print()


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

    summary = aggregate("pre_pr", state.outcomes(), _POLICY, total_duration)
    _print_summary(summary, state)
    _write_summary_json(summary, args.summary_json)

    if summary.blocking:
        _print_blocking_guidance(summary)
        return exit_code_for(summary)

    _print_result_line(summary)
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
