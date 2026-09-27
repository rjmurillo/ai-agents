"""Ratchet ceilings for path-local effective context (issue #4880).

`uv run python -m scripts.validation.effective_context --write-ceilings`
re-measures CEILINGS_BYTES and PATH_LOCAL_DIRECTORY_CEILINGS and rewrites
this module. Review that diff like any code change. FROZEN_TARGETS,
HARNESSES, and CEILING_LABEL come from the spec and are carried over.
effective_context.py imports these names, so a test that monkeypatches
them there reaches the functions that read them.
"""

from __future__ import annotations

# Frozen targets from SPEC-4880-path-local-effective-context.md, "Frozen
# targets" table. --write-ceilings never edits this tuple: adding or
# removing a frozen target is a spec decision, not a measurement.
FROZEN_TARGETS: tuple[str, ...] = (
    ".github/workflows/pr-validation.yml",
    "scripts/validation/pre_pr.py",
    "build/scripts/build_all.py",
    "templates/agents/analyst.shared.md",
    "src/claude/agents/analyst.md",
)

HARNESSES: tuple[str, ...] = ("claude", "copilot")

CEILING_LABEL: str = (
    "These are local, non-regression ceilings measured at the accepted "
    "state on the commit where they were set. No vendor (Anthropic, "
    "GitHub) publishes a size limit for CLAUDE.md or AGENTS.md; no "
    "vendor limit is implied by any ceiling value."
)

# Re-measured by --write-ceilings for every frozen target above, both
# harnesses. Issue #4880 AC7: PATH_LOCAL_DIRECTORY_CEILINGS below covers
# every OTHER git-tracked directory with a nested CLAUDE.md/AGENTS.md, so
# growth outside the five frozen targets is caught too. See
# CEILING_LABEL above: local, measured, no vendor limit implied.
CEILINGS_BYTES: dict[tuple[str, str], int] = {
    (".github/workflows/pr-validation.yml", "claude"): 5190,
    (".github/workflows/pr-validation.yml", "copilot"): 5190,
    ("build/scripts/build_all.py", "claude"): 5807,
    ("build/scripts/build_all.py", "copilot"): 5807,
    ("scripts/validation/pre_pr.py", "claude"): 4141,
    ("scripts/validation/pre_pr.py", "copilot"): 4141,
    ("src/claude/agents/analyst.md", "claude"): 3183,
    ("src/claude/agents/analyst.md", "copilot"): 6376,
    ("templates/agents/analyst.shared.md", "claude"): 5923,
    ("templates/agents/analyst.shared.md", "copilot"): 5923,
}

