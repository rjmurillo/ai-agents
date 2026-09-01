#!/usr/bin/env python3
# taste-lint: ignore file-size
#
# file-size suppression rationale: this module is a registration sequence, not
# logic. It holds one function whose body is ordered ``run_validation`` calls,
# so its line count tracks how many gates the project has, not how hard the
# module is to read. The rule's own remediation (extract helpers) does not
# apply: the docstring below records that this file was itself extracted from
# ``pre_pr.py`` for the same ceiling. The real fix is a table-driven registry
# (issue #4285), which is out of scope for the change that crossed the line.
"""Ordered pre-PR validation sequence (extracted from ``pre_pr.py``, Issue #3073).

Holds ``run_all_validations``: the ordered list of gates that ``pre_pr.main()``
used to inline. Extracted so ``pre_pr.py`` stays under the module size ceiling
while a new governance gate is added.

The sequence is data. ``_SEQUENCE`` is a tuple of ``_Gate`` rows read top to
bottom by one loop, so ordering is visible as a list rather than inferred from
408 lines of call sites (issue #4285). Adding a gate is a one-line edit, and the
module's length now tracks how many gates exist without pretending to measure
complexity.

Validators are imported directly from the ``checks_*`` sibling modules, not from
``pre_pr``: ``pre_pr`` runs as ``__main__`` when invoked as a script, so
``from pre_pr import ...`` would import a second copy of that module. The
``run_validation`` runner and ``ValidationState`` are injected by the caller for
the same reason (they live in ``pre_pr`` and would otherwise force a cycle).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from active_plan_closeout import validate_active_plan_closeout
from check_adr_lifecycle import validate_adr_lifecycle
from check_adr_links import validate_adr_links
from check_citation_freshness import validate_citation_freshness
from check_doc_interpreter_portability import (
    validate_doc_interpreter_portability,
)
from check_duplicate_test_helpers import validate_duplicate_test_helpers
from check_generated_staleness import validate_generated_staleness
from check_git_hook_health import validate_git_hook_health
from check_nested_tests import validate_no_nested_tests
from check_push_lock_paths import validate_push_lock_paths
from check_subprocess_encoding import validate_subprocess_encoding
from check_test_tree_writes import validate_test_tree_writes
from check_tmp_worktrees import validate_tmp_worktrees
from check_unreachable_code import validate_unreachable_code
from check_worktree_recipes import validate_worktree_recipes
from checks_coverage import (
    validate_review_marker,
)
from checks_dash import validate_dash_prohibition
from checks_mypy import validate_mypy_changed_files
from checks_plugin import (
    validate_agent_content_parity,
    validate_colocated_skill_tests,
    validate_copilot_agent_frontmatter,
    validate_hook_anchoring,
    validate_install_parity,
    validate_lefthook_installed,
    validate_plugin_version_bump,
    validate_shipped_skill_routes,
    validate_workflow_local_run,
)
from checks_ratchet import validate_count_ratchets
from checks_spec import (
    validate_agent_catalog,
    validate_build_gates,
    validate_canonical_citations,
    validate_model_pins,
    validate_orchestrator_citations,
    validate_rule_activation_coverage,
    validate_skill_md_portability,
    validate_skill_memory_references,
    validate_skill_shells,
    validate_skill_skip_clauses,
    validate_spec_contradiction,
    validate_spec_id_uniqueness,
    validate_sync_registry,
    validate_traceability,
    validate_vendor_portability,
)
from checks_tooling import (
    validate_agent_drift,
    validate_always_on_corpus_claims,
    validate_ci_dependency_pins,
    validate_copilot_version_pin,
    validate_instruction_budget,
    validate_markdown_lint,
    validate_path_normalization,
    validate_planning_artifacts,
    validate_session_end,
    validate_workflow_yaml,
    validate_yaml_style,
)
from stale_script_refs import validate_stale_script_refs
from validate_argument_hint import validate_argument_hint
from validate_design_review import validate_design_review_frontmatter
from validate_no_orphaned_build_deferrals import (
    validate_no_orphaned_build_deferrals,
)
from validate_python_syntax import validate_python_syntax

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable


class _ValidationStateLike(Protocol):
    """Structural view of ``pre_pr.ValidationState`` the sequence writes to.

    Typed structurally rather than imported from ``pre_pr`` so this module never
    references ``pre_pr``. ``pre_pr`` imports this module; a back-reference would
    make mypy resolve ``pre_pr`` under two module names (Issue #3073).
    """

    total: int
    skipped: int


FAST_STAGE_RAN_ENV = "AI_AGENTS_PRE_PR_FAST_STAGE_RAN"


@dataclass(frozen=True)
class _Gate:
    """One row of the ordered sequence.

    ``run`` receives the repo root and the parsed CLI namespace and returns the
    validator's pass/fail. Taking both keeps every row the same shape, so the
    three gates that need more than a repo root do not need a second mechanism.

    ``skip_when_quick`` maps to ``run_validation(..., skip=...)``, which records a
    SKIP result. ``skip_flag`` is different: it names an ``args`` attribute that,
    when truthy, bypasses ``run_validation`` entirely and only bumps the totals.
    Only ``--skip-tests`` behaves that way, and it predates the SKIP record.

    ``already_run_by`` names an unconditional pre-push fast-stage job that runs
    the same whole-tree check. The piped hook cannot start pre-pr-validation
    unless that job passed. Direct and CI callers leave
    :data:`FAST_STAGE_RAN_ENV` unset and run the full sequence.
    """

    name: str
    run: Callable[[Path, argparse.Namespace], bool]
    skip_when_quick: bool = False
    skip_flag: str | None = None
    skip_note: str = ""
    already_run_by: str = ""
    notes: str = field(default="", repr=False)


def _root_only(validator: Callable[[Path], bool]) -> Callable[[Path, argparse.Namespace], bool]:
    """Adapt a ``validate_x(repo_root)`` validator to the uniform gate signature.

    The validator is resolved by name at call time, not captured at import.
    ``_SEQUENCE`` is built once at module import, so capturing the function
    object would freeze it and a wiring test that rebinds the module attribute
    could never observe the call. Per-consumer wiring tests are required here
    (``testing.md`` SHOULD 6), so the indirection is what keeps them able to
    fail.
    """

    name = validator.__name__

    def _run(repo_root: Path, _args: argparse.Namespace) -> bool:
        current = cast("Callable[[Path], bool]", globals().get(name, validator))
        return current(repo_root)

    return _run


def _run_orphaned_build_deferrals(repo_root: Path, _args: argparse.Namespace) -> bool:
    """Honor ``GH_REPO`` so the gate can run against a different upstream.

    The validator keeps the canonical default when ``GH_REPO`` is unset, so the
    override is passed positionally only when the environment supplies one.
    """
    deferral_repo = os.environ.get("GH_REPO")
    return bool(
        validate_no_orphaned_build_deferrals(
            repo_root / "build" / "scripts" / "build_all.py",
            *([deferral_repo] if deferral_repo else []),
        )
    )


def _run_copilot_routing_exclusions(repo_root: Path, _args: argparse.Namespace) -> bool:
    """Import lazily; ``run_validation`` turns any raise into a recorded failure.

    The previous shape wrapped both the import and the ``run_validation`` call in
    one ``try``, so a raise from the runner would have run the gate a second time
    and double-counted ``state.total``. Importing inside the callback keeps the
    failure path to one record and reports the real import error rather than a
    fixed string.
    """
    from checks_copilot import validate_copilot_routing_exclusions

    return bool(validate_copilot_routing_exclusions(repo_root))


_SEQUENCE: tuple[_Gate, ...] = (
    # Blocking parse gate over every tracked .py file (issue #2655). A
    # SyntaxError in a hook module wedges the CLI (the PreToolUse dispatcher
    # fails closed on import), and ruff/pytest never caught PR #2640 because
    # ruff is advisory and nothing imports those modules. Runs first and fast so
    # the cheapest, highest-impact defect is caught before anything slower.
    _Gate("Python Syntax (compile gate)", _root_only(validate_python_syntax)),
    # Second so the cheapest push-blocking signal arrives first. See the
    # checks_ratchet module docstring for why these run here (issue #4251).
    _Gate(
        "Count Ratchets",
        _root_only(validate_count_ratchets),
        already_run_by="count-ratchets",
    ),
    _Gate("Nested Test Detection", _root_only(validate_no_nested_tests)),
    _Gate("Duplicate Test Helper Detection", _root_only(validate_duplicate_test_helpers)),
    _Gate(
        "Unreachable Code Detection",
        _root_only(validate_unreachable_code),
        already_run_by="python-unreachable-statements",
    ),
    _Gate("Subprocess Encoding Convention", _root_only(validate_subprocess_encoding)),
    _Gate("Test Working Tree Writes", _root_only(validate_test_tree_writes)),
    _Gate("Push Lock Path Agreement", _root_only(validate_push_lock_paths)),
    # Blocks a tracked prescription that tells a reader to create a worktree
    # under /tmp or inside the checkout, against universal.md MUST NOT 7. Issue
    # #5111: the rule, a Serena memory, and a prior incident all already
    # existed, and six violations still accumulated, because nothing read the
    # recipes.
    _Gate("Worktree Recipe Destinations", _root_only(validate_worktree_recipes)),
    # Advisory companion to the gate above: the same rule measured against the
    # machine rather than the tree. Reports worktrees sitting under /tmp
    # (including orphans git no longer lists) and a low /tmp free-space floor.
    # Never fails; see the validator's docstring for why machine state does not
    # get to block a push. Issue #5111.
    _Gate("Temp-filesystem Worktrees (advisory)", _root_only(validate_tmp_worktrees)),
    _Gate("Session End Validation", _root_only(validate_session_end)),
    # Type-check changed Python files with ratchet semantics (issue #4674).
    # Surfaces regressions at pre-PR time rather than waiting for push CI.
    _Gate("Mypy Changed Files (ratchet)", _root_only(validate_mypy_changed_files)),
    _Gate("Markdown Linting", _root_only(validate_markdown_lint)),
    _Gate("Workflow YAML Validation", _root_only(validate_workflow_yaml)),
    # Fails when the pinned @github/copilot version is missing, unparseable, or
    # known-bad (0.0.397). Issue #2630.
    _Gate("Copilot CLI Version Pin", _root_only(validate_copilot_version_pin)),
    # Fails when a hand-written pkg==version literal under .github/ contradicts
    # the pyproject constraint for that package (issue #3377). Two pytest pins
    # disagreed and one sat a major below the declared floor; a review then
    # proposed aligning the correct one down.
    _Gate("CI Dependency Pins", _root_only(validate_ci_dependency_pins)),
    # Ratcheted lifecycle gate over .agents/architecture/ADR-NNN-*.md (issue
    # #5191). Sits beside the DESIGN-REVIEW gate because both read frontmatter
    # in the same directory. Read-only: ADR-073 forbids rewriting prose.
    _Gate("ADR Lifecycle Frontmatter (ratchet)", _root_only(validate_adr_lifecycle)),
    # Resolves every markdown link naming an ADR, and checks that a link whose
    # text says ADR-NNN targets that number (issue #5197). Unwired, this gate
    # cannot stop the rot that produced the ADR-033 repairs it protects.
    _Gate("ADR Link Resolution", _root_only(validate_adr_links)),
    _Gate("Design Review Frontmatter", _root_only(validate_design_review_frontmatter)),
    # PR #1887 retrospective, Layer 2.
    _Gate("Build Command Exit Gates", _root_only(validate_build_gates)),
    # Fails when live docs command a removed script (issue #2916), the
    # PowerShell-to-Python migration regression behind issues #2914 and #2915.
    _Gate("Stale Script References", _root_only(validate_stale_script_refs)),
    # Fails when a line ADDED since the base ref cites a path-and-line
    # location that HEAD contradicts: file untracked, line out of range, or
    # the named anchor content living elsewhere. Automates the manual
    # git-grep gate canonical-source-mirror.md prescribes; mechanically
    # checkable claims were reaching paid AI review rounds instead (PR #5336
    # existed solely to repair four such citations; issue #5337).
    _Gate("Citation Freshness (added lines)", _root_only(validate_citation_freshness)),
    # Fails when a live doc tells a contributor to run a script with third-party
    # imports under a bare `python3`, which dies with ModuleNotFoundError on a
    # clean checkout. Issue #3791.
    _Gate("Documented Interpreter Portability", _root_only(validate_doc_interpreter_portability)),
    # Fails when a staleness-deferral exemption in build_all.py cites a CLOSED
    # tracking issue, the orphan signature that hid stale mirrors before #2780.
    # Issue #2770.
    _Gate("Orphaned Build Deferrals", _run_orphaned_build_deferrals),
    # The gate above reads deferral comments inside build_all.py's source. This
    # one asks the separate question CI asks: is the generated tree stale
    # against its inputs. Runs sync_plugin_lib.py --check then
    # build/scripts/build_all.py --check, in the order
    # .claude/rules/generated-artifacts.md requires. Both are read-only.
    # Issue #5079: without it, a hand-edit to a generated file cleared every
    # local gate and the generator silently reverted it in CI (PR #5059).
    _Gate("Generated Artifact Staleness", _root_only(validate_generated_staleness)),
    _Gate("Spec ID Uniqueness", _root_only(validate_spec_id_uniqueness)),  # Issue #2068
    _Gate("Traceability", _root_only(validate_traceability)),
    # No new hard-coded upstream-only paths (issue #2050).
    _Gate("Vendor Portability", _root_only(validate_vendor_portability)),
    # The same rule over .md path refs (issue #2050).
    _Gate("Skill Markdown Portability", _root_only(validate_skill_md_portability)),
    # Skill dir with tracked content but no SKILL.md (issue #2677). Catches an
    # "invisible" skill the catalog still counts after a prune removed its
    # SKILL.md but left tracked files behind.
    _Gate("Skill Shell Detection", _root_only(validate_skill_shells)),
    # Fails when a multi-member leading-token skill family lacks a well-formed
    # route to a real sibling. Issue #3484.
    _Gate("Skill SKIP Clause Routing", _root_only(validate_skill_skip_clauses)),
    # Fails when a skill or agent instruction commands read_memory or
    # edit_memory on a name that resolves to no tracked memory. Issue #4897:
    # pr-comment-responder's BLOCKING Phase 0 named an unscoped memory, so the
    # blocking step failed for any agent that ran the instruction literally.
    _Gate("Skill Memory References", _root_only(validate_skill_memory_references)),
    # Block new test files colocated in customer-shipped skill dirs. Issue #4838.
    _Gate("Colocated Skill Tests", _root_only(validate_colocated_skill_tests)),
    # Ratchet (issue #3457). Fails when a rule or skill has no activation
    # scenario and is not baselined, or when a scenario points at a deleted
    # artifact. Fail-closed on any config or structural fault so an unmeasured
    # artifact never reads as clean.
    _Gate("Rule Activation Coverage", _root_only(validate_rule_activation_coverage)),
    # Copilot shipped skills must not route to an excluded skill name
    # (templates/platforms/copilot-cli.yaml).
    _Gate("Copilot Routing Exclusions", _run_copilot_routing_exclusions),
    _Gate("Sync Registry Provenance", _root_only(validate_sync_registry)),  # Issue #1909
    # docs/agent-catalog.md vs templates/agents/ (issue #1904).
    _Gate("Agent Catalog Drift", _root_only(validate_agent_catalog)),
    # Fails when a routing table in a shipped tree points at a skill that tree
    # does not ship. Issue #2026 coordination drift.
    _Gate("Shipped Skill Routes", _root_only(validate_shipped_skill_routes)),
    # Heuristic; soft warn unless STRICT_CANONICAL_CHECK=1. PR #1887
    # retrospective, Layer 4.
    _Gate("Canonical Citation Check", _root_only(validate_canonical_citations)),
    # Fails when a backtick path citation in .claude/commands/pr-quality/all.md
    # points to a file that no longer exists. Issue #1966.
    _Gate("Orchestrator Citation Check", _root_only(validate_orchestrator_citations)),
    # Branch-wide em/en-dash check (issue #1923, REQ-006-AC7).
    _Gate("Em/en-dash Prohibition", _root_only(validate_dash_prohibition)),
    # Advisory (issue #1920). Catches the PR #1897 round-7 loop (linked issue
    # claims one model tier, committed agent frontmatter ships another) locally
    # instead of after each push.
    _Gate("Spec Contradiction Check", _root_only(validate_spec_contradiction)),
    # ADR-080, warn mode (issue #3073). Advisory gate wrapping
    # check_model_pins.py --mode warn. Surfaces unpinned or mismatched model
    # references locally; warn mode never blocks (enforcement stays in CI), but a
    # config error (exit 2) still fails.
    _Gate("Model Pin Governance (warn)", _root_only(validate_model_pins)),
    # Advisory warning when every tracking issue on an active execution plan is
    # closed, so stale plans do not silently refill .agents/plans/active/.
    # Issue #3426.
    _Gate("Active Plan Closeout Advisory", _root_only(validate_active_plan_closeout)),
    _Gate("YAML Style Validation", _root_only(validate_yaml_style), skip_when_quick=True),
    _Gate(
        "Path Normalization",
        _root_only(validate_path_normalization),
        skip_when_quick=True,
        already_run_by="path-normalization",
    ),
    _Gate(
        "Planning Artifacts",
        _root_only(validate_planning_artifacts),
        skip_when_quick=True,
        already_run_by="planning-artifacts",
    ),
    _Gate("Agent Drift Detection", _root_only(validate_agent_drift), skip_when_quick=True),
    # Changed-together sibling check; cheap, always on.
    _Gate("Install Parity (agents and rules)", _root_only(validate_install_parity)),
    # validate_install_parity checks co-change; it does not compare on-disk
    # content. This gate catches drift that already exists regardless of what
    # changed in the current PR. Issue #4082.
    _Gate(
        "Agent Content Parity (.claude/agents vs src/claude)",
        _root_only(validate_agent_content_parity),
    ),
    # A source change requires a plugin.json bump (issue #2118).
    _Gate("Plugin Version Bump", _root_only(validate_plugin_version_bump)),
    # Claude and Copilot plugin hooks.json must anchor to the plugin root. Bare
    # paths regressed Copilot CLI in #2205, and the same trap exists on Claude.
    _Gate("Hook Anchoring (Claude + Copilot)", _root_only(validate_hook_anchoring)),
    # Copilot agent frontmatter must parse as YAML (#2491 through #2496): an
    # unquoted description embedding colon-bearing examples makes Copilot fail to
    # load the agent.
    _Gate("Copilot Agent Frontmatter", _root_only(validate_copilot_agent_frontmatter)),
    # Argument-hint frontmatter must be a bracket-safe string scalar: adjacent
    # optional groups (e.g. ``[a] [b]``) make Copilot CLI parse separate flow
    # nodes. Canonical CI source: .github/workflows/validate-generated-agents.yml,
    # step "Validate Copilot agent frontmatter (issues #2491-#2497, #2500)", which
    # runs doc-interpreter-portability: verbatim CI quote; CI installs deps
    # system-wide verbatim: ``python3 scripts/validation/validate_argument_hint.py``.
    # This local check calls validate_argument_hint() over the same default scan
    # surface.
    _Gate("Argument-Hint Frontmatter", _root_only(validate_argument_hint)),
    # Deeper than the gate below, and adjacent so neither reads as covering the
    # other. "Lefthook Installed" asks whether lefthook considers itself
    # installed; this asks whether git will read those shims at all. A
    # core.hooksPath pointing at a missing directory makes git run no hook and
    # print no warning, which is how the PR #5059 hand-edit reached CI instead
    # of being refused at push time. Issue #5090; the same repair already
    # drifted back once after 2026-07-19.
    _Gate("Git Hook Health (core.hooksPath)", _root_only(validate_git_hook_health)),
    # Local clones must dispatch repository guardrails. Skipped under CI, where
    # workflows invoke validation directly.
    _Gate("Lefthook Installed", _root_only(validate_lefthook_installed)),
    # actionlint plus gh act dry-run for changed workflows.
    _Gate("Workflow Local Run", _root_only(validate_workflow_local_run)),
    # Advisory by default; /ship blocks (issue #1938). Reports whether HEAD
    # carries a SHA-bound Reviewed-By: /review@... marker.
    _Gate("Review Marker (SHA-bound /review)", _root_only(validate_review_marker)),
    # Always-on non-regression ratchet (issue #3419) on the summed bytes of
    # language-universal .github/instructions/*.instructions.md files, so the
    # always-on corpus cannot grow silently on a new all-language rule.
    _Gate("Instruction Budget (always-on)", _root_only(validate_instruction_budget)),
    # Pins the numeric claims in model-context-doctrine.md to live measurements.
    # The budget gate above checks a ceiling; this gate checks the exact figures
    # (byte counts, file counts, multipliers) stated in the doctrine doc, so a
    # rule growing by 400 bytes surfaces locally in under 0.5 seconds instead of
    # 17 minutes later in CI. Issue #4285.
    _Gate("Always-on Corpus Claims", _root_only(validate_always_on_corpus_claims)),
)


def run_all_validations(
    repo_root: Path,
    args: argparse.Namespace,
    state: _ValidationStateLike,
    run_validation: Callable[..., bool],
) -> None:
    """Run the ordered pre-PR validation sequence, recording into ``state``.

    ``run_validation`` and ``state`` are owned by ``pre_pr.main()`` and injected
    to avoid importing ``pre_pr`` (which runs as ``__main__``). ``args`` supplies
    the CLI flags (``quick``, ``skip_tests``, ``verbose``) the sequence reads.

    The order is ``_SEQUENCE``. Read that table, not this loop.
    """
    fast_stage_ran = os.environ.get(FAST_STAGE_RAN_ENV) == "1"
    for gate in _SEQUENCE:
        if gate.skip_flag is not None and getattr(args, gate.skip_flag, False):
            print(f"[SKIP] {gate.name} ({gate.skip_note})")
            state.total += 1
            state.skipped += 1
            continue

        if fast_stage_ran and gate.already_run_by:
            print(
                f"[SKIP] {gate.name} (already passed as the unconditional "
                f"pre-push job {gate.already_run_by})"
            )
            state.total += 1
            state.skipped += 1
            continue

        run_validation(
            gate.name,
            state,
            lambda g=gate: g.run(repo_root, args),
            skip=gate.skip_when_quick and args.quick,
        )
