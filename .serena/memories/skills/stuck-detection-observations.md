# Skill Observations: stuck-detection

**Last Updated**: 2026-04-27
**Sessions Analyzed**: 1

## Purpose

Captures learnings from the `stuck-detection` skill, added to `.claude/skills/stuck-detection/` in PR #1796.

The skill detects agent conversation loops via Jaccard similarity on topic signatures. When N recent response signatures exceed a similarity threshold, it emits a self-reflection nudge so the orchestrator can break the loop.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Default history path must resolve via `--history` CLI flag, then `STUCK_DETECTION_HISTORY` env var, then `$XDG_STATE_HOME/claude-stuck-detection/history.json`, then `~/.local/state/...`. Never hardcode workspace paths (Session 2026-04-27-session-1754, 2026-04-27)
- Nudge text must contain no personal names or environment-specific branding. Test `TestBuildNudge.test_nudge_no_personal_names` enforces this (Session 2026-04-27-session-1754, 2026-04-27)
- Script is stdlib only. Do not introduce third-party dependencies. The skill must run with the bare Python toolchain that the rest of `.claude/skills/` assumes (Session 2026-04-27-session-1754, 2026-04-27)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Pair the skill with task-completion checks. Lexical Jaccard misses semantic loops where the model rephrases the same content (Session 2026-04-27-session-1754, 2026-04-27)
- Call `check` once per agent turn, not per token. Per-token calls produce noisy signatures and inflate IO (Session 2026-04-27-session-1754, 2026-04-27)
- Call `reset` after a confirmed topic change. Otherwise stale history triggers false positives (Session 2026-04-27-session-1754, 2026-04-27)

## Edge Cases (MED confidence)

These are scenarios to handle:

- Templated text where surface vocabulary dominates the actual theme (e.g., "deployment pipeline failed", "authentication pipeline failed") will collide on shared noise words. Vary surrounding language or raise `DEFAULT_SIMILARITY_THRESHOLD` toward 0.75 (Session 2026-04-27-session-1754, 2026-04-27)
- Responses below `MIN_TEXT_LENGTH` (50 chars) return signature `None` and never participate in stuck detection (Session 2026-04-27-session-1754, 2026-04-27)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

- A second-tier semantic similarity check (embedding-based) could complement the lexical layer for cases where the model paraphrases the same content. Currently out of scope (Session 2026-04-27-session-1754, 2026-04-27)
- The skill could expose a hook-friendly invocation pattern so orchestrators wire it in declaratively rather than calling the CLI per turn (Session 2026-04-27-session-1754, 2026-04-27)

## History

| Date | Session | Change |
|------|---------|--------|
| 2026-04-27 | 1754 | Initial skill added in PR #1796. Ported from Node.js prototype to Python with stdlib only. 32 pytest cases, ruff clean, mypy clean. |
