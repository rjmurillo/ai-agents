"""Ratchet ceilings for path-local effective context (issue #4880).

Split out of ``effective_context.py``: this module's own ceiling data (ten
frozen-target entries plus 124 per-directory, per-harness entries) pushed
that module to 624 lines, past the taste-lints 500-line file-size ERROR
threshold. Pure data plus the one shared label string; every check that
reads these constants (``check_ceilings``, ``check_directory_ceiling``,
``_run_ci``) stays in ``effective_context.py``, so a test that monkeypatches
``effective_context.CEILINGS_BYTES`` or
``effective_context.PATH_LOCAL_DIRECTORY_CEILINGS`` still reaches the same
name those functions read: both are imported there under their own names,
not re-derived, and the functions that consult them are defined in that
same module, so the patched module-global is exactly what their own
``__globals__`` lookup resolves.
"""

from __future__ import annotations

# Frozen targets from SPEC-4880-path-local-effective-context.md, "Frozen
# targets" table. Each exercises a different depth and a different nested
# file combination (workflow under two directories, script under two, agent
# template under three for Claude's src/ split).
FROZEN_TARGETS: tuple[str, ...] = (
    ".github/workflows/pr-validation.yml",
    "scripts/validation/pre_pr.py",
    "build/scripts/build_all.py",
    "templates/agents/analyst.shared.md",
    "src/claude/agents/analyst.md",
)

HARNESSES: tuple[str, ...] = ("claude", "copilot")

# These are LOCAL, NON-REGRESSION ceilings measured at the accepted state on
# the commit where SPEC-4880 seeded them (this module's own first commit,
# `git log -1 --format=%H -- scripts/validation/effective_context.py`).
# Anthropic and GitHub publish no 25 KB, 200-line, or 50-line hard limit for
# CLAUDE.md or AGENTS.md; no vendor size limit is implied by any value below.
# Lower a ceiling when the nested corpus shrinks; never raise one without
# recording why in the same change. This label covers both CEILINGS_BYTES
# (per frozen target) and PATH_LOCAL_DIRECTORY_CEILINGS below (every other
# instructed directory): both are local, measured, non-vendor ceilings.
CEILING_LABEL: str = (
    "These are local, non-regression ceilings measured at the accepted "
    "state on the commit where they were set. No vendor (Anthropic, "
    "GitHub) publishes a size limit for CLAUDE.md or AGENTS.md; no vendor "
    "limit is implied by any ceiling value."
)

CEILINGS_BYTES: dict[tuple[str, str], int] = {
    (".github/workflows/pr-validation.yml", "claude"): 5_190,
    (".github/workflows/pr-validation.yml", "copilot"): 5_190,
    ("scripts/validation/pre_pr.py", "claude"): 4_141,
    ("scripts/validation/pre_pr.py", "copilot"): 4_141,
    ("build/scripts/build_all.py", "claude"): 5_807,
    ("build/scripts/build_all.py", "copilot"): 5_807,
    ("templates/agents/analyst.shared.md", "claude"): 5_923,
    ("templates/agents/analyst.shared.md", "copilot"): 5_923,
    # Claude loads only `src/AGENTS.md` and `src/CLAUDE.md`: `src/claude/`
    # has no `CLAUDE.md`, so Claude Code's own loading model (imports only
    # follow from a `CLAUDE.md`) never reaches `src/claude/AGENTS.md`.
    # Copilot's directory-chain rule needs no import, reads AGENTS.md/CLAUDE.md
    # directly per directory, and so also counts `src/claude/AGENTS.md`. This
    # asymmetry is why SPEC-4880 picked this target: it exercises the one
    # place the two harnesses' nested layers genuinely diverge.
    ("src/claude/agents/analyst.md", "claude"): 3_183,
    ("src/claude/agents/analyst.md", "copilot"): 6_376,
}

# Issue #4880 AC7: the five frozen targets above cannot catch growth in a
# directory none of them passes through. This maps every git-tracked
# directory `discover_nested_directories` finds (any directory with its own
# nested `CLAUDE.md`/`AGENTS.md`) to its own measured ceiling, per harness,
# rather than one shared ceiling: a shared ceiling could not tell a directory
# that grew a little from one that grew to the shared limit, and it let any
# directory regrow all the way up to the single highest-measured value
# (`.claude/hooks/PreCompact` under Copilot, 11,369 bytes) without tripping.
# Each value below is that directory's own measured path-local bytes at this
# map's most recent update; a directory this repository grows that has no
# entry here fails closed (`check_directory_ceiling` names it and this
# constant), rather than passing silently or inheriting a neighbor's ceiling.
# See CEILING_LABEL above: local, measured, no vendor limit implied.
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
