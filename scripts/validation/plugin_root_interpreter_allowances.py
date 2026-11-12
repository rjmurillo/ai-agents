"""Known shipped-YAML offenses that check_plugin_root_interpreter.py allows.

Each entry is keyed by (path relative to its plugin root, YAML key path, rule,
script tail), so one entry covers the three mirrors and survives line moves,
but a new command under another key is still reported. Rules: "form",
"dependency", "bare-path". For an entry that no longer matches anything, the
checker prints it to stderr and exits 1, so a stale entry cannot hide a later
offense. Delete the entry once the offense is fixed (issue #6506).
"""

from __future__ import annotations

import re

_PR_REVIEW_CONFIG = "skills/pr-review/pr-review-config.yaml"
_GUARDED_MARKDOWN_IT = (
    "check_review_thread_resolution_shas.py imports markdown-it-py inside "
    "try/except ImportError and scans the raw body without it. Whether a guarded "
    "import meets MUST 4 is an owner decision (Refs #6195)."
)
_PR = "skills/github/scripts/pr/"
_CRITERION = "completion_criteria.command"

YAML_ALLOWANCES: dict[tuple[str, str, str, str], str] = {
    (
        _PR_REVIEW_CONFIG,
        _CRITERION,
        "dependency",
        f"{_PR}check_review_thread_resolution_shas.py",
    ): _GUARDED_MARKDOWN_IT,
}

_CLAUDE_HOOK = (
    "Claude Code hook runtime. Claude hooks never render into src/copilot-cli, and "
    "Claude Code exports only its own plugin-root variable (official-hook-contracts.md)."
)
_CLAUDE_HOOK_CHECK = (
    "Validates the Claude hooks.json anchor, which is the Claude variable by contract. "
    "The Copilot shape is checked against its generator."
)
_HARNESS_FACT = (
    "States what Claude Code exports, as harness-reference evidence. It is a fact about "
    "one harness, not a command."
)

# Rule 4 (single-root): files that may name the Claude plugin-root variable
# without the Copilot one. Keyed by full path, else by path with the plugin tree
# stripped (one key then covers every render). Value is
# (number of standalone statements per copy, reason). The checker fails when a
# file holds more, or fewer, than the count, and when a key matches no file.
SINGLE_ROOT_ALLOWANCES: dict[str, tuple[int, str]] = {
    "src/claude/hooks/hooks.json": (1, _CLAUDE_HOOK),
    "hooks/invoke_dispatch_claude.py": (4, _CLAUDE_HOOK),
    "hooks/PreCompact/invoke_compact_checkpoint.py": (1, _CLAUDE_HOOK),
    "hooks/PreToolUse/_bootstrap.py": (8, _CLAUDE_HOOK),
    "hooks/SessionStart/invoke_checkout_freshness_check.py": (1, _CLAUDE_HOOK),
    "hooks/SessionStart/invoke_context_loader.py": (1, _CLAUDE_HOOK),
    "hooks/SessionStart/invoke_plugin_hook_drift_check.py": (1, _CLAUDE_HOOK),
    "templates/hooks/hooks.json": (1, _CLAUDE_HOOK),
    "templates/hooks/invoke_dispatch_claude.py": (4, _CLAUDE_HOOK),
    "templates/hooks/PreCompact/invoke_compact_checkpoint.py": (1, _CLAUDE_HOOK),
    "templates/hooks/PreToolUse/_bootstrap.py": (8, _CLAUDE_HOOK),
    "templates/hooks/SessionStart/invoke_checkout_freshness_check.py": (1, _CLAUDE_HOOK),
    "templates/hooks/SessionStart/invoke_context_loader.py": (1, _CLAUDE_HOOK),
    "templates/hooks/SessionStart/invoke_plugin_hook_drift_check.py": (1, _CLAUDE_HOOK),
    "scripts/validation/validate_hook_anchoring.py": (4, _CLAUDE_HOOK_CHECK),
    "scripts/validation/hook_contracts.py": (1, _CLAUDE_HOOK_CHECK),
    "scripts/validation/checks_plugin.py": (1, _CLAUDE_HOOK_CHECK),
    "build/scripts/generate_hooks_emit.py": (1, "Comment on the Claude hook command rewrite."),
    "scripts/validation/git_hook_policy.py": (
        1,
        "Pre-push pytest env pins one plugin tree for the suite. Not shipped, not a command.",
    ),
    "skills/agent-harness-reference/SKILL.md": (2, _HARNESS_FACT),
    "templates/skills/agent-harness-reference.SKILL.md.tmpl": (2, _HARNESS_FACT),
    "skills/agent-harness-reference/references/probe-evidence.md": (1, _HARNESS_FACT),
    "skills/github/scripts/pr/run_completion_gate.py": (
        2,
        "A table that still recognizes the legacy single-root form in installed configs, "
        "and a comment on the root-trust check. Both stay put: any edit to this file "
        "changes the gate's frozen dispatch closure, which CI compares with the base.",
    ),
}

