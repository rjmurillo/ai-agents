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
git_sha: 31ce4bc6
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

1. **c1**: Invoked from a slash command via `Task(subagent_type=...)` rather than spawned by a peer agent. Detection includes both literal forms (e.g., `Task(subagent_type="agent")`) and descriptive forms in slash command docs that name the agent in a parenthesized list paired with a `Task(subagent_type=...)` template.
2. **c2**: Body is >=70% structured-reference material (tables, decision-tree lists, anti-pattern catalogs, format/schema specs, validation rule lists) per PRD section 11 lock-in.
3. **c3**: Sibling artifact in the same pipeline is already a skill. N/A when invoked from 3+ slash commands (per PRD section 11 3-pipeline rule).
4. **c4**: Has produced schema/format drift caught by review automation (CodeRabbit, Copilot bot, etc.).

### Load-budget criterion (added 2026-05-10 because of Claude truncation context)

5. **c5_frontmatter_bytes**: bytes of agent frontmatter (always-loaded portion of the catalog). Quantifies load-budget impact of skill-migration verdicts.

### Verdict rule (canonical; reconciled with DESIGN-011 section C3 and PRD AC-6)

```
discriminator_score = c1 + c2 + c3 + c4
  (c1=Yes counts 1; c2=>=70% counts 1; c3=Yes counts 1; c4=Yes counts 1; everything else 0)

isolation = hard | soft | none
  hard: agent body documents that it MUST NOT see/pollute parent's context
        (orchestrator routing, critic adversarial review, analyst
        bias-free investigation per #2003 counter-signal). context: fork
        leaks parent working state and breaks the asymmetry/independence
        the agent's function depends on.
  soft: agent benefits from a fresh sub-context but does not require
        parent-context exclusion. context: fork (skill mode) serves.
  none: no isolation requirement.

verdict = keep-as-agent       if isolation = hard
verdict = context-fork-skill  if score >= 2 AND isolation = soft
verdict = skill               if score >= 2 AND isolation = none
verdict = keep-as-agent       if score < 2 (no shape mismatch detected)
verdict = merge-into-X        if >= 70% capability overlap with another agent
                              (Phase 2 measurement; not assessed here)
```

The hard/soft/none distinction reconciles three previously-divergent rules: DESIGN-011 section C3 originally collapsed hard+soft into a single `isolation_exception` flag; PRD AC-6 said `keep-as-agent` only when `context: fork` cannot satisfy; the audit applies the hard/soft split to make both consistent.

Hard-isolation agents identified per #2003 counter-signal: `orchestrator`, `analyst`, `critic` (`pr-comment-responder` is already a skill in this codebase). Soft-isolation candidates identified during this audit: `architect`, `security`, `independent-thinker`, `high-level-advisor`, `memory`, `retrospective`.

## Audit table

Columns: agent | c1 | c2 | c3 | c4 | discriminator_score | c5_frontmatter_bytes | c5_full_body_bytes | has_shared_template | verdict | rationale (full text below per row in "Per-criterion evidence" section). The numeric c1/c2/c3/c4 cells use 1 for Yes/>=70%/Yes/Yes and 0 otherwise; c2 enum string and c4 Unknown distinction are preserved in the per-row evidence section below.

