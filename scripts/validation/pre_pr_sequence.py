#!/usr/bin/env python3
"""Ordered pre-PR validation sequence (extracted from ``pre_pr.py``, Issue #3073).

Holds ``run_all_validations``: the ordered list of ``run_validation`` calls that
``pre_pr.main()`` used to inline. Extracted so ``pre_pr.py`` stays under the
module size ceiling while a new governance gate is added.

Validators are imported directly from the ``checks_*`` sibling modules, not from
``pre_pr``: ``pre_pr`` runs as ``__main__`` when invoked as a script, so
``from pre_pr import ...`` would import a second copy of that module. The
``run_validation`` runner and ``ValidationState`` are injected by the caller for
the same reason (they live in ``pre_pr`` and would otherwise force a cycle).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from active_plan_closeout import validate_active_plan_closeout
from checks_coverage import (  # noqa: E402
    validate_review_marker,
)
from checks_dash import validate_dash_prohibition  # noqa: E402
from checks_plugin import (  # noqa: E402
    validate_copilot_agent_frontmatter,
    validate_hook_anchoring,
    validate_install_parity,
    validate_lefthook_installed,
    validate_plugin_version_bump,
    validate_workflow_local_run,
)
from checks_spec import (  # noqa: E402
    validate_agent_catalog,
    validate_build_gates,
    validate_canonical_citations,
    validate_model_pins,
    validate_orchestrator_citations,
    validate_rule_activation_coverage,
    validate_skill_md_portability,
    validate_skill_shells,
    validate_spec_contradiction,
    validate_spec_id_uniqueness,
    validate_sync_registry,
    validate_traceability,
    validate_vendor_portability,
)
from checks_tooling import (  # noqa: E402
    validate_agent_drift,
    validate_ci_dependency_pins,
    validate_copilot_version_pin,
    validate_instruction_budget,
    validate_markdown_lint,
    validate_path_normalization,
    validate_pester_tests,
    validate_planning_artifacts,
    validate_session_end,
    validate_workflow_yaml,
    validate_yaml_style,
)
from stale_script_refs import validate_stale_script_refs  # noqa: E402
from validate_argument_hint import validate_argument_hint  # noqa: E402
from validate_design_review import validate_design_review_frontmatter  # noqa: E402
from validate_no_orphaned_build_deferrals import (  # noqa: E402
    validate_no_orphaned_build_deferrals,
)
from validate_python_syntax import validate_python_syntax  # noqa: E402

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
    """
    quick = args.quick

    # 0. Python Syntax (issue #2655). Blocking parse gate over every tracked
    # .py file. A SyntaxError in a hook module wedges the CLI (PreToolUse
    # dispatcher fails closed on import), and ruff/pytest never caught PR #2640
    # because ruff is advisory and nothing imports those modules. Runs first
    # and fast so the cheapest, highest-impact defect is caught before anything
    # slower.
    run_validation(
        "Python Syntax (compile gate)",
        state,
        lambda: validate_python_syntax(repo_root),
    )

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

    # 3.55 Copilot CLI Version Pin (Issue #2630). Fails when the pinned
    # @github/copilot version is missing, unparseable, or known-bad (0.0.397).
    run_validation(
        "Copilot CLI Version Pin",
        state,
        lambda: validate_copilot_version_pin(repo_root),
    )

    # 3.57 CI Dependency Pins (Issue #3377). Fails when a hand-written
    # pkg==version literal under .github/ contradicts the pyproject constraint
    # for that package. Two pytest pins disagreed and one sat a major below the
    # declared floor; a review then proposed aligning the correct one down.
    run_validation(
        "CI Dependency Pins",
        state,
        lambda: validate_ci_dependency_pins(repo_root),
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

    # 3.71 Stale script refs (Issue #2916). Fails when live docs command a
    # removed script, the PowerShell-to-Python migration regression behind
    # issues #2914 and #2915.
    run_validation(
        "Stale Script References",
        state,
        lambda: validate_stale_script_refs(repo_root),
    )

    # 3.72 Orphaned build_all --check deferrals (Issue #2770). Fails when a
    # staleness-deferral exemption in build_all.py cites a CLOSED tracking
    # issue, the orphan signature that hid stale mirrors before #2780. Honor
    # GH_REPO so the gate can run against a different upstream without code edits;
    # the validator keeps the canonical default when GH_REPO is unset.
    deferral_repo = os.environ.get("GH_REPO")
    run_validation(
        "Orphaned Build Deferrals",
        state,
        lambda: validate_no_orphaned_build_deferrals(
            repo_root / "build" / "scripts" / "build_all.py",
            *([deferral_repo] if deferral_repo else []),
        ),
    )

    # 3.75 Spec ID Uniqueness (Issue #2068)
    run_validation(
        "Spec ID Uniqueness",
        state,
        lambda: validate_spec_id_uniqueness(repo_root),
    )

    run_validation(
        "Traceability",
        state,
        lambda: validate_traceability(repo_root),
    )

    # 3.76 Vendor Portability (no new hard-coded upstream-only paths; Issue #2050)
    run_validation(
        "Vendor Portability",
        state,
        lambda: validate_vendor_portability(repo_root),
    )

    # 3.765 Skill Markdown Vendor Portability (.md path refs; Issue #2050)
    run_validation(
        "Skill Markdown Portability",
        state,
        lambda: validate_skill_md_portability(repo_root),
    )

    # 3.766 Skill Shell Detection (skill dir with tracked content but no
    # SKILL.md; Issue #2677). Catches an "invisible" skill the catalog still
    # counts after a prune removed its SKILL.md but left tracked files behind.
    run_validation(
        "Skill Shell Detection",
        state,
        lambda: validate_skill_shells(repo_root),
    )

    # 3.767 Rule and Skill Activation Coverage (ratchet; Issue #3457). Fails
    # when a rule or skill has no activation scenario and is not baselined, or
    # when a scenario points at a deleted artifact. Fail-closed on any config
    # or structural fault so an unmeasured artifact never reads as clean.
    run_validation(
        "Rule Activation Coverage",
        state,
        lambda: validate_rule_activation_coverage(repo_root),
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


    # 3.88 Model Pin Governance (ADR-080, warn mode; Issue #3073). Advisory
    # gate wrapping check_model_pins.py --mode warn. Surfaces unpinned or
    # mismatched model references locally; warn mode never blocks (enforcement
    # stays in CI), but a config error (exit 2) still fails.
    run_validation(
        "Model Pin Governance (warn)",
        state,
        lambda: validate_model_pins(repo_root),
    )

    # 3.89 Active Plan Closeout (Issue #3426). Advisory warning when every
    # tracking issue on an active execution plan is closed, so stale plans do
    # not silently refill .agents/plans/active/.
    run_validation(
        "Active Plan Closeout Advisory",
        state,
        lambda: validate_active_plan_closeout(repo_root),
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

    # 6c4. Argument-hint frontmatter must be a bracket-safe string scalar: adjacent
    # optional groups (e.g. ``[a] [b]``) make Copilot CLI parse separate flow nodes.
    # Canonical CI source: .github/workflows/validate-generated-agents.yml, step
    # "Validate Copilot agent frontmatter (issues #2491-#2497, #2500)", which runs
    # verbatim: ``python3 scripts/validation/validate_argument_hint.py``. This local
    # check calls validate_argument_hint() over the same default scan surface.
    run_validation(
        "Argument-Hint Frontmatter",
        state,
        lambda: validate_argument_hint(repo_root),
    )

    # 6d. Lefthook Installed (local clones must dispatch repository guardrails).
    # Skipped under CI, where workflows invoke validation directly.
    run_validation(
        "Lefthook Installed",
        state,
        lambda: validate_lefthook_installed(repo_root),
    )

    # 6e. Workflow Local Run (actionlint + gh act dry-run for changed workflows)
    run_validation(
        "Workflow Local Run",
        state,
        lambda: validate_workflow_local_run(repo_root),
    )

    # 7. Review Marker (advisory by default; /ship blocks, Issue #1938).
    # Reports whether HEAD carries a SHA-bound Reviewed-By: /review@... marker.
    run_validation(
        "Review Marker (SHA-bound /review)",
        state,
        lambda: validate_review_marker(repo_root),
    )

    # 7c. Instruction Budget (always-on, Issue #3419). Non-regression ratchet on
    # the summed bytes of language-universal .github/instructions/*.instructions.md files, so
    # the always-on corpus cannot grow silently on a new all-language rule.
    run_validation(
        "Instruction Budget (always-on)",
        state,
        lambda: validate_instruction_budget(repo_root),
    )
