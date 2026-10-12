"""Known shipped-YAML offenses that check_plugin_root_interpreter.py allows.

Each entry is keyed by (path relative to its plugin root, rule, script tail),
so one entry covers the three mirrors and survives line moves. Rules: "form",
"dependency", "bare-path". For an entry that no longer matches anything, the
checker prints a non-failing ``note:`` line on stdout, so a fixed offense shows
up as an entry to delete without failing CI.
"""

from __future__ import annotations

_PR_REVIEW_CONFIG = "skills/pr-review/pr-review-config.yaml"
_CLAUDE_CODE_MAP = (
    "scripts.claude_code predates plugin-self-containment MUST 2; the copilot map "
    "already uses the plugin-root form. Migrating it is an owner decision (Refs #6195)."
)
_CRITERIA_BEFORE_GATE_FIX = (
    "completion_criteria used bare paths because run_completion_gate.py did not "
    "expand the plugin-root form at dispatch. The gate fix moves them to the "
    "plugin-root form; this entry then stops matching (Refs #6195)."
)
_GATE_NEEDS_PYYAML = (
    "transport_preflight.verify_trust runs run_completion_gate.py, which imports "
    "yaml, so bare python3 cannot run it (Refs #6195)."
)
_GUARDED_MARKDOWN_IT = (
    "check_review_thread_resolution_shas.py imports markdown-it-py inside "
    "try/except ImportError and scans the raw body without it. Whether a guarded "
    "import meets MUST 4 is an owner decision (Refs #6195)."
)
_PR_SCRIPTS = "skills/github/scripts/pr/"


def _allow(rule: str, script: str, reason: str) -> tuple[tuple[str, str, str], str]:
    return (_PR_REVIEW_CONFIG, rule, script), reason


YAML_ALLOWANCES: dict[tuple[str, str, str], str] = dict(
    [
        *(
            _allow("bare-path", f"{_PR_SCRIPTS}{name}.py", _CLAUDE_CODE_MAP)
            for name in (
                "get_pr_context",
                "test_pr_merged",
                "get_pr_review_threads",
                "get_unresolved_review_threads",
                "wait_for_unresolved_zero",
                "get_unaddressed_comments",
                "get_pr_checks",
                "add_pr_review_thread_reply",
                "resolve_pr_review_thread",
            )
        ),
        _allow(
            "bare-path", "skills/pr-comment-responder/scripts/cluster_threads.py", _CLAUDE_CODE_MAP
        ),
        *(
            _allow("bare-path", f"{_PR_SCRIPTS}{name}.py", _CRITERIA_BEFORE_GATE_FIX)
            for name in (
                "check_suppressed_review_findings",
                "check_review_thread_resolution_shas",
                "test_pr_merge_ready",
            )
        ),
        _allow("form", f"{_PR_SCRIPTS}run_completion_gate.py", _GATE_NEEDS_PYYAML),
        _allow(
            "dependency",
            f"{_PR_SCRIPTS}check_review_thread_resolution_shas.py",
            _GUARDED_MARKDOWN_IT,
        ),
    ]
)