| agent | c1 | c2 | c3 | c4 | scr | c5_fm_B | c5_full_B | shared | verdict |
|-------|----|----|----|----|-----|---------|-----------|--------|---------|
| `spec-generator` | 1 | 1 | 1 | 1 | 4/4 | 494 | 5868 | No | **skill** |
| `devops` | 1 | 1 | 1 | 0 | 3/4 | 494 | 15574 | Yes | **skill** |
| `implementer` | 1 | 1 | 1 | 0 | 3/4 | 658 | 18928 | Yes | **skill** |
| `milestone-planner` | 1 | 1 | 1 | 0 | 3/4 | 458 | 6623 | Yes | **skill** |
| `qa` | 1 | 1 | 1 | 0 | 3/4 | 473 | 25654 | Yes | **skill** |
| `roadmap` | 1 | 1 | 1 | 0 | 3/4 | 472 | 6149 | Yes | **skill** |
| `task-decomposer` | 1 | 1 | 1 | 0 | 3/4 | 462 | 10359 | Yes | **skill** |
| `context-retrieval` | 1 | 1 | 0 | 0 | 2/4 | 720 | 5171 | No | **skill** |
| `architect` | 1 | 1 | 1 | 0 | 3/4 | 489 | 23581 | Yes | **context-fork-skill** |
| `security` | 1 | 1 | 1 | 0 | 3/4 | 466 | 32567 | Yes | **context-fork-skill** |
| `analyst` | 1 | 1 | 0 | 0 | 2/4 | 488 | 6925 | Yes | **keep-as-agent** |
| `adr-generator` | 0 | 1 | 0 | 0 | 1/4 | 228 | 6684 | No | **keep-as-agent** |
| `backlog-generator` | 0 | 1 | 0 | 0 | 1/4 | 455 | 6905 | Yes | **keep-as-agent** |
| `critic` | 1 | 0 | 0 | 0 | 1/4 | 445 | 12680 | Yes | **keep-as-agent** |
| `explainer` | 0 | 1 | 0 | 0 | 1/4 | 489 | 6034 | Yes | **keep-as-agent** |
| `issue-feature-review` | 0 | 1 | 0 | 0 | 1/4 | 371 | 7884 | Yes | **keep-as-agent** |
| `memory` | 0 | 1 | 0 | 0 | 1/4 | 505 | 14127 | Yes | **keep-as-agent** |
| `orchestrator` | 0 | 1 | 0 | 0 | 1/4 | 479 | 15237 | Yes | **keep-as-agent** |
| `quality-auditor` | 0 | 1 | 0 | 0 | 1/4 | 408 | 3533 | No | **keep-as-agent** |
| `retrospective` | 0 | 1 | 0 | 0 | 1/4 | 509 | 43362 | Yes | **keep-as-agent** |
| `skillbook` | 0 | 1 | 0 | 0 | 1/4 | 497 | 7603 | Yes | **keep-as-agent** |
| `high-level-advisor` | 0 | 0 | 0 | 0 | 0/4 | 452 | 8471 | Yes | **keep-as-agent** |
| `independent-thinker` | 0 | 0 | 0 | 0 | 0/4 | 467 | 8258 | Yes | **keep-as-agent** |

### Per-criterion evidence and rationale (full text)

For each agent, evidence justifying every score plus the verdict rationale. Numeric `c1..c4` cells in the table above collapse {Yes, >=70%, Yes, Yes} to 1 and {No, <70%, No, No, Unknown, N/A} to 0; this section preserves the full enum value and evidence per the schema in DESIGN-011 section C2.

#### `spec-generator` (verdict=skill, score=4/4)

- **c1 (Yes)**: .claude/commands/spec.md:365
- **c2 (>=70%)**: 76/95 lines structured (80%); 13 table sep, 1 code blocks, 28 list items, anti-pattern hd, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: spec.md: Skill(chestertons-fence); spec.md: Skill(memory); spec.md: Skill(memory)
- **c4 (Yes)**: PR #1995: 9-of-13 frontmatter schema violations (priority, category, status, complexity enums); PR #1989 similar drift documented in #2001
- **c5_frontmatter_bytes**: 494 (full body: 5868)
- **has_shared_template**: No
- **verdict_rationale**: discriminator_score=4/4 (c1=1, c2=1, c3=1, c4=1); 2-of-4 rule fires; no isolation requirement documented

#### `devops` (verdict=skill, score=3/4)

- **c1 (Yes)**: .claude/commands/ship.md:15; .claude/commands/test.md:72
- **c2 (>=70%)**: 332/366 lines structured (91%); 6 table sep, 7 code blocks, 40 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: test.md: Skill(code-qualities-assessment); test.md: Skill(security-scan); test.md: Skill(quality-grades)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 494 (full body: 15574)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented

