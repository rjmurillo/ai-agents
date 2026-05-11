---
type: audit
id: AUDIT-2026-05-10-agent-skill
source: GH-2003
parent_epic: GH-1944
authority:
  - ADR-030
  - ADR-036
  - .agents/governance/agent-consolidation-process.md
created: 2026-05-10
git_sha: 7876c0c9
agent_count: 23
---

# Agent-Skill Classification Audit (2026-05-10)

Phase 1 deliverable for issue #2003. Classifies all 23 agents in `.claude/agents/` against the 4-criterion discriminator from #2001/#2002 plus a 5th frontmatter-bytes load-budget criterion (added because of Claude Code catalog truncation context observed in current sessions).

## Authority and method

- **ADR-030** Skills Pattern Superiority: documents skill latency (5-20ms) vs subagent spawn (100-200ms), lower token usage, direct MCP access. The discriminator's foundation.
- **ADR-036** Two-Source Agent Template Architecture: agents live in BOTH `src/claude/*.md` and `templates/agents/*.shared.md`. The `has_shared_template` column quantifies dual-source presence so Phase 2 refactors target both layouts.
- **`.agents/governance/agent-consolidation-process.md`**: the existing overlap-analysis matrix and recommendation thresholds. This audit applies it AND extends it with the 4-criterion discriminator + load-budget criterion.
- **PRD**: `.agents/specs/PRD-agent-skill-classification-audit.md` (committed in the spec commit on this branch).
- **Spec**: REQ-011 / DESIGN-011 / TASK-011.

### Discriminator (per #2001/#2002)

An agent should be a skill (not an agent) if 2+ of these are true:

1. **c1**: Invoked from a slash command via `Task(subagent_type=...)` rather than spawned by a peer agent.
2. **c2**: Body is ≥70% structured-reference material (tables, decision-tree lists, anti-pattern catalogs, format/schema specs, validation rule lists) per PRD §11 lock-in.
3. **c3**: Sibling artifact in the same pipeline is already a skill. N/A when invoked from 3+ slash commands (per PRD §11 3-pipeline rule).
4. **c4**: Has produced schema/format drift caught by review automation (CodeRabbit, Copilot bot, etc.).

### Load-budget criterion (added 2026-05-10 because of Claude truncation context)

5. **c5_frontmatter_bytes**: bytes of agent frontmatter (always-loaded portion of the catalog). Quantifies load-budget impact of skill-migration verdicts.

### Verdict rule

```
discriminator_score = c1 + c2 + c3 + c4
verdict = skill                if score >= 2 AND no isolation requirement
verdict = context-fork-skill   if score >= 2 AND isolation benefits exist BUT context: fork serves
verdict = keep-as-agent        if score >= 2 AND genuine reasoning-asymmetry isolation required
                                  OR if score < 2
verdict = merge-into-X         if >=70% capability overlap with another agent (Phase 2 measurement; not assessed here)
```

Isolation exceptions per #2003 counter-signal section + PRD AC-6: `orchestrator`, `analyst`, `critic`. (`pr-comment-responder` is already a skill in this codebase.)

## Audit table

