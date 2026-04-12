# SPEC: Agent Prompt Optimization and Wiki Enrichment

## Problem Statement

The `.claude/agents/` directory has 23 agent definitions totaling 441KB. The largest agents (orchestrator 69KB, implementer 45KB, retrospective 43KB) score worst on quality assessments. The smallest agents (high-level-advisor 8KB, adr-generator 7KB) score best. Agent prompts need slimming and targeted enrichment, not consolidation.

## Goals

1. Slim all 23 agent prompts toward 8-12KB target (hard cap 16KB)
2. Enrich the 7 lowest-scoring agents with compressed, sanitized wiki knowledge inline
3. Measure improvement via baseline assessment framework

## Acceptance Criteria

### Prompt Optimization (this PR's scope)

- AC-1: All 23 agents retained (no merges, no deletions)
- AC-2: **The 11 low-scoring agents targeted by this PR** (explainer, implementer, analyst, context-retrieval, orchestrator, spec-generator, critic, skillbook, roadmap, milestone-planner, issue-feature-review) are slimmed to the 5-8KB range, all under the 16KB hard cap.
- AC-3: Untouched agents that still exceed 16KB (security 31KB, retrospective 43KB, qa 22KB, architect 22KB, devops 15KB, memory 14KB) are explicitly flagged as Phase 3 candidates in `.serena/memories/agent-prompt-optimization-observations.md` but are **out of scope** for this PR. They score above threshold (4.0+) in the current eval and are not blocking.
- AC-4: For the 11 slim targets, duplicated boilerplate (style guide, activation profiles, memory protocols) is removed
- AC-5: For the 11 slim targets, stale cross-agent references are fixed (e.g., implementer referencing nonexistent debug agent)
- AC-6: Each slimmed agent's core mission is preserved. No capability loss from slimming (verified via eval).

### Mirror Synchronization

- AC-7: Changes to `.claude/agents/*.md` are propagated to `src/claude/*.md`, `templates/agents/*.shared.md`, `src/copilot-cli/*.agent.md`, and `src/vs-code-agents/*.agent.md` for the 11 slim targets. Helper script: `build/sync_slim_agents.py`. Verified by `build/scripts/detect_agent_drift.py` (all 11 targets at 100.0% similarity).
- AC-8: `context-retrieval` and `spec-generator` are Claude-only agents; not mirrored to other platforms.

### Eval Framework

- AC-9: New eval framework `.agents/planning/eval-agents.py` scores agents on 4 dimensions (role_adherence, actionability, quality, **appropriateness**) with Cynefin complexity tagging.
- AC-10: Baseline (v1 and v2) and post-review eval results are committed under `.agents/planning/agent-*-results.json`.
- AC-11: Post-optimization eval confirms all 11 slim targets are above 4.0 overall (no regressions).
- AC-12: Average score across all 23 agents improved from 4.24 → 4.57 (+0.33) in the post-review eval.

### Wiki Enrichment (deferred)

- **Deferred to a follow-up PR.** The /autoplan CEO+Eng review explicitly flagged wiki enrichment as risky for a public repo without a sanitization pipeline. This PR's scope is prompt slimming + eval framework only. Wiki enrichment is tracked in observations memory as Phase 3 work.

## Baseline Results (2026-04-11)

