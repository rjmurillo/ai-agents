# Skill Sidecar Learnings: Knowledge Integration

**Last Updated**: 2026-04-11
**Sessions Analyzed**: 1

## Constraints (HIGH confidence)

- Use `references/` not `resources/` for skill knowledge files. SkillForge generates `references/`. SKILL CLAUDE.md says "Move reference documentation to references/". The planner skill's `resources/` is the only exception. (Session 1, 2026-04-11)
- `references/` files are demand-loaded, not auto-loaded. SKILL.md must contain explicit `See references/X.md` pointers at relevant process steps. Agents read files when skill instructions direct them to. No token budget explosion from passive loading. (Session 1, 2026-04-11)
- `architect` and `implementer` are agents in `src/claude/`, not skills in `.claude/skills/`. They lack SKILL.md and references/ directories. Do not target them for skill-level resource injection. (Session 1, 2026-04-11)
- References add value inversely proportional to pre-training coverage. Only create references for niche or organization-specific knowledge. Well-known topics (OWASP, SOLID, chaos engineering, observability) get marginal benefit from references. API eval across 12 skills confirmed: cva-analysis +1.50 (niche), threat-modeling +0.00 (well-known). (Session 1, 2026-04-11)
- Over-loading skill context with references can cause regression. The analyze skill regressed -0.56 with 6 reference files. Keep references lean, max 3-4 per skill. (Session 1, 2026-04-11)

## Preferences (MED confidence)

- When reviewing plans with /autoplan, proof-first beats bulk execution. Both CEO voices (Codex and Claude subagent) independently converged on this for knowledge integration. Prove value on 5 skills before scaling to 283 files. (Session 1, 2026-04-11)
- Resource files need YAML frontmatter with `source`, `created`, and `review-by` fields for staleness tracking. DX review consensus 5/5 on this. (Session 1, 2026-04-11)
- Organization-specific knowledge (engineering complexity tiers, explainers/intents process) produces the highest ROI references. Pre-training cannot cover these. Planner skill gained +0.89 from org-specific references vs +0.05 for well-known topics. (Session 1, 2026-04-11)
- Run evals per-skill in foreground for reliability. Multi-skill runs hit timeouts on long eval batches. Background bash commands with piped grep produce empty output. (Session 1, 2026-04-11)

## Edge Cases (MED confidence)

- git stash pop can revert linter-applied changes. After stash pop, always re-read files before editing. The cva-analysis SKILL.md edit failed because the linter had modified the file during stash. (Session 1, 2026-04-11)
- Background bash commands with piped grep produce empty output due to shell buffering. Run eval commands in foreground or redirect to file without grep filtering. (Session 1, 2026-04-11)
- The eval script's SKILL_PATHS dict was hardcoded to 5 skills. Dynamic resolution via SKILLS_DIR / skill_name is required for --prompts-file with custom skills. (Session 1, 2026-04-11)

## Notes for Review (LOW confidence)

- Codex CEO review produced higher-quality strategic analysis than Claude subagent for this repo. Codex found P0 (agents vs skills target confusion) that subagent missed. May indicate Codex is better at repo-specific structural analysis. (Session 1, 2026-04-11)
- Self-scoring (model scores its own output) inflates baselines. API eval baselines (3.5-4.9) are higher than subagent eval baselines (2.2-3.8). The delta is what matters, not absolute scores. (Session 1, 2026-04-11)
- The analyze skill regression (-0.56) may be a fluke from model nondeterminism with n=6. Needs verification with a larger sample before removing references. (Session 1, 2026-04-11)