| agent | c1 | c2 | c3 | c4 | scr | c5_fm_B | c5_full_B | shared | verdict | rationale |
|-------|----|----|----|----|-----|---------|-----------|--------|---------|-----------|
| `spec-generator` | 1 | 1 | 1 | 1 | 4/4 | 494 | 5868 | No | **skill** | discriminator_score=4/4 (c1=1, c2=1, c3=1, c4=1); 2-of-4 rule fires; no isolatio |
| `devops` | 1 | 1 | 1 | 0 | 3/4 | 494 | 15574 | Yes | **skill** | discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolatio |
| `implementer` | 1 | 1 | 1 | 0 | 3/4 | 658 | 18928 | Yes | **skill** | discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolatio |
| `milestone-planner` | 1 | 1 | 1 | 0 | 3/4 | 458 | 6623 | Yes | **skill** | discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolatio |
| `qa` | 1 | 1 | 1 | 0 | 3/4 | 473 | 25654 | Yes | **skill** | discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolatio |
| `task-decomposer` | 1 | 1 | 1 | 0 | 3/4 | 462 | 10359 | Yes | **skill** | discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolatio |
| `context-retrieval` | 1 | 1 | 0 | 0 | 2/4 | 720 | 5171 | No | **skill** | discriminator_score=2/4 (c1=1, c2=1, c3=0, c4=0); 2-of-4 rule fires; no isolatio |
| `architect` | 1 | 1 | 1 | 0 | 3/4 | 489 | 23581 | Yes | **context-fork-skill** | score=3/4; isolation benefits exist but context: fork serves: governance review  |
| `security` | 1 | 1 | 1 | 0 | 3/4 | 466 | 32567 | Yes | **context-fork-skill** | score=3/4; isolation benefits exist but context: fork serves: reviews diffs for  |
| `analyst` | 1 | 1 | 0 | 0 | 2/4 | 488 | 6925 | Yes | **keep-as-agent** | isolation exception: investigation-time code reads are massive; context: fork co |
| `adr-generator` | 0 | 1 | 0 | 0 | 1/4 | 228 | 6684 | No | **keep-as-agent** | discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected |
| `backlog-generator` | 0 | 1 | 0 | 0 | 1/4 | 455 | 6905 | Yes | **keep-as-agent** | discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected |
| `critic` | 1 | 0 | 0 | 0 | 1/4 | 445 | 12680 | Yes | **keep-as-agent** | isolation exception: fresh-context adversarial review is the agent's CORE functi |
| `explainer` | 0 | 1 | 0 | 0 | 1/4 | 489 | 6034 | Yes | **keep-as-agent** | discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected |
| `issue-feature-review` | 0 | 1 | 0 | 0 | 1/4 | 371 | 7884 | Yes | **keep-as-agent** | discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected |
| `memory` | 0 | 1 | 0 | 0 | 1/4 | 505 | 14127 | Yes | **keep-as-agent** | discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected |
| `orchestrator` | 0 | 1 | 0 | 0 | 1/4 | 479 | 15237 | Yes | **keep-as-agent** | isolation exception: routes tasks across all agents; needs isolated routing cont |
| `quality-auditor` | 0 | 1 | 0 | 0 | 1/4 | 408 | 3533 | No | **keep-as-agent** | discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected |
| `retrospective` | 0 | 1 | 0 | 0 | 1/4 | 509 | 43362 | Yes | **keep-as-agent** | discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected |
| `roadmap` | 0 | 1 | 0 | 0 | 1/4 | 472 | 6149 | Yes | **keep-as-agent** | discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected |
| `skillbook` | 0 | 1 | 0 | 0 | 1/4 | 497 | 7603 | Yes | **keep-as-agent** | discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected |
| `high-level-advisor` | 0 | 0 | 0 | 0 | 0/4 | 452 | 8471 | Yes | **keep-as-agent** | discriminator_score=0/4; below 2-of-4 threshold; no shape mismatch detected |
| `independent-thinker` | 0 | 0 | 0 | 0 | 0/4 | 467 | 8258 | Yes | **keep-as-agent** | discriminator_score=0/4; below 2-of-4 threshold; no shape mismatch detected |

### Per-criterion evidence

For each agent, evidence justifying the score:

#### `spec-generator` (skill, score=4/4)

- **c1 (Yes)**: .claude/commands/spec.md:365
- **c2 (>=70%)**: 76/95 lines structured (80%); 13 table sep, 1 code blocks, 28 list items, anti-pattern hd, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: spec.md: Skill(chestertons-fence); spec.md: Skill(memory); spec.md: Skill(memory)
- **c4 (Yes)**: PR #1995: 9-of-13 frontmatter schema violations (priority, category, status, complexity enums); PR #1989 similar drift documented in #2001
- **c5_frontmatter_bytes**: 494 (full body: 5868)
- **has_shared_template**: No
- **verdict_rationale**: discriminator_score=4/4 (c1=1, c2=1, c3=1, c4=1); 2-of-4 rule fires; no isolation requirement documented