#### `implementer` (verdict=skill, score=3/4)

- **c1 (Yes)**: .claude/commands/build.md:27
- **c2 (>=70%)**: 147/192 lines structured (77%); 9 table sep, 105 list items, anti-pattern hd, validation/rules hd
- **c3 (Yes)**: build.md: Skill(pre-mortem); build.md: Skill(code-qualities-assessment); build.md: Skill(taste-lints)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 658 (full body: 18928)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented

#### `milestone-planner` (verdict=skill, score=3/4)

- **c1 (Yes)**: .claude/commands/plan.md:17
- **c2 (>=70%)**: 106/124 lines structured (85%); 9 table sep, 1 code blocks, 28 list items, anti-pattern hd, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: plan.md: Skill(execution-plans)
- **c4 (No)**: emits milestone documents; PR search returned 0 matches
- **c5_frontmatter_bytes**: 458 (full body: 6623)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented

#### `qa` (verdict=skill, score=3/4)

- **c1 (Yes)**: .claude/commands/test.md:33
- **c2 (>=70%)**: 486/544 lines structured (89%); 16 table sep, 11 code blocks, 68 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: test.md: Skill(code-qualities-assessment); test.md: Skill(security-scan); test.md: Skill(quality-grades)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 473 (full body: 25654)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented

#### `roadmap` (verdict=skill, score=3/4)

- **c1 (Yes)**: .claude/commands/review.md:32 (descriptive form: 'Task(subagent_type=...) agent (analyst, architect, qa, security, devops, roadmap)')
- **c2 (>=70%)**: 91/106 lines structured (86%); 8 table sep, 1 code blocks, 24 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: review.md: Skill(code-qualities-assessment), Skill(golden-principles), Skill(taste-lints) (3 sibling skills in same pipeline)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 472 (full body: 6149)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented (strategic alignment, not separate-context reasoning)

#### `task-decomposer` (verdict=skill, score=3/4)

- **c1 (Yes)**: .claude/commands/plan.md:18
- **c2 (>=70%)**: 199/224 lines structured (89%); 10 table sep, 6 code blocks, 36 list items, anti-pattern hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: plan.md: Skill(execution-plans)
- **c4 (No)**: emits TASK files; PR search returned 0 matches
- **c5_frontmatter_bytes**: 462 (full body: 10359)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented

#### `context-retrieval` (verdict=skill, score=2/4)

- **c1 (Yes)**: .claude/commands/forgetful/memory-explore.md:11
- **c2 (>=70%)**: 51/63 lines structured (81%); 4 table sep, 0 code blocks, 16 list items, format/schema hd, validation/rules hd
- **c3 (No)**: pipeline files ['memory-explore.md']: no Skill() siblings found
- **c4 (No)**: emits memory/index updates; PR search returned 0 matches
- **c5_frontmatter_bytes**: 720 (full body: 5171)
- **has_shared_template**: No
- **verdict_rationale**: discriminator_score=2/4 (c1=1, c2=1, c3=0, c4=0); 2-of-4 rule fires; no isolation requirement documented

#### `architect` (verdict=context-fork-skill, score=3/4)

- **c1 (Yes)**: .claude/commands/test.md:96
- **c2 (>=70%)**: 404/448 lines structured (90%); 13 table sep, 7 code blocks, 69 list items, anti-pattern hd, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: test.md: Skill(code-qualities-assessment); test.md: Skill(security-scan); test.md: Skill(quality-grades)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 489 (full body: 23581)
- **has_shared_template**: Yes
- **verdict_rationale**: score=3/4; isolation benefits exist but context: fork serves: governance review benefits from isolation; context: fork serves

#### `security` (verdict=context-fork-skill, score=3/4)