| Agent | Model | Role | Action | Quality | Overall |
|-------|-------|------|--------|---------|---------|
| high-level-advisor | opus | 5.00 | 4.50 | 5.00 | 4.83 |
| security | opus | 5.00 | 5.00 | 4.25 | 4.75 |
| adr-generator | unspec | 5.00 | 5.00 | 4.00 | 4.67 |
| architect | opus | 5.00 | 4.50 | 4.50 | 4.67 |
| qa | sonnet | 5.00 | 4.75 | 4.25 | 4.67 |
| skillbook | sonnet | 5.00 | 4.75 | 4.25 | 4.67 |
| task-decomposer | sonnet | 4.50 | 5.00 | 4.00 | 4.50 |
| devops | sonnet | 4.75 | 4.50 | 4.00 | 4.42 |
| independent-thinker | opus | 5.00 | 4.00 | 4.25 | 4.42 |
| memory | sonnet | 4.75 | 4.50 | 4.00 | 4.42 |
| quality-auditor | sonnet | 5.00 | 4.00 | 4.25 | 4.42 |
| backlog-generator | sonnet | 4.00 | 4.00 | 3.50 | 3.83 |
| milestone-planner | sonnet | 3.50 | 4.25 | 3.25 | 3.67 |
| issue-feature-review | sonnet | 3.75 | 3.25 | 3.50 | 3.50 |
| retrospective | sonnet | 4.00 | 3.25 | 3.25 | 3.50 |
| roadmap | opus | 3.75 | 3.25 | 3.50 | 3.50 |
| **critic** | sonnet | 3.25 | 3.50 | 3.50 | **3.42** |
| **spec-generator** | sonnet | 3.75 | 2.75 | 3.75 | **3.42** |
| **orchestrator** | opus | 3.25 | 3.50 | 3.25 | **3.33** |
| **context-retrieval** | haiku | 3.00 | 3.50 | 3.00 | **3.17** |
| **analyst** | sonnet | 3.25 | 3.00 | 3.00 | **3.08** |
| **implementer** | opus | 2.75 | 2.75 | 3.00 | **2.83** |
| **explainer** | sonnet | 2.00 | 1.75 | 3.00 | **2.25** |

Key finding: Model does not predict quality. Prompt size inversely correlates with quality. Best agents are 7-9KB. Worst are 45-69KB.

## Out of Scope

- Merging or deleting agents (explicitly rejected by /autoplan CEO+Eng review)
- Changing skill definitions (already enriched in PR #1614)
- Modifying commands (/spec, /plan, /build, /test, /review, /ship)
- Committing org-specific content (team names, system names, internal references)
- Adding new eval dimensions (delegation accuracy, constraint compliance) -- deferred

## Open Questions

1. How much can orchestrator (69KB) be slimmed without losing coordination capability?
2. Which wiki content is generic enough to pass sanitization for a public repo?
3. Should boilerplate extraction go into AGENTS.md passive context or a separate shared file?

## Approach (from /autoplan review)

### Phase 1: Slim (measure-first)

1. Identify and extract duplicated boilerplate across all 23 agents (style guide, tool access, activation profiles)
2. Remove stale cross-agent references
3. Trim verbose instructions to follow Anthropic's "right altitude" guidance
4. Re-run baseline. Verify no regression.

### Phase 2: Enrich (targeted)

1. For each of the 7 lowest-scoring agents, identify which wiki content would improve their specific persona
2. Sanitize content: remove org-specific references, convert to transferable principles
3. Compress to "decision kernels" (2-3 canonical examples, not 50 rules)
4. Add inline, respecting the 16KB hard cap
5. Re-run assessment. Verify >= +0.5 delta in at least 4 of 7.

### Phase 3: Validate

1. Full baseline re-run on all 23 agents
2. Compare pre/post scores
3. Verify size constraints met (all agents under 16KB)

## CVA Summary

**Commonalities across agents (candidates for extraction):**
- Style guide compliance section (identical in all 23)
- Strategic knowledge references (Serena memory access patterns)
- Claude Code tool access declarations
- Activation profile / keyword matching

**Variabilities (must stay inline):**
- Core mission / role definition
- Output format expectations
- Tool access restrictions (read-only vs write)
- Model assignment (opus vs sonnet vs haiku)
- Decision framework references specific to role

**Relationships:**
- Orchestrator delegates to all other agents
- Reviewer agents (architect, critic, security) have read-only access
- Implementer has write access
- Planner agents produce artifacts consumed by implementer
- Analyst agents gather context consumed by planners and reviewers

## /autoplan Review Record

- **CEO Review**: 6/6 confirmed. Both Codex and Claude subagent rejected merge premise. Revised to slim+enrich.
- **Eng Review**: 6/6 confirmed. Size ceiling (16KB), security risk (public repo), eval gaps, spec staleness identified.
- **Design Review**: Skipped (no UI scope)
- **DX Review**: Skipped (infrastructure, not developer-facing API)
- **Verdict**: APPROVED (user accepted option A)