PATH_LOCAL_DIRECTORY_CEILINGS: dict[tuple[str, str], int] = {
    (".agents", "claude"): 3482,  # agents-write-target: historical -- dict key, not a path join
    (".agents", "copilot"): 3482,  # agents-write-target: historical -- dict key, not a path join
    (".agents/archive/planning/v0.3.1", "claude"): 3651,
    (".agents/archive/planning/v0.3.1", "copilot"): 3651,
    (".claude", "claude"): 0,
    (".claude", "copilot"): 4282,
    (".claude-mem/memories", "claude"): 0,
    (".claude-mem/memories", "copilot"): 1889,
    (".claude-mem/scripts", "claude"): 170,
    (".claude-mem/scripts", "copilot"): 170,
    (".claude-plugin", "claude"): 170,
    (".claude-plugin", "copilot"): 170,
    (".claude/hooks", "claude"): 5988,
    (".claude/hooks", "copilot"): 10270,
    (".claude/hooks/PostToolUse", "claude"): 6158,
    (".claude/hooks/PostToolUse", "copilot"): 10440,
    (".claude/hooks/PreCompact", "claude"): 7087,
    (".claude/hooks/PreCompact", "copilot"): 11369,
    (".claude/hooks/PreToolUse", "claude"): 6158,
    (".claude/hooks/PreToolUse", "copilot"): 10440,
    (".claude/hooks/SessionStart", "claude"): 6158,
    (".claude/hooks/SessionStart", "copilot"): 10440,
    (".claude/lib/github_core", "claude"): 170,
    (".claude/lib/github_core", "copilot"): 4452,
    (".claude/lib/hook_utilities", "claude"): 170,
    (".claude/lib/hook_utilities", "copilot"): 4452,
    (".claude/skills", "claude"): 4145,
    (".claude/skills", "copilot"): 8427,
    (".claude/skills/adr-review", "claude"): 4315,
    (".claude/skills/adr-review", "copilot"): 8597,
    (".claude/skills/adr-review/scripts", "claude"): 4485,
    (".claude/skills/adr-review/scripts", "copilot"): 8767,
    (".claude/skills/chaos-experiment/scripts", "claude"): 4315,
    (".claude/skills/chaos-experiment/scripts", "copilot"): 8597,
    (".claude/skills/codeql-scan/scripts", "claude"): 4315,
    (".claude/skills/codeql-scan/scripts", "copilot"): 8597,
    (".claude/skills/github", "claude"): 4315,
    (".claude/skills/github", "copilot"): 8597,
    (".claude/skills/github/scripts/issue", "claude"): 4485,
    (".claude/skills/github/scripts/issue", "copilot"): 8767,
    (".claude/skills/github/scripts/milestone", "claude"): 4485,
    (".claude/skills/github/scripts/milestone", "copilot"): 8767,
    (".claude/skills/github/scripts/pr", "claude"): 4485,
    (".claude/skills/github/scripts/pr", "copilot"): 8767,
    (".claude/skills/github/scripts/reactions", "claude"): 4485,
    (".claude/skills/github/scripts/reactions", "copilot"): 8767,
    (".claude/skills/memory", "claude"): 4315,
    (".claude/skills/memory", "copilot"): 8597,
    (".claude/skills/merge-resolver/scripts", "claude"): 4315,
    (".claude/skills/merge-resolver/scripts", "copilot"): 8597,
    (".codeql/scripts", "claude"): 169,
    (".codeql/scripts", "copilot"): 169,
    (".github", "claude"): 5190,
    (".github", "copilot"): 5190,
    (".project-toolkit/analysis", "claude"): 169,
    (".project-toolkit/analysis", "copilot"): 169,
    (".project-toolkit/memory/episodes", "claude"): 169,
    (".project-toolkit/memory/episodes", "copilot"): 169,
    (".serena", "claude"): 170,
    (".serena", "copilot"): 170,
    ("build", "claude"): 5807,
    ("build", "copilot"): 5807,
    ("docs", "claude"): 170,
    ("docs", "copilot"): 170,
    ("scripts", "claude"): 4141,
    ("scripts", "copilot"): 4141,
    ("scripts/github_core", "claude"): 4311,
    ("scripts/github_core", "copilot"): 4311,
    ("scripts/hook_utilities", "claude"): 4311,
    ("scripts/hook_utilities", "copilot"): 4311,
    ("src", "claude"): 3183,
    ("src", "copilot"): 3183,
    ("src/claude", "claude"): 3183,
    ("src/claude", "copilot"): 6376,
    ("src/claude/skills/adr-review", "claude"): 3353,
    ("src/claude/skills/adr-review", "copilot"): 6546,
    ("src/claude/skills/adr-review/scripts", "claude"): 3523,
    ("src/claude/skills/adr-review/scripts", "copilot"): 6716,
    ("src/claude/skills/chaos-experiment/scripts", "claude"): 3353,
    ("src/claude/skills/chaos-experiment/scripts", "copilot"): 6546,
    ("src/claude/skills/codeql-scan/scripts", "claude"): 3353,
    ("src/claude/skills/codeql-scan/scripts", "copilot"): 6546,
    ("src/claude/skills/github", "claude"): 3353,
    ("src/claude/skills/github", "copilot"): 6546,
    ("src/claude/skills/github/scripts/issue", "claude"): 3523,
    ("src/claude/skills/github/scripts/issue", "copilot"): 6716,
    ("src/claude/skills/github/scripts/milestone", "claude"): 3523,
    ("src/claude/skills/github/scripts/milestone", "copilot"): 6716,
    ("src/claude/skills/github/scripts/pr", "claude"): 3523,
    ("src/claude/skills/github/scripts/pr", "copilot"): 6716,
    ("src/claude/skills/github/scripts/reactions", "claude"): 3523,
    ("src/claude/skills/github/scripts/reactions", "copilot"): 6716,
    ("src/claude/skills/memory", "claude"): 3353,
    ("src/claude/skills/memory", "copilot"): 6546,
    ("src/claude/skills/merge-resolver/scripts", "claude"): 3353,
    ("src/claude/skills/merge-resolver/scripts", "copilot"): 6546,
    ("src/copilot-cli/lib/github_core", "claude"): 3353,
    ("src/copilot-cli/lib/github_core", "copilot"): 3353,
    ("src/copilot-cli/lib/hook_utilities", "claude"): 3353,
    ("src/copilot-cli/lib/hook_utilities", "copilot"): 3353,
    ("src/copilot-cli/skills/adr-review", "claude"): 3353,
    ("src/copilot-cli/skills/adr-review", "copilot"): 3353,
    ("src/copilot-cli/skills/adr-review/scripts", "claude"): 3523,
    ("src/copilot-cli/skills/adr-review/scripts", "copilot"): 3523,
    ("src/copilot-cli/skills/chaos-experiment/scripts", "claude"): 3353,
    ("src/copilot-cli/skills/chaos-experiment/scripts", "copilot"): 3353,
    ("src/copilot-cli/skills/codeql-scan/scripts", "claude"): 3353,
    ("src/copilot-cli/skills/codeql-scan/scripts", "copilot"): 3353,
    ("src/copilot-cli/skills/github", "claude"): 3353,
    ("src/copilot-cli/skills/github", "copilot"): 3353,
    ("src/copilot-cli/skills/github/scripts/issue", "claude"): 3523,
    ("src/copilot-cli/skills/github/scripts/issue", "copilot"): 3523,
    ("src/copilot-cli/skills/github/scripts/milestone", "claude"): 3523,
    ("src/copilot-cli/skills/github/scripts/milestone", "copilot"): 3523,
    ("src/copilot-cli/skills/github/scripts/pr", "claude"): 3523,
    ("src/copilot-cli/skills/github/scripts/pr", "copilot"): 3523,
    ("src/copilot-cli/skills/github/scripts/reactions", "claude"): 3523,
    ("src/copilot-cli/skills/github/scripts/reactions", "copilot"): 3523,
    ("src/copilot-cli/skills/memory", "claude"): 3353,
    ("src/copilot-cli/skills/memory", "copilot"): 3353,
    ("templates", "claude"): 5923,
    ("templates", "copilot"): 5923,
    ("tests", "claude"): 5459,
    ("tests", "copilot"): 5459,
}
