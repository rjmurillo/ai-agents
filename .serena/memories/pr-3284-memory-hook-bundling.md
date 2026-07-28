# Episode-extraction hook auto-bundles memory into every commit

## Finding (session 3257, PR #3284, 2026-07-21)

The pre-commit hook `.githooks/pre-commit:1406-1441` runs
`.claude/skills/memory/scripts/extract_session_episode.py` on every commit. It
extracts the current session's episode to `.agents/memory/episodes/episode-<session>.json`,
then stages it. Until ADR-088 it also wrote and staged
`.agents/memory/causality/causal-graph.json`; that graph and its writer job are
deleted, so the hook now stages one file per commit, not two.

## Consequence

Any commit that touches skills/commands lands memory files alongside them. This
structurally violates `.claude/rules/claude-agents.md` MUST NOT #2 ("MUST NOT
bundle skill code changes with memory changes in the same PR"). Bot reviewers
(copilot-pull-request-reviewer) flag it on PRs. On PR #3284 the flagged files
(`episode-2026-07-20-session-3256-*.json`, `causal-graph.json`) were hook
output, not manual authoring. The graph half of that output no longer exists.

## Why it matters

You cannot unbundle memory from a skill PR without `--no-verify` (forbidden by
universal.md) or a post-hoc unstage. Removing the memory files then committing
just re-adds the current session's episode. The real fix is at the hook layer,
tracked under the hook-ROI retirement epic #3197. Reply-and-resolve the bot
thread; do not fight the hook in a feature PR.

## Also: session-end validation is forward-looking

`scripts/validate_session_json.py` requires all sessionEnd MUSTs Complete=true
with non-empty evidence BEFORE the final commit (changesCommitted is claimed,
not verified against git). Contradiction detector bans these words in evidence:
`not available|skipped|N/A|deferred|will validate|will run|TODO|pending|TBD`.
Mirror the pattern in the prior session log (3256) that already validates.

Related: [[check-parallel-work-before-implementing]]

## Related

- [pr-comment-index](pr-comment-index.md)
- [pr-review-pr1873-observations](pr-review-pr1873-observations.md)
