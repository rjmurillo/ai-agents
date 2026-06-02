"""Canonical: scripts/ai_review_common/__init__.py. Sync via scripts/sync_plugin_lib.py."""

from __future__ import annotations

from .feature_review import (
    VALID_RECOMMENDATIONS,
    get_feature_review_assignees,
    get_feature_review_labels,
    get_feature_review_recommendation,
)
from .issue_triage import (
    convert_to_json_escaped,
    format_collapsible_section,
    format_markdown_table_row,
    format_verdict_alert,
    get_verdict_alert_type,
    get_verdict_emoji,
    get_verdict_exit_code,
    write_github_output,
    write_log,
    write_log_error,
    write_output,
    write_step_summary,
)
from .quality_gate import (
    FAIL_VERDICTS,
    SAFE_NAME_PATTERN,
    assert_environment_variables,
    extract_verdict,
    get_concurrency_group_from_run,
    get_failure_category,
    get_labels,
    get_labels_from_ai_output,
    get_milestone,
    get_milestone_from_ai_output,
    get_pr_changed_files,
    get_verdict,
    get_workflow_runs_by_pr,
    initialize_ai_review,
    invoke_with_retry,
    merge_verdicts,
    runs_overlap,
    spec_validation_failed,
)

QUALITY_GATE_AGENTS = (
    "security",
    "qa",
    "analyst",
    "architect",
    "devops",
    "roadmap",
    "reliability",
    "observability",
    "agent-safety",
    "decision-rigor",
)

QUALITY_GATE_AGENT_DISPLAY_NAMES = {
    "security": "Security",
    "qa": "QA",
    "analyst": "Analyst",
    "architect": "Architect",
    "devops": "DevOps",
    "roadmap": "Roadmap",
    "reliability": "Reliability",
    "observability": "Observability",
    "agent-safety": "Agent Safety",
    "decision-rigor": "Decision Rigor",
}


def agent_env_name(agent: str) -> str:
    """Return the environment variable prefix for an agent name."""
    return agent.upper().replace("-", "_")


def agent_arg_name(agent: str) -> str:
    """Return the argparse destination prefix for an agent name."""
    return agent.replace("-", "_")



__all__ = [
    "agent_env_name",
    "agent_arg_name",
    "QUALITY_GATE_AGENT_DISPLAY_NAMES",
    "QUALITY_GATE_AGENTS",
    "FAIL_VERDICTS",
    "SAFE_NAME_PATTERN",
    "VALID_RECOMMENDATIONS",
    "get_feature_review_assignees",
    "get_feature_review_labels",
    "get_feature_review_recommendation",
    "assert_environment_variables",
    "convert_to_json_escaped",
    "extract_verdict",
    "format_collapsible_section",
    "format_markdown_table_row",
    "format_verdict_alert",
    "get_concurrency_group_from_run",
    "get_failure_category",
    "get_labels",
    "get_labels_from_ai_output",
    "get_milestone",
    "get_milestone_from_ai_output",
    "get_pr_changed_files",
    "get_verdict",
    "get_verdict_alert_type",
    "get_verdict_emoji",
    "get_verdict_exit_code",
    "get_workflow_runs_by_pr",
    "initialize_ai_review",
    "invoke_with_retry",
    "merge_verdicts",
    "runs_overlap",
    "spec_validation_failed",
    "write_github_output",
    "write_log",
    "write_log_error",
    "write_output",
    "write_step_summary",
]
