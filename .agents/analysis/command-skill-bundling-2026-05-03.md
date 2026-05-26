# Command and Skill Bundling Opportunities

Date: 2026-05-03
Scope: `.claude/commands/`, `.claude/skills/`, `.claude/agents/`
Goal: Identify where commands underuse, miss, or duplicate skills and agents, and where bundling improves outcomes.

## Current Wiring (observed)

| Command | Skills invoked | Agents invoked |
|---|---|---|
| /spec | requirements-interview, cva-analysis (cond.), decision-critic | analyst, spec-generator, critic |
| /plan | execution-plans | milestone-planner, task-decomposer, analyst, critic |
| /build | code-qualities-assessment | analyst, implementer |
| /test | (security-detection in Gate 3 only) | analyst, qa, critic, security, devops, architect |
| /review | golden-principles, taste-lints | architect, security, qa, analyst |
| /ship | pipeline-validator, security-scan, golden-principles, taste-lints | devops |
| /pr-review | pr-comment-responder | per-PR Task agents |
| /research | (writes to memory) | (uses research-and-incorporate skill) |
| /context-gather | forgetful, serena, context7, deepwiki | (none) |
| /push-pr, /validate-pr-description | (none) | (none) |

## Gaps and Bundling Opportunities

### 1. Lifecycle commands skip session protocol (ADR-007)
- `session-init` not bundled into `/spec` start; `session-end` not bundled into `/ship` close.
- Fix: `/spec` opens with `Skill(skill="session-init")`. `/ship` closes with `Skill(skill="session-end")` after PR creation.
- Outcome: removes the "no session log for today" warning we hit on every run.

### 2. /plan duplicates pre-mortem and decision-critic logic inline
- Step 6 prompts `analyst` to "run a pre-mortem" instead of `Skill(skill="pre-mortem")`.
- Step 7 prompts `critic` instead of `Skill(skill="decision-critic")` (already used in /spec).
- Fix: replace prompts with skill invocations to inherit structured templates and avoid drift between /spec and /plan critique quality.

### 3. /build is preflight-blind
- Says "understand the existing code" but invokes no retrieval skill.
- Missing: `context-gather` (Forgetful + Context7 + Serena), `steering-matcher` (path-based guidance), `chestertons-fence` (when modifying old/low-coverage code per `.claude/rules/working-with-legacy-code.md`).
- Fix: bundle a preflight block: `Skill(context-gather)` -> `Skill(steering-matcher)` -> conditional `Skill(chestertons-fence)` if file age >6mo or coverage low.
- Outcome: eliminates the recurring "started coding before reading rules" failure.

### 4. /test gates underuse dedicated skills
- Gate 3 (Security) uses `security` agent but not `threat-modeling` or `security-scan` skills (`.claude/rules/security.md` SHOULD).
- Gate 4 (DevOps) duplicates pipeline checks `/ship` already runs via `pipeline-validator`.
- Gate 6 (Observability) prompts `architect` for SRE review but skips `slo-designer` and `observability` skills.
- Fix: bundle `threat-modeling` (tier 3+), `security-scan`, `pipeline-validator`, `slo-designer`, `observability` into matching gates.

### 5. /review missing axes
- No documentation axis: `doc-accuracy` skill exists and consolidates incoherence/doc-coverage/doc-sync.
- No legacy-code guard: `chestertons-fence` should fire on any diff into files with low coverage.
- Fix: add Axis 6 (Documentation) -> `Skill(doc-accuracy)`; conditionally invoke `chestertons-fence` in Axis 1.

### 6. /ship one-way: no learning capture
- No `reflect` skill on success. Each ship loses the pattern.
- Fix: append `Skill(skill="reflect")` after PR creation; HIGH-confidence learnings persist to Serena.

### 7. /pr-review missing conflict path
- Does not auto-invoke `merge-resolver` when conflicts are detected; the operator runs it manually.
- Fix: in Step 2 status check, branch to `Skill(merge-resolver)` if `mergeable_state != clean`.

### 8. /research and /context-gather are siblings, not composed
- Both pull external + memory. /research persists; /context-gather doesn't.
- Fix: /research's first step calls /context-gather to dedupe known knowledge before web fetch (saves the 3000-5000 word write when the answer already exists in memory).

### 9. Cross-command context handoff is missing
- Each command spawns fresh agents that re-read the same files. Forgetful/Serena stores are the natural carrier.
- Fix: /spec persists PRD summary to Serena under `spec/<slug>`; /plan and /build read it instead of reparsing args.

## Recommended Bundles (highest impact first)

1. Add `session-init` to `/spec`, `session-end` + `reflect` to `/ship`.
2. Replace inline pre-mortem/critic prompts in `/plan` with the `pre-mortem` and `decision-critic` skills.
3. Add a preflight block to `/build`: `context-gather` -> `steering-matcher` -> conditional `chestertons-fence`.
4. Wire `/test` gates to `threat-modeling`, `security-scan`, `pipeline-validator`, `slo-designer`, `observability`.
5. Add Axis 6 (`doc-accuracy`) to `/review`; conditional `chestertons-fence` in Axis 1.
6. Auto-invoke `merge-resolver` in `/pr-review` on conflict state.
7. Compose `/context-gather` as the first step of `/research`.

## Notes

- The `pr-quality:*` package and `forgetful:memory-*` slash skills already follow the bundle pattern; commands above should adopt the same convention rather than re-prompt agents.
- `quality-grades` and `analyze` skills are good candidates for an explicit cadence command (e.g., `/audit`) rather than a bundle inside the build/ship loop.
