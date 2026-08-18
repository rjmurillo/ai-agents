# Issue 5074: Merge-Resolver Rename Rule

**Statement**: Add/add conflicts on append-only evidence artifacts (`.agents/sessions/*`, `.agents/qa/*`, `.agents/retrospective/*`) resolve by keeping both files and renaming the head branch version with a distinguishing suffix (keep the session number, append an issue or topic slug), never by content-merging. Encoded in every merge-resolver guidance surface per the PR #4856 retrospective.

**Evidence**: `.agents/retrospective/2026-08-10-pr-4856-session-log-collision.md`; issue #4751 (allocation-time prevention, open P1).

## Edit surface map (measured this session)

- `templates/agents/merge-resolver.shared.md` is canonical, but `build/generate_agents.py` writes ONLY `src/copilot-cli/agents/` and `src/vs-code-agents/`. The copies at `src/claude/merge-resolver.md`, `.claude/agents/merge-resolver.md`, and `.github/agents/merge-resolver.agent.md` are hand-maintained; a shared-behavior change is 1 template + 3 hand edits + 2 regenerated outputs.
- A pre-commit hook auto-stages regenerated agent outputs and `docs/agent-catalog.md` into the same commit as the template edit.
- The skill guidance lives at `.claude/skills/merge-resolver/SKILL.md` and `references/strategies.md`; no `src/copilot-cli/skills/merge-resolver/` mirror exists.

## Drift baseline finding

`build/scripts/detect_agent_drift.py` `KNOWN_BASELINE_DRIFT` records a measured similarity floor for merge-resolver (was 20.9). Adding identical prose to both the verbose (.claude) and terse (template-derived) shapes SHIFTED Jaccard to 20.7, below the floor, so the floor had to be re-measured and lowered in the same change. Expect this any time both shapes gain shared wording.

## Known gap (follow-up)

`resolve_pr_conflicts.py` `AUTO_RESOLVABLE_PATTERNS` matches `.agents/sessions/*` and resolves by accept-theirs, which on an add/add silently discards the branch's own record. The rename half is manual; documented as a caveat in SKILL.md. The script does not implement the rename.
