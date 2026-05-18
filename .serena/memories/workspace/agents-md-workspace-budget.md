# AGENTS.md Workspace Budget Fix (Session 1835, 2026-05-17)

**Context**: `AGENTS.md` drifted over the 3072-byte per-file budget enforced by `tests/test_workspace_limits.py::test_per_file_limit[AGENTS.md]` (MAX_PER_FILE=3072, MAX_TOTAL=6758 for AGENTS.md + CLAUDE.md). The test runs on every PR via the pytest CI workflow (AC-3).

## Root Cause

AGENTS.md reached 3228 B (156 B over cap) as content accumulated without tracking the byte budget. 7 of 21 open PRs were CI-red because of this.

## Fix Applied (PR linked to issue #2034)

- Dropped `## Agents` roster section (330+ B) -- pure reference data, agents defined in `templates/agents/` and `.claude/agents/`; not needed per-turn in injected context
- Lossless rewording: merged duplicate pipe entries, trimmed filler prepositions
- Restored `**Autonomy Guardrail**` label (vs `**Autonomy**`) to match 20+ generated agent files that reference the term by name
- Result: 3228 to 2791 B (281 B headroom)

## Key Learnings

- `caveman-compress` targets **token** reduction (filler/articles), NOT a byte budget. For a file that is already pipe-terse, it saves almost nothing.
- The `## Agents` roster was redundant with `templates/agents/` and `.claude/agents/`; safe to drop from the injected-context file.
- Terminology consistency: AGENTS.md label changes must be checked against 20+ generated agent files that reference those labels by name (`src/claude/*.md`, `src/copilot-cli/`, `src/vs-code-agents/`, `templates/agents/*.shared.md`).

## Files

- `AGENTS.md` -- injected per-turn; 2791 B post-fix
- `tests/test_workspace_limits.py` -- hard cap enforcement
- `scripts/validate_workspace_budget.py` -- second validator (also checks `.claude/CLAUDE.md`)