#### `devops` (skill, score=3/4)

- **c1 (Yes)**: .claude/commands/ship.md:15; .claude/commands/test.md:72
- **c2 (>=70%)**: 332/366 lines structured (91%); 6 table sep, 7 code blocks, 40 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: test.md: Skill(code-qualities-assessment); test.md: Skill(security-scan); test.md: Skill(quality-grades)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 494 (full body: 15574)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented

#### `implementer` (skill, score=3/4)

- **c1 (Yes)**: .claude/commands/build.md:27
- **c2 (>=70%)**: 147/192 lines structured (77%); 9 table sep, 105 list items, anti-pattern hd, validation/rules hd
- **c3 (Yes)**: build.md: Skill(pre-mortem); build.md: Skill(code-qualities-assessment); build.md: Skill(taste-lints)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 658 (full body: 18928)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented

#### `milestone-planner` (skill, score=3/4)

- **c1 (Yes)**: .claude/commands/plan.md:17
- **c2 (>=70%)**: 106/124 lines structured (85%); 9 table sep, 1 code blocks, 28 list items, anti-pattern hd, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: plan.md: Skill(execution-plans)
- **c4 (No)**: emits milestone documents; PR search returned 0 matches
- **c5_frontmatter_bytes**: 458 (full body: 6623)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented

#### `qa` (skill, score=3/4)

- **c1 (Yes)**: .claude/commands/test.md:33
- **c2 (>=70%)**: 486/544 lines structured (89%); 16 table sep, 11 code blocks, 68 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: test.md: Skill(code-qualities-assessment); test.md: Skill(security-scan); test.md: Skill(quality-grades)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 473 (full body: 25654)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented

#### `task-decomposer` (skill, score=3/4)

- **c1 (Yes)**: .claude/commands/plan.md:18
- **c2 (>=70%)**: 199/224 lines structured (89%); 10 table sep, 6 code blocks, 36 list items, anti-pattern hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: plan.md: Skill(execution-plans)
- **c4 (No)**: emits TASK files; PR search returned 0 matches
- **c5_frontmatter_bytes**: 462 (full body: 10359)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented

#### `context-retrieval` (skill, score=2/4)

- **c1 (Yes)**: .claude/commands/forgetful/memory-explore.md:11
- **c2 (>=70%)**: 51/63 lines structured (81%); 4 table sep, 0 code blocks, 16 list items, format/schema hd, validation/rules hd
- **c3 (No)**: pipeline files ['memory-explore.md']: no Skill() siblings found
- **c4 (No)**: emits memory/index updates; PR search returned 0 matches
- **c5_frontmatter_bytes**: 720 (full body: 5171)
- **has_shared_template**: No
- **verdict_rationale**: discriminator_score=2/4 (c1=1, c2=1, c3=0, c4=0); 2-of-4 rule fires; no isolation requirement documented

#### `architect` (context-fork-skill, score=3/4)

- **c1 (Yes)**: .claude/commands/test.md:96
- **c2 (>=70%)**: 404/448 lines structured (90%); 13 table sep, 7 code blocks, 69 list items, anti-pattern hd, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: test.md: Skill(code-qualities-assessment); test.md: Skill(security-scan); test.md: Skill(quality-grades)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 489 (full body: 23581)
- **has_shared_template**: Yes
- **verdict_rationale**: score=3/4; isolation benefits exist but context: fork serves: governance review benefits from isolation; context: fork serves

#### `security` (context-fork-skill, score=3/4)

- **c1 (Yes)**: .claude/commands/test.md:60
- **c2 (>=70%)**: 561/622 lines structured (90%); 9 table sep, 9 code blocks, 144 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: test.md: Skill(code-qualities-assessment); test.md: Skill(security-scan); test.md: Skill(quality-grades)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 466 (full body: 32567)
- **has_shared_template**: Yes
- **verdict_rationale**: score=3/4; isolation benefits exist but context: fork serves: reviews diffs for vulns; benefits from isolated context but no genuine reasoning-asymmetry; context: fork serves