- **c1 (Yes)**: .claude/commands/test.md:60
- **c2 (>=70%)**: 561/622 lines structured (90%); 9 table sep, 9 code blocks, 144 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (Yes)**: test.md: Skill(code-qualities-assessment); test.md: Skill(security-scan); test.md: Skill(quality-grades)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 466 (full body: 32567)
- **has_shared_template**: Yes
- **verdict_rationale**: score=3/4; isolation benefits exist but context: fork serves: reviews diffs for vulns; benefits from isolated context but no genuine reasoning-asymmetry; context: fork serves

#### `analyst` (verdict=keep-as-agent, score=2/4)

- **c1 (Yes)**: .claude/commands/build.md:15; .claude/commands/plan.md:20; .claude/commands/review.md:24
- **c2 (>=70%)**: 80/106 lines structured (75%); 6 table sep, 0 code blocks, 21 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (N/A)**: invoked from 5 distinct slash commands; per 3-pipeline rule
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 488 (full body: 6925)
- **has_shared_template**: Yes
- **verdict_rationale**: hard isolation: investigation must not see parent's reasoning to avoid confirmation bias; #2003 counter-signal lists analyst alongside orchestrator/critic/pr-comment-responder as a 'must not see parent's context' agent. context: fork still couples to parent's working state.