# Ratchet for the legacy plugin-root form in authored files (ADR-121 rollout step 3).
# Keyed by authored group (`authored_group` in plugin_root_interpreter_ratchet.py).
# Value is (invocations, assignments, reason): invocations are `python3 "${...}/skills/..."`
# commands, assignments are lines such as `SCRIPTS_DIR=${...}`. The checker fails when a
# group holds more, or fewer, than the count. Lower a count in the pull request that
# migrates the sites; never raise one. A group with no entry has a baseline of (0, 0).
LEGACY_SITE_BASELINE: dict[str, tuple[int, int, str]] = {
    "templates/agents": (0, 0, "Migrated in rollout step 4 (agents first)."),
    "templates/skills": (15, 7, "Migrates in rollout step 4, in batches the budget allows."),
    "src/claude": (64, 50, "Skill support files. Rollout step 5 decides them by class."),
    "src/claude yaml": (
        17,
        0,
        "Class G: the completion gate dispatches these commands and runs no shell (ADR-121 "
        "decision 1). They keep the legacy form.",
    ),
}

_KEY_RE = re.compile(r"([A-Za-z0-9_.-]+):(?:\s|$)")
# A block scalar header closes a key line (or a `- ` item): `|`, `>`, with an
# optional chomping or indentation indicator and an optional trailing comment.
_BLOCK_HEADER_RE = re.compile(r"[|>](?:[+-]?\d?|\d[+-])[ \t]*(?:#.*)?$")


def _opens_block_scalar(content: str) -> bool:
    """Return whether ``content`` (dash already stripped) ends in a block scalar header."""
    match = _KEY_RE.match(content)
    value = content[match.end() :].strip() if match else content.strip()
    return bool(_BLOCK_HEADER_RE.fullmatch(value))


def yaml_key_paths(text: str) -> list[str]:
    """Return the dotted block-mapping key path that owns each line of ``text``.

    Stdlib only, for the block-style YAML this repository ships: a key's
    parents are the keys at smaller indentation above it, and a ``- `` list
    item adds no path segment. A comment or blank line inherits the open path.
    The body of a block scalar (``|`` or ``>``) is text, not keys: its lines
    inherit the owning key's path even when one reads like ``key:`` (issue #6506).
    """
    stack: list[tuple[int, str]] = []
    paths: list[str] = []
    block_floor: int | None = None  # body lines must be indented deeper than this
    for raw in text.splitlines():
        stripped = raw.lstrip(" ")
        if block_floor is not None:
            if not stripped or len(raw) - len(stripped) > block_floor:
                paths.append(".".join(key for _, key in stack))
                continue
            block_floor = None
        content = stripped
        floor = len(raw) - len(stripped)
        if content.startswith("- "):
            content = content[2:].lstrip(" ")
        if content and not content.startswith("#"):
            indent = len(raw) - len(content)
            while stack and stack[-1][0] >= indent:
                stack.pop()
            match = _KEY_RE.match(content)
            if match:
                stack.append((indent, match.group(1)))
                floor = indent
            if _opens_block_scalar(content):
                block_floor = floor
        paths.append(".".join(key for _, key in stack))
    return paths
