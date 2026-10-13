#!/usr/bin/env python3
"""Re-exports of the validators ``pre_pr.py`` does not import by name itself.

``pre_pr.py`` is a facade (issue #2223): ``from scripts.validation.pre_pr
import X`` must resolve for every ``validate_*`` that ``pre_pr_sequence`` imports.
``pre_pr.py`` star-imports this module so the names land in its namespace as
the identical objects, and so the runner stays under the 500-line ceiling
(issue #3073). It relies on ``pre_pr.py`` having put ``scripts/validation`` on
``sys.path`` before the star import.

Add a validator here when ``pre_pr_sequence`` imports it and ``pre_pr.py`` does
not already. ``tests/validation/test_pre_pr_sequence_registry.py`` fails
until you do (issue #5272).
"""

from __future__ import annotations

from check_adr_exception_markers import validate_adr_exception_markers
from check_agent_tree_frontmatter import validate_agent_tree_frontmatter
from check_agents_write_targets import validate_agents_write_targets
from check_bypass_allowlist import validate_bypass_allowlist
from check_duplicate_test_helpers import validate_duplicate_test_helpers
from check_generated_staleness import validate_generated_staleness
from check_git_hook_health import validate_git_hook_health
from check_in_root_worktrees import validate_in_root_worktrees
from check_index_line_endings import validate_index_line_endings
from check_promotion_exceptions import validate_promotion_exceptions
from check_push_lock_paths import validate_push_lock_paths
from check_required_context_conditions import validate_required_context_conditions
from check_serena_memory_worktree_scope import validate_serena_memory_worktree_scope
from check_skill_tree_layout import validate_skill_tree_layout
from check_tmp_worktrees import validate_tmp_worktrees
from check_worktree_recipes import validate_worktree_recipes
from checks_ci_parity import validate_closure_manifest, validate_memory_placement
from checks_copilot import validate_copilot_routing_exclusions
from checks_mypy import validate_mypy_changed_files
from checks_plugin import validate_agent_content_parity
from checks_portability import validate_agent_template_drift, validate_plugin_root_interpreter
from checks_ratchet import validate_count_ratchets
from checks_spec import (
    validate_commands_retired,
    validate_rule_activation_coverage,
    validate_skill_memory_references,
    validate_skill_skip_clauses,
    validate_traceability,
)
from checks_tooling import (
    validate_always_on_corpus_claims,
    validate_capability_graph_declarations,
    validate_effective_context_ratchet,
    validate_instruction_budget,
    validate_instruction_bytes,
    validate_nl_structural_debt_ratchet,
    validate_rule_scope_declarations,
    validate_skill_routing_roles_declarations,
)

__all__ = [
    "validate_agent_content_parity",
    "validate_agent_template_drift",
    "validate_adr_exception_markers",
    "validate_agent_tree_frontmatter",
    "validate_agents_write_targets",
    "validate_always_on_corpus_claims",
    "validate_bypass_allowlist",
    "validate_capability_graph_declarations",
    "validate_closure_manifest",
    "validate_commands_retired",
    "validate_copilot_routing_exclusions",
    "validate_count_ratchets",
    "validate_duplicate_test_helpers",
    "validate_effective_context_ratchet",
    "validate_generated_staleness",
    "validate_git_hook_health",
    "validate_in_root_worktrees",
    "validate_index_line_endings",
    "validate_instruction_budget",
    "validate_instruction_bytes",
    "validate_memory_placement",
    "validate_mypy_changed_files",
    "validate_nl_structural_debt_ratchet",
    "validate_plugin_root_interpreter",
    "validate_promotion_exceptions",
    "validate_push_lock_paths",
    "validate_required_context_conditions",
    "validate_rule_activation_coverage",
    "validate_rule_scope_declarations",
    "validate_serena_memory_worktree_scope",
    "validate_skill_memory_references",
    "validate_skill_routing_roles_declarations",
    "validate_skill_skip_clauses",
    "validate_skill_tree_layout",
    "validate_tmp_worktrees",
    "validate_traceability",
    "validate_worktree_recipes",
]