#### `adr-generator` (verdict=keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 122/149 lines structured (82%); 0 code blocks, 86 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (No)**: emits ADR frontmatter and structure; PR search returned 0 matches
- **c5_frontmatter_bytes**: 228 (full body: 6684)
- **has_shared_template**: No
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `backlog-generator` (verdict=keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 83/105 lines structured (79%); 10 table sep, 1 code blocks, 43 list items, validation/rules hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (No)**: emits backlog items; PR search returned 0 matches
- **c5_frontmatter_bytes**: 455 (full body: 6905)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `critic` (verdict=keep-as-agent, score=1/4)

- **c1 (Yes)**: .claude/commands/plan.md:21; .claude/commands/spec.md:372; .claude/commands/test.md:84
- **c2 (50-69%)**: 99/129 lines structured (77%); 8 table sep, 0 code blocks, 34 list items, anti-pattern hd, format/schema hd, validation/rules hd -> manual review: 'Reviewer Asymmetry' and 'Core Behavior' sections are reasoning prose; Adversarial Coverage Checklist is reference but not dominant; 50-69%
- **c3 (N/A)**: invoked from 3 distinct slash commands; per 3-pipeline rule
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 445 (full body: 12680)
- **has_shared_template**: Yes
- **verdict_rationale**: hard isolation: fresh-context adversarial review IS the function; sharing any parent state breaks the asymmetry. context: fork would partially leak parent state and break the reviewer-asymmetry guarantee documented in critic.md 'Reviewer Asymmetry' section.

#### `explainer` (verdict=keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 73/89 lines structured (82%); 5 table sep, 41 list items, anti-pattern hd, decision/criteria hd, format/schema hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (No)**: emits PRD/spec documents; PR search returned 0 matches
- **c5_frontmatter_bytes**: 489 (full body: 6034)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `issue-feature-review` (verdict=keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 86/104 lines structured (83%); 8 table sep, 0 code blocks, 18 list items, anti-pattern hd, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 371 (full body: 7884)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `memory` (verdict=keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 248/296 lines structured (84%); 26 table sep, 9 code blocks, 55 list items, decision/criteria hd, format/schema hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (No)**: emits memory entries (per memory schema); PR search returned 0 matches
- **c5_frontmatter_bytes**: 505 (full body: 14127)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `orchestrator` (verdict=keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 142/177 lines structured (80%); 18 table sep, 1 code blocks, 57 list items, anti-pattern hd, decision/criteria hd, validation/rules hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 479 (full body: 15237)
- **has_shared_template**: Yes
- **verdict_rationale**: hard isolation: routes work across all agents; must not see/pollute parent context (per #2003 counter-signal). context: fork would still leak parent state into routing decisions.

#### `quality-auditor` (verdict=keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 54/62 lines structured (87%); 0 code blocks, 34 list items, format/schema hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 408 (full body: 3533)
- **has_shared_template**: No
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `retrospective` (verdict=keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 883/1017 lines structured (87%); 41 table sep, 20 code blocks, 97 list items, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 509 (full body: 43362)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `skillbook` (verdict=keep-as-agent, score=1/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (>=70%)**: 89/115 lines structured (77%); 23 table sep, 1 code blocks, 22 list items, anti-pattern hd, decision/criteria hd, format/schema hd, validation/rules hd
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (No)**: emits skill files (per SKILL-CREATION-CRITERIA); PR search returned 0 matches
- **c5_frontmatter_bytes**: 497 (full body: 7603)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=1/4; below 2-of-4 threshold; no shape mismatch detected

#### `high-level-advisor` (verdict=keep-as-agent, score=0/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (50-69%)**: 162/199 lines structured (81%); 3 table sep, 3 code blocks, 69 list items, decision/criteria hd, format/schema hd -> manual review: Strategic frameworks/memories are reference; verdict-delivery prose is reasoning; mixed 50-69%
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 452 (full body: 8471)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=0/4; below 2-of-4 threshold; no shape mismatch detected

#### `independent-thinker` (verdict=keep-as-agent, score=0/4)

- **c1 (No)**: no slash-command Task() invocation found
- **c2 (50-69%)**: 137/169 lines structured (81%); 1 table sep, 2 code blocks, 49 list items, decision/criteria hd, format/schema hd -> manual review: Persona Traits + Core Mission are reasoning; Style Guide + Activation Profile are reference; mixed 50-69%
- **c3 (N/A)**: agent not invoked from any slash command (c1=No)
- **c4 (Unknown)**: agent emits prose/advisory output; no structured artifact for bots to validate against schema; no PR-history signal possible
- **c5_frontmatter_bytes**: 467 (full body: 8258)
- **has_shared_template**: Yes
- **verdict_rationale**: discriminator_score=0/4; below 2-of-4 threshold; no shape mismatch detected

## Summary

- **Authority** (per AC-9): this audit applies ADR-030 (Skills Pattern Superiority, discriminator foundation), ADR-036 (Two-Source Agent Template Architecture, `has_shared_template` column source), and `.agents/governance/agent-consolidation-process.md` (existing overlap-analysis matrix and recommendation thresholds).
- **Total agents audited**: 23 (matches `ls .claude/agents/*.md | grep -v -E '(AGENTS|CLAUDE)\.md' | wc -l`)
- **Verdict counts**:
  - `skill`: 8
  - `context-fork-skill`: 2
  - `keep-as-agent`: 13
  - `merge-into-X`: 0 (not assessed in Phase 1; deferred to Phase 2 with overlap analysis per `agent-consolidation-process.md`)
- **Load-budget impact**: total frontmatter bytes = 10979; bytes saved if all `skill`+`context-fork-skill` rows migrate = **5186 (47% of always-loaded portion)**.
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

- **`roadmap`** -> `skill`
  - Target: `.claude/skills/roadmap/SKILL.md`
  - Justification: discriminator_score=3/4 (c1=1, c2=1, c3=1, c4=0); 2-of-4 rule fires; no isolation requirement documented (strategic alignment, not separate-context reasoning)
  - Refactor must update: `.claude/agents/roadmap.md` (delete or thin shim), `templates/agents/roadmap.shared.md` (per ADR-036)

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

## Out of scope (per PRD section 9)

- Phase 2 refactor PRs (one per skill candidate above). Each is a separately filed issue per `phase_2_3_governance: separate-issues`.
- Phase 3 CI check implementation. See linked stub issue #2008.
- 24th `caveman` agent under `~/.claude/`. Not in `.claude/agents/`.
- Downstream platform variants under `src/copilot-cli/agents/` and `src/vs-code-agents/`.
- Quantitative ranking via `eval-knowledge-integration.py` / `eval-skill-overlap.py` (#1932). Deferred to Phase 2.
- `merge-into-X` verdicts (require pairwise overlap analysis; deferred to Phase 2).

## Notes

### c4 (schema-drift) confidence

Only `spec-generator` scored Yes on c4 (documented in #2001 with PR #1995 evidence). Other structured-output agents (`adr-generator`, `milestone-planner`, `task-decomposer`, `backlog-generator`, `explainer`, `skillbook`, `memory`, `context-retrieval`) were marked No conservatively after PR-history search returned no comparable schema-drift threads. **Phase 2 reviewers should re-examine c4 if a structured-output agent has produced schema drift since 2026-05-10**: a single drift incident moves the verdict from `keep-as-agent` to `skill` for several of these.

### c2 (reference vs reasoning) heuristic limitation

The automated heuristic (lines counted: tables + lists + headings + code blocks) over-estimated reference content for reasoning-focused agents. Manual deflation applied to: `critic`, `independent-thinker`, `high-level-advisor`. `analyst` was kept at >=70% (genuine decision-table dominance). Per PRD section 11 lock-in, only decision-tree bullets count, not all bullets. Reviewers may rebalance individual c2 scores; the c2 column documents the count.

### Determinism scope

NFR-1 in REQ-011 says re-runs produce byte-identical output for c1, c4, c5, has_shared_template, and c3. **c2 is human-judgment and MAY vary between reviewers** (per PRD section 11). Verdict can change for borderline agents whose discriminator_score depends on c2; this is an explicit limitation of the count rule, not a determinism failure.

### Isolation classification (hard vs soft)

This audit introduces a `hard` vs `soft` isolation distinction (see "Verdict rule" above) to reconcile three previously-divergent rules in PRD AC-6, DESIGN-011 section C3, and the audit's own rule. `hard` isolation maps to `keep-as-agent` regardless of discriminator_score (the agent's function depends on NOT seeing parent context). `soft` isolation maps to `context-fork-skill` when score >= 2 (fork creates a sub-context; the agent benefits but does not require asymmetry). DESIGN-011 section C3 was updated in the round-2 commit to encode the hard/soft split explicitly.

### c1 detection method (round-3 update)

A round-2 review (cursor on this PR) noted that `roadmap` was scored c1=No despite being invoked from `.claude/commands/review.md:32`. Root cause: the original c1 grep matched only literal forms like `Task(subagent_type="agent")`; review.md uses a descriptive form `Task(subagent_type=...) agent (analyst, architect, qa, security, devops, roadmap)` where the agent name appears in a parenthesized list, not in the Task() call literal. The c1 method now also detects descriptive forms; `roadmap` re-scored as c1=Yes (with c3=Yes via review.md siblings code-qualities-assessment / golden-principles / taste-lints), bringing its score to 3/4 and verdict to `skill`. No other agents were affected (the other 5 agents in the same descriptive list already had c1=Yes via literal matches elsewhere).

### Phase 3 CI check

Per PRD AC-12 + issue #2003 acceptance criterion 4, the Phase 3 CI check (detect new agents matching skill discriminator) is filed as a separate stub issue: **#2008**.

### `keep-as-agent` agents that are never invoked from slash commands (c1=No)

Several agents (`adr-generator`, `backlog-generator`, `explainer`, `issue-feature-review`, `quality-auditor`, `skillbook`, `high-level-advisor`, `independent-thinker`, `memory`) scored c1=0 and are kept-as-agent by the rule. **A separate triage** (not in #2003 scope) should evaluate whether these are dead code, peer-only invocations, or genuine but undiscoverable agents. Recommend filing a follow-up issue if invocation counts from session logs show <5% usage per `agent-consolidation-process.md` trigger.

### Validation

This audit's REQ-011 / DESIGN-011 / TASK-011 frontmatter was validated against `.agents/governance/spec-schemas.md` before commit (the very anti-pattern this audit addresses). spec-schemas was read before write; no enum drift introduced.
