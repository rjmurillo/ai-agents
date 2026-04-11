# Skill Sidecar Learnings: Knowledge Integration

**Last Updated**: 2026-04-11
**Sessions Analyzed**: 1

## Constraints (HIGH confidence)

- Use `references/` not `resources/` for skill knowledge files. SkillForge generates `references/`. SKILL CLAUDE.md says "Move reference documentation to references/". The planner skill's `resources/` is the only exception. (Session 1, 2026-04-11)
- `references/` files are demand-loaded, not auto-loaded. SKILL.md must contain explicit `See references/X.md` pointers at relevant process steps. Agents read files when skill instructions direct them to. No token budget explosion from passive loading. (Session 1, 2026-04-11)
- `architect` and `implementer` are agents in `src/claude/`, not skills in `.claude/skills/`. They lack SKILL.md and references/ directories. Do not target them for skill-level resource injection. (Session 1, 2026-04-11)

## Preferences (MED confidence)

- When reviewing plans with /autoplan, proof-first beats bulk execution. Both CEO voices (Codex and Claude subagent) independently converged on this for knowledge integration. Prove value on 5 skills before scaling to 283 files. (Session 1, 2026-04-11)
- Resource files need YAML frontmatter with `source`, `created`, and `review-by` fields for staleness tracking. DX review consensus 5/5 on this. (Session 1, 2026-04-11)

## Edge Cases (MED confidence)

- git stash pop can revert linter-applied changes. After stash pop, always re-read files before editing. The cva-analysis SKILL.md edit failed because the linter had modified the file during stash. (Session 1, 2026-04-11)

## Notes for Review (LOW confidence)

- Codex CEO review produced higher-quality strategic analysis than Claude subagent for this repo. Codex found P0 (agents vs skills target confusion) that subagent missed. May indicate Codex is better at repo-specific structural analysis. (Session 1, 2026-04-11)