#### `analyst` (keep-as-agent, score=2/4)

- **c1 (Yes)**: .claude/commands/build.md:15; .claude/commands/plan.md:20; .claude/commands/review.md:24
- **c2 (>=70%)**: 80/106 lines structured (75%); 6 table sep, 0 code blocks, 21 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (N/A)**: invoked from 5 distinct slash commands; per 3-pipeline rule
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 488 (full body: 6925)
- **has_shared_template**: Yes
- **verdict_rationale**: isolation exception: investigation-time code reads are massive; context: fork could work but #2003 counter-signal explicitly lists analyst as agent-shape

#### `adr-generator` (keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 122/149 lines structured (82%); 0 code blocks, 86 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (No)**: emits ADR frontmatter and structure; PR search returned 0 matches
- **c5_frontmatter_bytes**: 228 (full body: 6684)
- **has_shared_template**: No
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `backlog-generator` (keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 83/105 lines structured (79%); 10 table sep, 1 code blocks, 43 list items, validation/rules hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (No)**: emits backlog items; PR search returned 0 matches
- **c5_frontmatter_bytes**: 455 (full body: 6905)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `critic` (keep-as-agent, score=1/4)

- **c1 (Yes)**: .claude/commands/plan.md:21; .claude/commands/spec.md:372; .claude/commands/test.md:84
- **c2 (50-69%)**: 99/129 lines structured (77%); 8 table sep, 0 code blocks, 34 list items, anti-pattern hd, format/schema hd, validation/rules hd -> manual review: 'Reviewer Asymmetry' and 'Core Behavior' sections are reasoning prose; Adversarial Coverage Checklist is reference but not dominant; 50-69%
- **c3 (N/A)**: invoked from 3 distinct slash commands; per 3-pipeline rule
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 445 (full body: 12680)
- **has_shared_template**: Yes
- **verdict_rationale**: isolation exception: fresh-context adversarial review is the agent's CORE function (per body 'Reviewer Asymmetry' section); context: fork would break the asymmetry

#### `explainer` (keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 73/89 lines structured (82%); 5 table sep, 41 list items, anti-pattern hd, decision/criteria hd, format/schema hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (No)**: emits PRD/spec documents; PR search returned 0 matches
- **c5_frontmatter_bytes**: 489 (full body: 6034)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `issue-feature-review` (keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 86/104 lines structured (83%); 8 table sep, 0 code blocks, 18 list items, anti-pattern hd, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 371 (full body: 7884)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `memory` (keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 248/296 lines structured (84%); 26 table sep, 9 code blocks, 55 list items, decision/criteria hd, format/schema hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (No)**: emits memory entries (per memory schema); PR search returned 0 matches
- **c5_frontmatter_bytes**: 505 (full body: 14127)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `orchestrator` (keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 142/177 lines structured (80%); 18 table sep, 1 code blocks, 57 list items, anti-pattern hd, decision/criteria hd, validation/rules hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 479 (full body: 15237)
- **has_shared_template**: Yes
- **verdict_rationale**: isolation exception: routes tasks across all agents; needs isolated routing context that does not pollute parent thread (AGENTS.md orchestrator pattern)

#### `quality-auditor` (keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 54/62 lines structured (87%); 0 code blocks, 34 list items, format/schema hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 408 (full body: 3533)
- **has_shared_template**: No
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `retrospective` (keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 883/1017 lines structured (87%); 41 table sep, 20 code blocks, 97 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 509 (full body: 43362)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `roadmap` (keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 91/106 lines structured (86%); 8 table sep, 1 code blocks, 24 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 472 (full body: 6149)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `skillbook` (keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 89/115 lines structured (77%); 23 table sep, 1 code blocks, 22 list items, anti-pattern hd, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (No)**: emits skill files (per SKILL-CREATION-CRITERIA); PR search returned 0 matches
- **c5_frontmatter_bytes**: 497 (full body: 7603)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `high-level-advisor` (keep-as-agent, score=0/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (50-69%)**: 162/199 lines structured (81%); 3 table sep, 3 code blocks, 69 list items, decision/criteria hd, format/schema hd -> manual review: Strategic frameworks/memories are reference; verdict-delivery prose is reasoning; mixed 50-69%
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 452 (full body: 8471)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=0/4; below 2-of-4 threshold; no shape mismatch detected

#### `independent-thinker` (keep-as-agent, score=0/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (50-69%)**: 137/169 lines structured (81%); 1 table sep, 2 code blocks, 49 list items, decision/criteria hd, format/schema hd -> manual review: Persona Traits + Core Mission are reasoning; Style Guide + Activation Profile are reference; mixed 50-69%
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 467 (full body: 8258)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=0/4; below 2-of-4 threshold; no shape mismatch detected

## Summary

- **Total agents audited**: 23 (matches `ls .claude/agents/*.md | grep -v -E '(AGENTS|CLAUDE)\.md' | wc -l`)
- **Verdict counts**:
  - `skill`: 7
  - `context-fork-skill`: 2
  - `keep-as-agent`: 14
  - `merge-into-X`: 0 (not assessed in Phase 1; deferred to Phase 2 with overlap analysis per `agent-consolidation-process.md`)
- **Load-budget impact**: total frontmatter bytes = 10979; bytes saved if all `skill`+`context-fork-skill` rows migrate = **4714 (42% of always-loaded portion)**.
- **Total agent body bytes (on-demand load)**: 298177.
- **Dual-source coverage (ADR-036)**: 19/23 agents have `templates/agents/*.shared.md` siblings.

## Phase 2 backlog (`verdict != keep-as-agent`)

Each candidate becomes a separate filed issue per `phase_2_3_governance: separate-issues`.

- **`spec-generator`** -> `skill`
  - Target: `.claude/skills/spec-generator/SKILL.md`
  - Justification: discriminator_score=4/4 (c1=1, c2=1, c3=1, c4=1); 2-of-4 rule fires; no isolation requirement documented
  - Refactor must update: `.claude/agents/spec-generator.md` (delete or thin shim) (no shared template; Claude-only)
  - Note: also covered by closed issue #2001; this audit row is the canonical case (4/4 score).

- **`devops`** -> `skill`
  - Target: `.claude/skills/devops/SKILL.md`
  - Justification: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented
  - Refactor must update: `.claude/agents/devops.md` (delete or thin shim), `templates/agents/devops.shared.md` (per ADR-036)

- **`implementer`** -> `skill`
  - Target: `.claude/skills/implementer/SKILL.md`
  - Justification: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented
  - Refactor must update: `.claude/agents/implementer.md` (delete or thin shim), `templates/agents/implementer.shared.md` (per ADR-036)

- **`milestone-planner`** -> `skill`
  - Target: `.claude/skills/milestone-planner/SKILL.md`
  - Justification: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented
  - Refactor must update: `.claude/agents/milestone-planner.md` (delete or thin shim), `templates/agents/milestone-planner.shared.md` (per ADR-036)

- **`qa`** -> `skill`
  - Target: `.claude/skills/qa/SKILL.md`
  - Justification: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented
  - Refactor must update: `.claude/agents/qa.md` (delete or thin shim), `templates/agents/qa.shared.md` (per ADR-036)

- **`task-decomposer`** -> `skill`
  - Target: `.claude/skills/task-decomposer/SKILL.md`
  - Justification: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented
  - Refactor must update: `.claude/agents/task-decomposer.md` (delete or thin shim), `templates/agents/task-decomposer.shared.md` (per ADR-036)

- **`context-retrieval`** -> `skill`
  - Target: `.claude/skills/context-retrieval/SKILL.md`
  - Justification: discriminator_score=2/4 (c1=1, c2=1, c3=0, c4=0); 2-of-4 rule fires; no isolation requirement documented
  - Refactor must update: `.claude/agents/context-retrieval.md` (delete or thin shim) (no shared template; Claude-only)

- **`architect`** -> `context-fork-skill` (with `context: fork` in skill frontmatter)
  - Target: `.claude/skills/architect/SKILL.md`
  - Justification: score=3/4; isolation benefits exist but context: fork serves: governance review benefits from isolation; context: fork serves
  - Refactor must update: `.claude/agents/architect.md` (delete or thin shim), `templates/agents/architect.shared.md` (per ADR-036)

- **`security`** -> `context-fork-skill` (with `context: fork` in skill frontmatter)
  - Target: `.claude/skills/security/SKILL.md`
  - Justification: score=3/4; isolation benefits exist but context: fork serves: reviews diffs for vulns; benefits from isolated context but no genuine reasoning-asymmetry; context: fork serves
  - Refactor must update: `.claude/agents/security.md` (delete or thin shim), `templates/agents/security.shared.md` (per ADR-036)

## Out of scope (per PRD §9)

- Phase 2 refactor PRs (one per skill candidate above). Each is a separately filed issue per `phase_2_3_governance: separate-issues`.
- Phase 3 CI check implementation. See linked stub issue.
- 24th `caveman` agent under `~/.claude/`. Not in `.claude/agents/`.
- Downstream platform variants under `src/copilot-cli/agents/` and `src/vs-code-agents/`.
- Quantitative ranking via `eval-knowledge-integration.py` / `eval-skill-overlap.py` (#1932). Deferred to Phase 2.
- `merge-into-X` verdicts (require pairwise overlap analysis; deferred to Phase 2).

## Notes

### c4 (schema-drift) confidence

Only `spec-generator` scored Yes on c4 (documented in #2001 with PR #1995 evidence). Other structured-output agents (`adr-generator`, `milestone-planner`, `task-decomposer`, `backlog-generator`, `explainer`, `skillbook`, `memory`, `context-retrieval`) were marked No conservatively after PR-history search returned no comparable schema-drift threads. **Phase 2 reviewers should re-examine c4 if a structured-output agent has produced schema drift since 2026-05-10**: a single drift incident moves the verdict from `keep-as-agent` to `skill` for several of these.

### c2 (reference vs reasoning) heuristic limitation

The automated heuristic (lines counted: tables + lists + headings + code blocks) over-estimated reference content for reasoning-focused agents. Manual deflation applied to: `critic`, `independent-thinker`, `high-level-advisor`. `analyst` was kept at ≥70% (genuine decision-table dominance). Per PRD §11 lock-in, only decision-tree bullets count, not all bullets. Reviewers may rebalance individual c2 scores; the c2 column documents the count.

### Isolation exceptions

Per #2003 counter-signal + PRD AC-6, three agents are kept as agents despite scoring >=2: `orchestrator`, `analyst`, `critic`. Each has documented isolation requirement (orchestrator routes across all agents; analyst/critic need fresh-context reasoning asymmetry). `context: fork` cannot serve these because the ASYMMETRY (no shared parent state) is the function, not the side-effect.

### `keep-as-agent` agents that are never invoked from slash commands (c1=No)

Several agents (`adr-generator`, `backlog-generator`, `explainer`, `issue-feature-review`, `quality-auditor`, `roadmap`, `skillbook`, `high-level-advisor`, `independent-thinker`, `memory`) scored c1=0 and are kept-as-agent by the rule. **A separate triage** (not in #2003 scope) should evaluate whether these are dead code, peer-only invocations, or genuine but undiscoverable agents. Recommend filing a follow-up issue if invocation counts from session logs show <5% usage per `agent-consolidation-process.md` trigger.

### Phase 3 CI check

Per PRD AC-12 + issue #2003 acceptance criterion 4, the Phase 3 CI check (detect new agents matching skill discriminator) is filed as a separate stub issue: **#2008**.

### Validation

This audit's REQ-011 / DESIGN-011 / TASK-011 frontmatter was validated against `.agents/governance/spec-schemas.md` before commit (the very anti-pattern this audit addresses). spec-schemas was read before write; no enum drift introduced.
