# Issue #2003 Phase 2: Claude 4.7 Prompt Discipline Audit

> Phase 2 of Issue #2003. Phase 1 (PRD/DESIGN-011/REQ-011/TASK-011) shipped in PR #2009, merged 2026-05-15. This document is the consolidated Phase 2 audit deliverable. No rewrites are bundled. Triage and rewrite scope live in a separate follow-up (Phase 3).

Date: 2026-05-25
Branch: `feat/2003-phase2-prompt-discipline-audit`
Rubric source: `~/Documents/Obsidian Vault/wiki/concepts/AI Productivity/Claude 4.7 Prompting Discipline.md`
Audit scope: 73 files (26 prompts, 25 agents, 18 templates, 4 instructions)
Audit method: 7-axis rubric (see Section 1). Per-file scores with file:line citations on axes scoring 1-2.

## Executive summary

### Tier distribution across all 73 files

| Surface | Files | A | B | C | D | F |
|---|---|---|---|---|---|---|
| `.github/prompts/*.md` | 26 | 0 | 7 | 18 | 0 | 1 |
| `.github/agents/*.md` | 25 | 0 | 16 | 6 | 3 | 0 |
| `templates/agents/*.shared.md` | 18 | 0 | 6 | 12 | 0 | 0 |
| `.github/instructions/*.md` | 4 | 0 | 0 | 0 | 4 | 0 |
| **Total** | **73** | **0** | **29** | **36** | **7** | **1** |

Zero A-tier files. Ceiling is B (best files: `orchestrator.agent.md`, `qa.agent.md`, `implementer.agent.md` all at 31/35).

### Cross-cutting weakest axes (codebase-wide)

| Axis | Prompts avg | Agents avg | Templates avg | Diagnosis |
|---|---|---|---|---|
| A6 Reasoning depth | 2.58 | 3.40 | 2.17 | No file invokes "think before answering" or extended-thinking on high-stakes reasoning. Zero of 18 templates carry an explicit reasoning-depth directive. |
| A5 Tool use directive | 2.54 | 3.04 | 3.44 | Tool inventories live in frontmatter; no prose directive ("search first, verify, do not rely on memory") matched to task type. |
| A2 Length calibration | 2.50 | 3.60 | 3.39 | No prose-producing prompt sets a word, bullet, or section cap. `pr-review.prompt.md` is 365 lines with no length bound on agent output. |

These three axes are the systemic deficit. Fixing them on the high-leverage templates would cascade across every workflow.

### Rewrite priority (top 10, ranked by fix-leverage not raw score)

1. `templates/agents/orchestrator.shared.md` (27/35, B). Top of the call graph; every multi-step workflow routes through it. Add A6 reasoning directive, cap A2 phase response length.
2. `templates/agents/implementer.shared.md` (27/35, B). Every code-change workflow. Add A6 "think before edit" on plan-validation.
3. `templates/agents/critic.shared.md` (26/35, B). Every plan validation. Add A6 plus A5 (read related ADRs before judging).
4. `templates/agents/security.shared.md` (26/35, B). Threat modeling without "think first" on a high-stakes reasoning task.
5. `templates/agents/qa.shared.md` (25/35, C). Every test strategy. Add A6 plus coverage tool directive.
6. `templates/agents/analyst.shared.md` (25/35, C). Every research task. Add A5 "search before claiming".
7. `templates/agents/architect.shared.md` (25/35, C). Every ADR. Add A6 plus ADR-precedent search.
8. `.github/prompts/pr-quality.*.prompt.md` (21/30 each, C, 7 files). Local wrappers are clones; one template fix lifts seven files.
9. `.github/prompts/default-ai-review.md` (11/30, F). The only F-tier file. Stub with no shape, no order, no boundaries.
10. `.github/agents/code-simplifier.agent.md` (15/35, D), `comment-analyzer.agent.md` (17/35, D), `pr-test-analyzer.agent.md` (18/35, D). Three freestanding D-tier agents with no handoff contract.

### Systemic findings (cross-report consolidation)

1. **Two-tier agent codebase.** Eighteen template-derived agents carry Handoff Protocol, named handoff targets, and completion criteria. Six freestanding agents (`code-reviewer`, `code-simplifier`, `comment-analyzer`, `pr-test-analyzer`, `type-design-analyzer`, `silent-failure-hunter`) lack any handoff, completion criteria, or failure-mode contract. Pre-template legacy that never got reconciled.
2. **All 18 templates use foggy "I need" / "help me" framing in the Summon block.** Grep-confirmed 18 of 18. The body sections recover with shipping verbs (delegate, score, validate, extract), but the most prominent paragraph of every template is the weakest sentence in the file.
3. **28 em-dash hits across 14 templates violate the file's own "No em dashes" Style Guide Compliance rule.** Heaviest: `orchestrator.shared.md` (7), `pr-comment-responder.shared.md` (8 counting `→`-style arrows), `critic.shared.md` (3). The Generate-Agents pipeline propagates these to generated outputs.
4. **Banned vocab is rare but present.** `comprehensive` hits 5 times (planner, implementer, qa templates) in descriptive prose, not load-bearing instruction lines.
5. **`pr-quality.*.prompt.md` cloning.** Seven local wrappers are structural clones with identical A2=2 / A6=2 deficits. Single template fix lifts seven files.
6. **`.github/instructions/*.md` are pointer stubs.** All four score D, all four punt to `.agents/steering/*.md`. Fixing the stubs is low leverage; canonical content lives in steering docs (separate audit scope).
7. **Interrogative-style sections substitute for shipping verbs in 4 quality-gate files.** `pr-quality-gate-{analyst,architect,roadmap,devops}.md` open sections with "Does X?" instead of imperative "Extract X". Security and qa gates do better because they list explicit FAIL-criteria tables.

### Generation cascade

Per ADR-036, every `templates/agents/*.shared.md` fix cascades to up to three downstream files via `python3 build/generate_agents.py`:

- `src/vs-code-agents/*.agent.md` (generated)
- `src/copilot-cli/*.agent.md` (generated)
- `src/claude/*.md` (hand-maintained, content-identical per ADR-036)

The 18-template rewrite scope therefore translates to roughly 54 effective downstream files.

### Phase 3 decisions (ACTIVE as of 2026-05-26)

Phase 3 is now active. Decisions from the four open questions are answered below.

**Answered decisions:**

1. **Scope.** Rewrite the top-10 priority list (top-7 leverage templates plus D/F files). B-tier-to-A pass across all 73 files deferred to Phase 4.
2. **Sequencing.** Template-first (auto-cascades via `python3 build/generate_agents.py`). Quick wins (pr-quality clones, default-ai-review) in the same pass since they share the A2/A6 deficit pattern.
3. **Verification.** Offline rubric rescore (target 32+/35 for agent/template files, 27+/30 for prompt files) plus `python3 scripts/validation/pre_pr.py` plus `python3 build/generate_agents.py` round-trip per PR. CI gate (skill discriminator) deferred; not implemented.
4. **Owner.** Autonomous subagent (one PR per target). Human review via PR before merge. Templates touch the call graph and must go through full PR review.

## Discipline self-check (this document)

- Zero em-dashes in the executive summary above (period, comma, colon, semicolon, parenthesis used instead). Source reports in sections 1-4 preserve their original em-dash usage where authors chose it.
- Banned vocab scan on the executive summary: zero hits for `crucial`, `comprehensive`, `delve`, `robust`, `multifaceted`, `foster`, `showcase`, `underscore`, `tapestry`, `vibrant`, `pivotal`, `leverage` (as verb).
- File:line citations preserved from source reports where axes scored 1-2.

---

## Section 1: The audit rubric

# Claude 4.7 Prompt Audit Rubric

Apply this to each canonical prompt file in `~/src/GitHub/rjmurillo/ai-agents/`. Score each file across 7 axes (1-5 scale, 5 = fully meets discipline, 1 = severely violates). Total score / 35 = the file's grade.

## Files to audit (69 total)

- `.github/prompts/*.md` (26 files, 3144 LOC)
- `.github/agents/*.md` (25 files, 12012 LOC)
- `.github/instructions/*.md` (4 files, 158 LOC)
- `templates/agents/*.shared.md` (18 files, 11428 LOC, SOURCE OF TRUTH; generates src/claude, src/copilot-cli, src/vs-code-agents)

DO NOT audit:
- `worktrees/**` (transient feature branches; not canonical)
- `src/claude/**`, `src/copilot-cli/**`, `src/vs-code-agents/**` (GENERATED from templates/agents/; fixing templates auto-fixes these via `python3 build/generate_agents.py`)

## The 7 axes

### Axis 1: Output specification (1-5)

Does the prompt name the output shape (table, JSON, markdown, code, memo, checklist, before/after, etc.) AND order (what comes first, second, third) AND boundaries (what to skip / assume / ask first)?

- 5: All three (shape + order + boundaries) explicit
- 3: Shape named, order or boundaries missing
- 1: "Review", "help with", "look at" with no shape

### Axis 2: Length and complexity calibration (1-5)

Does the prompt bound output length explicitly OR explicitly invite elaboration ("Go beyond the basics") when appropriate?

- 5: Length bounded (word count, bullet count, section count) OR explicit elaboration directive matched to task type
- 3: Implicit length guidance only ("brief", "detailed")
- 1: No length signal; relies on model defaulting

### Axis 3: Positive over negative instructions (1-5)

Are constraints framed as "do X" rather than "don't do Y" for stylistic/quality dimensions? (Safety negatives like "do not send actual emails" are EXEMPT and do not penalize.)

- 5: All stylistic constraints positive; only safety constraints negative
- 3: Mixed; some stylistic negatives present
- 1: Predominantly "don't" / "avoid" / "never" for stylistic dimensions without positive counterparts

### Axis 4: Shipping verbs (1-5)

Does the prompt use deliverable-producing verbs (extract, rank, rewrite, diagnose, decide, draft, verify, score, compress, format, ship, classify) rather than activity-describing verbs (help, think about, look at, handle, improve, make better)?

- 5: Predominantly shipping verbs throughout
- 3: Mixed; foggy verbs in non-critical positions
- 1: Predominantly foggy verbs; reader cannot tell what artifact is supposed to ship

### Axis 5: Tool use directive (1-5)

For prompts where tool use is relevant (research, agent, verification, freshness-sensitive): does the prompt explicitly direct tool use ("search first, then answer", "verify every major claim with at least 2 sources", "do not rely on memory for factual claims") OR explicitly suppress it ("do not use web search; answer from context")?

- 5: Explicit tool directive that matches task type
- 3: Implicit tool guidance only
- 1: No tool directive on a task where tool use matters
- N/A: Tool use is irrelevant to this prompt (e.g., pure formatting transformation)

### Axis 6: Reasoning depth signaling (1-5)

For prompts requiring multi-step reasoning (strategy, debugging, code review, security analysis, architecture, decision-making): does the prompt explicitly invoke think-before-answering OR adaptive reasoning?

- 5: Explicit reasoning directive matched to task complexity
- 3: Implicit reasoning signal (e.g., "carefully analyze")
- 1: No reasoning directive on a high-stakes reasoning task
- N/A: Trivial transformation, no reasoning required

### Axis 7: Agent-specific dimensions (1-5)

For agent prompts (.github/agents/, templates/agents/) ONLY: does the prompt specify (a) delegation protocol, (b) quality gates / completion criteria, (c) failure modes, (d) inter-agent contract for output shape?

- 5: All four dimensions explicit
- 3: Two or three present
- 1: Zero or one present; agent is operating on implicit contract
- N/A: Not an agent prompt (skip for `.github/prompts/`, `.github/instructions/`)

## Per-file output format

For each file, emit one row of:

```
| File | Axis1 | Axis2 | Axis3 | Axis4 | Axis5 | Axis6 | Axis7 | Total | Tier |
```

Tier:
- **A (32-35)**: Production-ready. Skim for nits, no major rewrites.
- **B (26-31)**: Solid. Targeted improvements possible but not urgent.
- **C (20-25)**: Real gaps. Worth a rewrite pass.
- **D (14-19)**: Significant deficit. Rewrite priority.
- **F (<14)**: Severely under-specified. Highest-priority rewrites.

For axes scored 1-2, include a one-line citation: file:line and the offending phrase.

## Top-level output

After per-file rows:

### Summary stats

- Counts per tier
- Average score per axis (which axes are systematically weak across the codebase?)
- 10 worst-scoring files (rewrite-priority list)
- 10 best-scoring files (use as templates for the rewrites)

### Systemic findings

Patterns observed across the codebase, e.g.:
- "All 18 templates/agents/*.shared.md use 'help' as the primary verb in their identity statement"
- "Zero of 26 .github/prompts files specify output order"
- "Agent prompts uniformly miss failure-mode specification"

### Rewrite priority list

A ranked list of files to fix first, with a 1-line justification each.

## Reference

Audit rubric is the operationalization of `~/Documents/Obsidian Vault/wiki/concepts/AI Productivity/Claude 4.7 Prompting Discipline.md`. The 5 load-bearing disciplines + the painfully-literal floor + agent-specific extensions in that page are the spec; this rubric is the measurement instrument.

## Discipline reminders

- Zero em-dashes in the report (period, comma, colon, semicolon, parenthesis instead)
- No banned vocab: crucial, comprehensive, delve, robust, multifaceted, foster, showcase, underscore, tapestry, vibrant, pivotal, leverage-as-verb
- Be specific. Cite file:line for low scores.
- Do NOT manufacture findings to look thorough; if a file scores well, say so.
- Do NOT speculate about authorial intent; score what the text actually says.


---

## Section 2: Report on `.github/prompts/*.md` (26 files)

# Audit Report: `.github/prompts/*.md` (26 files)

Rubric: `/tmp/ai-agents-audit-rubric.md`. Axes 1-6 scored (Axis 7 N/A: these are prompts, not agent definitions). Total /30. Tier bands: A=27-30, B=22-26, C=17-21, D=12-16, F<12.

## Per-file scores

| File | A1 | A2 | A3 | A4 | A5 | A6 | Total | Tier |
|------|----|----|----|----|----|----|------|------|
| pr-quality.all.prompt.md | 5 | 2 | 5 | 4 | 3 | 2 | 21 | C |
| pr-quality.analyst.prompt.md | 5 | 2 | 5 | 4 | 3 | 2 | 21 | C |
| pr-quality.architect.prompt.md | 5 | 2 | 5 | 4 | 3 | 2 | 21 | C |
| pr-quality.devops.prompt.md | 5 | 2 | 5 | 4 | 3 | 2 | 21 | C |
| pr-quality.qa.prompt.md | 5 | 2 | 5 | 4 | 3 | 2 | 21 | C |
| pr-quality.roadmap.prompt.md | 5 | 2 | 5 | 4 | 3 | 2 | 21 | C |
| pr-quality.security.prompt.md | 5 | 2 | 5 | 4 | 3 | 2 | 21 | C |
| default-ai-review.md | 2 | 1 | 4 | 2 | 1 | 1 | 11 | F |
| pr-quality-gate-security.md | 5 | 2 | 4 | 4 | 2 | 3 | 20 | C |
| pr-quality-gate-qa.md | 5 | 3 | 3 | 4 | 2 | 3 | 20 | C |
| pr-quality-gate-analyst.md | 4 | 2 | 4 | 3 | 2 | 2 | 17 | C |
| pr-quality-gate-architect.md | 4 | 2 | 4 | 3 | 2 | 3 | 18 | C |
| pr-quality-gate-devops.md | 5 | 3 | 4 | 4 | 2 | 3 | 21 | C |
| pr-quality-gate-roadmap.md | 4 | 2 | 5 | 3 | 2 | 2 | 18 | C |
| issue-prd-generation.md | 5 | 3 | 4 | 4 | 4 | 3 | 23 | B |
| issue-feature-review.md | 5 | 3 | 3 | 4 | 4 | 3 | 22 | B |
| issue-triage-categorize.md | 5 | 4 | 5 | 4 | 2 | 2 | 22 | B |
| issue-triage-roadmap.md | 5 | 4 | 5 | 4 | 2 | 3 | 23 | B |
| spec-check-completeness.md | 5 | 2 | 4 | 4 | 2 | 3 | 20 | C |
| spec-trace-requirements.md | 5 | 2 | 4 | 4 | 2 | 3 | 20 | C |
| session-protocol-check.md | 5 | 3 | 4 | 4 | 2 | 2 | 20 | C |
| merge-conflict-analysis.md | 5 | 4 | 2 | 4 | 2 | 3 | 20 | C |
| pr-comment-triage.md | 5 | 4 | 4 | 4 | 2 | 3 | 22 | B |
| copilot-synthesis.md | 5 | 3 | 4 | 4 | 3 | 3 | 22 | B |
| pr-review.prompt.md | 4 | 2 | 4 | 4 | 4 | 5 | 23 | B |
| review-pr.prompt.md | 3 | 2 | 4 | 3 | 3 | 3 | 18 | C |

### Low-score citations (A1-A6 scores of 1-2)

- default-ai-review.md A1=2, A2=1, A4=2, A5=1, A6=1. line 5 "Analyze the provided context and give your assessment." Stub with no shape, no order, no length, no verbs, no tool/reasoning directives.
- pr-quality.{all,analyst,architect,devops,qa,roadmap,security}.prompt.md A2=2, A6=2. none of the 7 wrappers bound length or invoke think-before-answer; e.g., pr-quality.security.prompt.md:24-29 lists 4 imperatives with no length cap and no reasoning directive on an OWASP review task.
- pr-quality-gate-security.md A5=2. line 39-48 lists regex patterns for secret detection but never directs "verify each finding against the diff" or "do not rely on memory for CVE claims".
- pr-quality-gate-qa.md A3=3, A5=2. heavy "FAIL if" framing (lines 67-73 "Errors are silently swallowed", "Generic exceptions hide", "User-facing error messages expose internals") instead of positive equivalents.
- pr-quality-gate-analyst.md A4=3, A5=2, A6=2. line 7-11 "Readability: Is the code easy to understand? Maintainability: Will this be easy to modify?" Soft questions, no shipping verb, no reasoning directive on a code-quality task.
- pr-quality-gate-architect.md A4=3, A5=2. line 6-9 "Does the change follow established design patterns". interrogative format throughout; reader infers but is not told what artifact to ship for each section.
- pr-quality-gate-roadmap.md A4=3, A5=2, A6=2. line 6-9 "Does this change align with the project's stated goals?" Pure interrogative on a strategy-alignment task that needs reasoning.
- pr-quality-gate-devops.md A5=2. no directive to verify action versions against GitHub Marketplace or run `actionlint`.
- spec-check-completeness.md A2=2, A5=2. line 5-8 "Extract all acceptance criteria... Check if the implementation satisfies each criterion" with no length cap and no tool directive (e.g., grep for REQ-IDs).
- spec-trace-requirements.md A2=2, A5=2. same shape as completeness check; no tool directive on a traceability task.
- session-protocol-check.md A5=2, A6=2. strict output but no reasoning directive on RFC-2119 compliance checking.
- merge-conflict-analysis.md A3=2. lines 6-10 are five consecutive "DO NOT" directives ("DO NOT include any text before the JSON", "DO NOT include any text after", "DO NOT wrap JSON in markdown code fences", "DO NOT explain your reasoning outside the JSON") with no positive counterpart ("Start with `{`, end with `}`" appears once at line 10 but is overwhelmed by the negatives).
- pr-comment-triage.md A5=2. no directive to fetch comment context via `gh api` when comment body is truncated.
- copilot-synthesis.md A2=3 acceptable but A5=3 implicit only.
- pr-review.prompt.md A2=2. 365-line prompt with no length bound on agent output.
- review-pr.prompt.md A1=3, A4=3, A2=2. line 30 "Run a comprehensive pull request review using multiple specialized agents" but output shape is not named; "comprehensive" + soft verbs.

## Tier distribution

- A (27-30): 0
- B (22-26): 7 (issue-prd-generation, issue-triage-roadmap, pr-review.prompt, issue-feature-review, issue-triage-categorize, pr-comment-triage, copilot-synthesis)
- C (17-21): 18
- D (12-16): 0
- F (<12): 1 (default-ai-review)

## Average score per axis

| Axis | Mean | Rank |
|------|------|------|
| A1 Output spec | 4.65 | strongest |
| A3 Positive framing | 4.04 | |
| A4 Shipping verbs | 3.77 | |
| A6 Reasoning depth | 2.58 | |
| A5 Tool use directive | 2.54 | |
| A2 Length calibration | 2.50 | weakest |

Weakest axes are A2, A5, A6. The codebase ships output schemas well but does not bound length, does not direct tool use, and does not invoke explicit reasoning depth on multi-step tasks.

## Top 5 worst-scoring (rewrite priority)

1. **default-ai-review.md (11, F)**. stub with no shape, no order, no boundaries; "give your assessment" is the entire task statement.
2. **pr-quality-gate-analyst.md (17, C)**. interrogative format throughout; no PR-type detection table (unlike security/qa/devops siblings); soft verbs.
3. **pr-quality-gate-architect.md (18, C)**. same pattern as analyst, no PR-type detection, no tool/reasoning directives on architecture review.
4. **pr-quality-gate-roadmap.md (18, C)**. soft "Does this align" interrogatives; no tool directive on a strategy task that should reference roadmap docs.
5. **review-pr.prompt.md (18, C)**. front-matter heavy, output shape under-specified, soft verbs in workflow steps.

## Top 5 best-scoring (use as templates)

1. **issue-prd-generation.md (23, B)**. explicit shape with section list, escalation table, research/source directive, status emojis define output order.
2. **issue-triage-roadmap.md (23, B)**. priority matrix, decision table, JSON shape, escalation criteria all explicit; tight numbered rules.
3. **pr-review.prompt.md (23, B)**. only file invoking explicit reasoning depth ("ultrathink"); strong workflow ordering; explicit tool list in front-matter.
4. **issue-feature-review.md (22, B)**. context limitations explicit ("You do NOT have access to..."), evaluation framework table, quality checklist; honest about unknowns.
5. **issue-triage-categorize.md (22, B)**. strict JSON-only output, label taxonomy, numbered rules; "Respond with ONLY valid JSON" is a clean boundary directive.

## Systemic findings

1. **The 7 `pr-quality.*.prompt.md` local wrappers are clones at 21/30.** They share identical structure (`{{file}}` include + 5 numbered "Instructions" + JSON output schema) and all have the same A2=2, A6=2 deficits. A single template fix (add length cap, add reasoning directive) lifts seven files at once. `pr-quality.all.prompt.md` is the meta-wrapper and inherits the same gap.

2. **Length calibration (A2) is the single weakest discipline: 23 of 26 files score 2 or 3.** Only `issue-triage-*` (4) and `pr-comment-triage`, `merge-conflict-analysis` (4) bound output meaningfully (JSON-only). No prose-producing prompt sets a word, bullet, or section cap. The 365-line `pr-review.prompt.md` produces unbounded agent output by construction.

3. **Tool-use directives (A5) absent on verification-heavy tasks: 13 of 26 files score 2.** Security review never says "verify CVE claims against NVD". Spec-trace never says "grep for REQ-IDs across changed files". Architect review never says "consult `.agents/architecture/` ADRs". Only `pr-review.prompt.md`, `issue-prd-generation.md`, `issue-feature-review.md` give explicit research/tool guidance.

4. **Reasoning depth (A6) absent on high-stakes reasoning tasks: 11 files score 2.** Security and architect quality gates are the most reasoning-heavy tasks in the set and score A6=2-3. Only `pr-review.prompt.md` uses the explicit `ultrathink` token. No prompt invokes "think step by step before producing the JSON".

5. **Interrogative-style sections substitute for shipping verbs in 4 quality-gate files.** `pr-quality-gate-{analyst,architect,roadmap,devops}.md` open sections with "Does X?" / "Are Y?" questions instead of imperative "Extract X" / "Rank Y". The security and qa gates do better because they list explicit FAIL-criteria tables. The interrogative four also lack the PR-type detection table that anchors the imperative two.

6. **Negative framing concentrated in JSON-only prompts.** `merge-conflict-analysis.md:6-10` and `pr-comment-triage.md:38-40` use 4-5 consecutive "DO NOT" lines around output format. The positive recast ("First character must be `{`, last character must be `}`") appears but is buried.

7. **No prompt scores tier A.** The ceiling across 26 files is 23/30. The gap to A (27+) is closeable on A2 and A6 alone: bound length and add a reasoning directive to the seven clones plus the seven gate criteria files and the average tier shifts from C to B.


---

## Section 3: Report on `.github/agents/*.md` (25 files)

# Audit: `.github/agents/*.md` (25 files)

Rubric: `/tmp/ai-agents-audit-rubric.md`. All 7 axes scored (these are agent prompts). Scale 1-5; total /35.

## Per-file scores

| File | A1 | A2 | A3 | A4 | A5 | A6 | A7 | Total | Tier |
|------|----|----|----|----|----|----|----|------:|------|
| orchestrator.agent.md | 5 | 4 | 4 | 5 | 4 | 4 | 5 | 31 | B |
| qa.agent.md | 5 | 4 | 4 | 5 | 4 | 4 | 5 | 31 | B |
| implementer.agent.md | 5 | 4 | 4 | 5 | 4 | 4 | 5 | 31 | B |
| critic.agent.md | 5 | 4 | 4 | 5 | 3 | 4 | 5 | 30 | B |
| planner.agent.md | 5 | 4 | 4 | 5 | 3 | 4 | 5 | 30 | B |
| security.agent.md | 5 | 4 | 4 | 5 | 4 | 4 | 4 | 30 | B |
| architect.agent.md | 5 | 4 | 4 | 5 | 3 | 4 | 5 | 30 | B |
| retrospective.agent.md | 5 | 4 | 4 | 5 | 3 | 4 | 4 | 29 | B |
| task-generator.agent.md | 5 | 4 | 4 | 5 | 3 | 3 | 5 | 29 | B |
| skillbook.agent.md | 5 | 4 | 4 | 5 | 3 | 3 | 5 | 29 | B |
| analyst.agent.md | 4 | 4 | 4 | 5 | 4 | 4 | 4 | 29 | B |
| memory.agent.md | 4 | 4 | 4 | 5 | 4 | 3 | 4 | 28 | B |
| devops.agent.md | 4 | 4 | 4 | 5 | 4 | 3 | 4 | 28 | B |
| roadmap.agent.md | 4 | 4 | 4 | 5 | 3 | 3 | 4 | 27 | B |
| pr-comment-responder.agent.md | 4 | 4 | 4 | 5 | 3 | 3 | 4 | 27 | B |
| pr-comment-responder.prompt.md | 4 | 4 | 4 | 5 | 3 | 3 | 4 | 27 | B |
| explainer.agent.md | 4 | 3 | 4 | 4 | 3 | 3 | 4 | 25 | C |
| high-level-advisor.agent.md | 4 | 3 | 4 | 4 | 3 | 4 | 3 | 25 | C |
| independent-thinker.agent.md | 4 | 3 | 4 | 4 | 3 | 4 | 3 | 25 | C |
| silent-failure-hunter.agent.md | 4 | 3 | 3 | 4 | 3 | 3 | 2 | 22 | C |
| code-reviewer.agent.md | 4 | 3 | 3 | 4 | 2 | 3 | 1 | 20 | C |
| type-design-analyzer.agent.md | 4 | 3 | 3 | 4 | 2 | 3 | 1 | 20 | C |
| pr-test-analyzer.agent.md | 3 | 3 | 2 | 4 | 2 | 3 | 1 | 18 | D |
| comment-analyzer.agent.md | 3 | 3 | 2 | 3 | 2 | 3 | 1 | 17 | D |
| code-simplifier.agent.md | 3 | 2 | 2 | 3 | 2 | 2 | 1 | 15 | D |

### Low-score citations (axes 1-2)

- `code-simplifier.agent.md:line ~95` Axis 2=2: no length bounds, no elaboration directive; "refining code immediately after it's written" with no shape budget.
- `code-simplifier.agent.md:line ~70` Axis 6=2: high-stakes refactoring task with only "Analyze for opportunities" (foggy verb, no reasoning directive).
- `comment-analyzer.agent.md:line ~78` Axis 3=2: stylistic negatives ("never modify", "avoid comments that...", "should be flagged for removal") without positive counterparts.
- `pr-test-analyzer.agent.md:line ~62` Axis 3=2: "Avoid suggesting tests for trivial getters/setters", "Avoid being overly pedantic" framed negatively.
- `code-reviewer.agent.md:line ~58` Axis 5=2: review task with no tool directive ("git diff" mentioned once but no "verify each finding by reading the file" directive). A7=1: no handoff, no failure modes, no inter-agent contract; freestanding prompt.
- `type-design-analyzer.agent.md:line ~5` Axis 5=2 / A7=1: no tool directive, no handoff/delegation/failure-mode block.
- `silent-failure-hunter.agent.md` A7=2: failure-handling philosophy present but no handoff target, no completion criteria, no return-to-orchestrator contract.
- `pr-test-analyzer.agent.md` A1=3: output shape listed but no length bound and no skip/boundary rules.
- `comment-analyzer.agent.md` A4=3: mixes shipping verbs ("flag", "rewrite") with foggy ones ("evaluate", "assess", "consider").
- `code-simplifier.agent.md` A4=3: predominantly foggy ("refine", "enhance", "maintain balance", "ensure"); reader cannot tell what artifact ships (a diff? a rewrite? a list of suggestions?).
- `code-simplifier.agent.md` A1=3: no output shape named; just "refine code".

## Tier distribution

- A (32-35): 0
- B (26-31): 16
- C (20-25): 6
- D (14-19): 3
- F (<14): 0

## Average per-axis

- A1 Output spec: 4.28
- A2 Length: 3.60
- A3 Positive framing: 3.64
- A4 Shipping verbs: 4.56
- A5 Tool directive: 3.04
- A6 Reasoning depth: 3.40
- A7 Agent contract: 3.56

Weakest axes across the codebase: A5 (tool directive) and A6 (reasoning depth). A2 (length) is also systemically light.

## Worst 5

1. `code-simplifier.agent.md` (15, D): no output shape, no length bound, foggy verbs ("refine", "enhance"), no delegation contract.
2. `comment-analyzer.agent.md` (17, D): predominantly negative framing, no tool directive, no inter-agent handoff.
3. `pr-test-analyzer.agent.md` (18, D): rating scheme present but no length cap, no tool directive, zero Axis 7.
4. `code-reviewer.agent.md` (20, C): confidence-scored output is good but A7=1 (no handoff, no failure mode, no completion criteria).
5. `type-design-analyzer.agent.md` (20, C): clean rating template but isolated; no delegation, no failure handling, no quality gate.

## Best 5

1. `orchestrator.agent.md` (31, B): full delegation protocol, failure modes, completion criteria, handoff contract.
2. `qa.agent.md` (31, B): explicit Pre-PR Quality Gate, APPROVED/BLOCKED verdict, three named handoff destinations with validation checklists.
3. `implementer.agent.md` (31, B): plan-as-authoritative contract, quantified quality gates (cyclomatic <=10, methods <=60 lines), commit protocol.
4. `critic.agent.md` (30, B): explicit verdict format, review checklist, completeness gates.
5. `security.agent.md` (30, B): numeric risk scores (CVSS), CWE/CVE evidence requirement, severity classification, handoff protocol.

## Systemic findings

### Axis 7 (agent contract)

1. **Two-tier codebase.** Templates-derived agents (planner, qa, orchestrator, implementer, critic, security, architect, retrospective, task-generator, skillbook, devops, roadmap, analyst, memory, pr-comment-responder, explainer, high-level-advisor, independent-thinker) consistently include a Handoff Protocol section, named handoff targets, and a "subagents cannot delegate" inter-agent invariant. The 6 freestanding agents (`code-reviewer`, `code-simplifier`, `comment-analyzer`, `pr-test-analyzer`, `type-design-analyzer`, `silent-failure-hunter`) lack any handoff, completion criteria, or failure-mode contract. They look like first-generation Claude Code agent stubs that never got reconciled with the template structure.

2. **Quality gates are uneven.** `qa.agent.md` and `implementer.agent.md` define numeric thresholds and APPROVED/BLOCKED verdicts. Most others define a verdict shape (e.g., architect's ADR, critic's checklist) but no measurable pass/fail threshold. The 6 freestanding agents define no quality gate at all; `code-reviewer.agent.md` comes closest with its confidence>=80 threshold.

3. **Failure modes mostly absent outside orchestrator and retrospective.** `orchestrator.agent.md` explicitly enumerates failure modes; `retrospective.agent.md` operationalizes Five Whys on failures. Other template-derived agents reference "failure" generically in handoffs without enumerating the failure taxonomy (what does silent-failure-hunter do if it finds zero issues? what does critic do if the plan is uncritiqueable?).

### Other systemic patterns

4. **Tool-directive weakness (A5 avg 3.04).** Most agents list tools in YAML frontmatter but do not direct *when* to use them ("search Serena memory before answering", "verify every claim against the file"). `analyst`, `security`, and `memory` are exceptions.

5. **Length never bounded (A2 avg 3.60).** No agent specifies a word/section cap on its primary deliverable. "Brief overview", "thorough but pragmatic", and "comprehensive" recur. The literal word "comprehensive" appears in `pr-test-analyzer.agent.md` and `qa.agent.md` (banned vocab in this audit's own rubric, but the agent files themselves were not authored against that rubric, so flagged here as a finding).

6. **Reasoning depth implicit (A6 avg 3.40).** "Carefully analyze", "think deeply", "approach with skepticism" appear, but no agent explicitly invokes extended thinking or a think-before-answering directive matched to its task complexity. Architect, critic, security, and analyst would all benefit.

7. **Negative-framing leak in older agents.** The 6 freestanding agents lean on "avoid", "never", "don't" for stylistic dimensions (`comment-analyzer`: "avoid comments that reference temporary states"; `pr-test-analyzer`: "Avoid suggesting tests for trivial getters/setters"; `code-simplifier`: "Avoid over-simplification"). Template-derived agents use positive constraints via the Style Guide Compliance block.


---

## Section 4: Report on `templates/agents/*.shared.md` and `.github/instructions/*.md` (22 files)

# Audit: templates/agents/*.shared.md and .github/instructions/*.md

Applied rubric: `/tmp/ai-agents-audit-rubric.md` (Claude 4.7 prompt discipline, 7 axes).
Repo: `~/src/GitHub/rjmurillo/ai-agents/`. Generated under: `src/vs-code-agents/`, `src/copilot-cli/`, `src/claude/` (src/claude is hand-maintained per ADR-036, but the same template content is duplicated there per the sync rule, so a template fix still cascades content-wise).

## Section 1: templates/agents/*.shared.md (18 files, /35)

Scoring legend: A=32-35, B=26-31, C=20-25, D=14-19, F<14.

| File | A1 | A2 | A3 | A4 | A5 | A6 | A7 | Total | Tier |
|---|---|---|---|---|---|---|---|---|---|
| analyst.shared.md | 4 | 3 | 4 | 4 | 4 | 2 | 4 | 25 | C |
| architect.shared.md | 4 | 3 | 4 | 4 | 4 | 2 | 4 | 25 | C |
| critic.shared.md | 4 | 4 | 4 | 5 | 3 | 2 | 4 | 26 | B |
| devops.shared.md | 4 | 3 | 4 | 4 | 4 | 2 | 4 | 25 | C |
| explainer.shared.md | 4 | 3 | 4 | 4 | 3 | 2 | 3 | 23 | C |
| high-level-advisor.shared.md | 4 | 3 | 4 | 5 | 3 | 2 | 3 | 24 | C |
| implementer.shared.md | 4 | 4 | 4 | 4 | 4 | 3 | 4 | 27 | B |
| independent-thinker.shared.md | 3 | 3 | 4 | 4 | 3 | 2 | 3 | 22 | C |
| memory.shared.md | 4 | 3 | 4 | 4 | 4 | 2 | 3 | 24 | C |
| orchestrator.shared.md | 4 | 3 | 4 | 4 | 4 | 3 | 5 | 27 | B |
| planner.shared.md | 4 | 3 | 4 | 4 | 3 | 2 | 4 | 24 | C |
| pr-comment-responder.shared.md | 4 | 4 | 4 | 4 | 4 | 2 | 4 | 26 | B |
| qa.shared.md | 4 | 4 | 4 | 4 | 3 | 2 | 4 | 25 | C |
| retrospective.shared.md | 5 | 4 | 4 | 5 | 3 | 3 | 5 | 29 | B |
| roadmap.shared.md | 4 | 4 | 4 | 5 | 3 | 2 | 3 | 25 | C |
| security.shared.md | 4 | 4 | 4 | 4 | 4 | 2 | 4 | 26 | B |
| skillbook.shared.md | 4 | 4 | 4 | 4 | 3 | 2 | 4 | 25 | C |
| task-generator.shared.md | 4 | 3 | 4 | 4 | 3 | 2 | 4 | 24 | C |

### Tier distribution (templates)

- A: 0
- B: 6 (critic, implementer, orchestrator, pr-comment-responder, retrospective, security)
- C: 12
- D: 0
- F: 0

Total: **A=0, B=6, C=12, D=0, F=0** out of 18.

### Average per-axis score (templates)

- A1 Output shape: 3.94
- A2 Length calibration: 3.39
- A3 Positive framing: 4.00
- A4 Shipping verbs: 4.22
- A5 Tool directive: 3.44
- A6 Reasoning depth: 2.17 (systemic weakness)
- A7 Agent dimensions: 3.83

### Low-axis citations (templates)

Axis 6 = 2 on 14 of 18 files. No template invokes "think before answering", "extended thinking", "think hard", or adaptive reasoning. Confirmed by grep across all 18 templates: zero hits for `think (step|carefully|hard|deep|before)|extended thinking|reasoning effort`.

- `analyst.shared.md:68` Summon paragraph uses foggy verb "Help me understand" on a research task that warrants explicit "think before answering" directive; no such directive in file.
- `architect.shared.md:46` "Challenge my technical choices if they compromise the architecture", no reasoning directive on architecture review task.
- `critic.shared.md:45` Plan stress-test task with zero reasoning directive.
- `devops.shared.md:47` CI/CD design task; no reasoning directive.
- `explainer.shared.md:43` PRD writing; no reasoning directive but lower stakes (Axis 6 = 2 still applies because INVEST validation requires reasoning).
- `high-level-advisor.shared.md:47` "Strategic advice" without explicit think-first directive.
- `independent-thinker.shared.md:53` Devil's advocate role with no extended-thinking invocation; ironic given the role.
- `memory.shared.md:46` Retrieval+reasoning task without reasoning directive.
- `planner.shared.md:46` Multi-step plan creation without reasoning directive.
- `pr-comment-responder.shared.md:56` Triage + delegation logic without reasoning directive.
- `qa.shared.md:31` Test strategy design without reasoning directive.
- `roadmap.shared.md:45` Prioritization with RICE/KANO with no reasoning directive.
- `security.shared.md:59` Threat modeling with no "think first" directive on a high-stakes reasoning task.
- `skillbook.shared.md:48` Atomicity scoring + dedup decisions without reasoning directive.
- `task-generator.shared.md:48` Decomposition without reasoning directive.

Axis 2 = 3 across most files: implicit length guidance only. "Short sentences (15-20 words)" appears in every file but governs sentence shape, not deliverable size; no bound on report length, bullet count, table row count.

- `analyst.shared.md:52` "Short sentences (15-20 words)" only; no deliverable-length cap.
- `devops.shared.md:62` same boilerplate.
- `explainer.shared.md:28` PRD task with no PRD length envelope.
- `high-level-advisor.shared.md:34` advisor verdict with no verdict length cap.
- `memory.shared.md:33` retrieval summary with no token/word envelope.
- `planner.shared.md:34` work-package with no size envelope.
- `task-generator.shared.md:34` task list with no enumeration cap.

Axis 5 = 3 on six files: tool inventories listed in frontmatter (implicit directive) but no explicit "search first, then answer" / "do not rely on memory for factual claims" prose directive matched to task.

- `critic.shared.md:88` Constraints block lists "No code review" but no positive tool-use directive.
- `explainer.shared.md:43` PRD task; tool list present in frontmatter but no instruction to verify external claims.
- `high-level-advisor.shared.md:65` No directive to verify before issuing verdict.
- `independent-thinker.shared.md:23` Contrarian role demands sources but file does not say "search before claiming"; says "Cite sources" only.
- `planner.shared.md:58` No directive to read roadmap+ADRs first as a tool-use rule (mentioned as responsibility but not enforced).
- `qa.shared.md:55` "Read roadmaps before designing tests" exists as responsibility, but no tool-use enforcement language.
- `roadmap.shared.md:53` "Investigate user pain points and success metrics actively" but no concrete tool directive.
- `skillbook.shared.md:73` dedup operation but no explicit "search existing skillbook before adding".
- `task-generator.shared.md:65` "Read PRDs and epics thoroughly" but no tool directive.

Axis 7 ≤ 3 on six files: missing one or more of {delegation protocol, completion criteria, failure modes, output contract}.

- `explainer.shared.md` no failure-mode section; no inter-agent output contract for downstream implementer/qa.
- `high-level-advisor.shared.md` no completion criteria; verdict format described but no failure-mode block.
- `independent-thinker.shared.md` advisory-only role, no inter-agent contract, no failure-mode block.
- `memory.shared.md` no failure-mode block (what if memory retrieval returns nothing usable?).
- `roadmap.shared.md` no failure mode handling; no delegation protocol back to planner spelled out.

Em-dash + banned vocab discipline (cross-cutting Axis 1/3 risk):

- 28 em-dash hits across 14 templates. Heaviest: `orchestrator.shared.md` (7), `pr-comment-responder.shared.md` (2 in body plus 8 in tables of `→`-style arrows that read as em-dashes), `critic.shared.md` (3), `retrospective.shared.md` (2), `architect.shared.md` (1 at line 46 inside the Summon paragraph, em-dash before "the architect").
- Banned vocab: "comprehensive" appears in `planner.shared.md`, `implementer.shared.md`, `qa.shared.md`. Total 5 hits. Confined to descriptive copy, not load-bearing instruction lines.

## Section 2: .github/instructions/*.md (4 files, /30)

Axis 7 N/A (instructions, not agents). Legend: A=27-30, B=22-26, C=17-21, D=12-16, F<12.

| File | A1 | A2 | A3 | A4 | A5 | A6 | Total | Tier |
|---|---|---|---|---|---|---|---|---|
| agent-prompts.instructions.md | 3 | 3 | 4 | 3 | 2 | N/A→2 | 17 | D |
| documentation.instructions.md | 3 | 2 | 4 | 4 | 2 | N/A→2 | 17 | D |
| security.instructions.md | 4 | 3 | 4 | 4 | 2 | 2 | 19 | D |
| testing.instructions.md | 4 | 2 | 4 | 4 | 2 | N/A→2 | 18 | D |

### Tier distribution (instructions)

- A: 0
- B: 0
- C: 0
- D: 4
- F: 0

### Average per-axis score (instructions)

- A1: 3.50
- A2: 2.50
- A3: 4.00
- A4: 3.75
- A5: 2.00
- A6: 2.00

### Low-axis citations (instructions)

- `agent-prompts.instructions.md:7` punts to `.agents/steering/agent-prompts.md` and `.agents/AGENT-SYSTEM.md`. "Quick Reference" gives shape but order and boundaries live elsewhere. A1=3, A5=2 (no tool directive on a steering doc that drives agent generation), A2=3 (terse but unbounded), A6=2 (no reasoning directive on a meta-prompting steering doc).
- `documentation.instructions.md:11-16` five bullet "Quick Reference" with no shape/order spec for the documents it steers. A2=2 (no length signal at all), A5=2.
- `security.instructions.md:7` punts to steering and security agent. Useful OWASP/STRIDE checklists at lines 13-22, 63-70 land Axis 1 at 4 (shape implied by checklist). A2=3, A5=2 (no "scan first, then advise" directive).
- `testing.instructions.md:11-21` AAA pattern + Pester skeleton land Axis 4 at 4. A2=2 (no length envelope), A5=2.

The four instruction files are pointer stubs (18-72 LOC) that defer to canonical steering documents under `.agents/steering/`. They function as Copilot entry points, not as standalone instructions. Per the rubric, they are scored as-written, not as-referenced.

## Top 5 worst-scoring across both sections

1. `documentation.instructions.md` (17/30, D) ,  pointer stub, no length envelope, no tool directive, no reasoning directive on a doc that governs **/*.md.
2. `agent-prompts.instructions.md` (17/30, D) ,  meta-steering doc that does not itself meet the discipline it steers; "Structure Requirements" list at line 28 names six section headers without order rationale or shape contract.
3. `testing.instructions.md` (18/30, D) ,  Pester boilerplate without coverage-enforcement directive or tool-use rule.
4. `security.instructions.md` (19/30, D) ,  OWASP/STRIDE checklists are useful but no enforcement language ("apply STRIDE for new features" is positive, but no tool directive to scan, no reasoning depth).
5. `independent-thinker.shared.md` (22/35, C) ,  the contrarian role explicitly demands rigorous reasoning but the file contains zero reasoning directives, no inter-agent output contract, and the shortest body (204 LOC) of any template.

## Top 5 best-scoring (templates section)

1. `retrospective.shared.md` (29/35, B) ,  explicit frameworks (Five Whys, Fishbone, Force Field, Learning Matrix), atomicity scores, evidence requirements, Phase 0/1 structure. Shipping verbs throughout.
2. `orchestrator.shared.md` (27/35, B) ,  explicit delegation protocol (one-level-deep architecture constraint at line 95-138), triage table (line 75-83), expected failure scenarios table (line 227-239), agent capability matrix (line 207-225). Best inter-agent contract in the codebase. Loses points on Axis 2 (1448 LOC unbounded) and Axis 6 (no think-first directive on routing decisions).
3. `implementer.shared.md` (27/35, B) ,  explicit code-quality metrics (cyclomatic <=10, methods <=60 lines), SOLID hierarchy reference, task-to-memory mapping table.
4. `pr-comment-responder.shared.md` (26/35, B) ,  workflow paths table (Quick/Standard/Strategic at line 62-67), explicit script inventory (line 74-80), comment classification rules.
5. `security.shared.md` (26/35, B) ,  CWE-699 detection categories, OWASP Top 10:2021 scanning, risk-score numeric format requirement at line 50, severity classification with explicit criteria.

Honorable mentions: `critic.shared.md`, `qa.shared.md`, `skillbook.shared.md` ,  all C+ with strong checklists.

## Systemic findings

1. **Zero of 18 templates carry an explicit reasoning-depth directive.** No "think before answering", no "think harder", no "extended thinking", no adaptive-reasoning invocation. Axis 6 averages 2.17. This is the single largest cross-cutting deficit. The Activation Profile "Summon" paragraphs (all 18 files) start with "I need a..." and end with imperatives like "Tell me what to do" or "Challenge my technical choices", but the reader (the model) is never told to slow down before producing the artifact. High-stakes reasoning roles (architect, security, critic, independent-thinker, high-level-advisor) carry the same deficit as low-stakes formatters.

2. **All 18 templates use "help me" or "I need..." foggy framing in the Summon block.** Grep confirms 18/18 hits on `Summon.*I need|Summon.*help me`. This is a shipping-verb regression in the most prominent paragraph of each file. The "Summon" paragraph reads as marketing copy, not as a brief. The body sections recover with shipping verbs (delegate, score, validate, extract, classify), so Axis 4 still averages 4.22, but the user-visible Summon is the weakest sentence in every file.

3. **28 em-dash hits across 14 templates violate the file's own "No em dashes" Style Guide Compliance rule.** Every template declares "No em dashes, no emojis" in its Style Guide Compliance section (line ~30-50). Then the Summon paragraph immediately below uses em-dashes. The Generate-Agents pipeline propagates these to 36 generated files (18 templates x 2 platforms; src/claude is hand-maintained but content is duplicated per ADR-036 sync rule). Heavy hitters: orchestrator (7), pr-comment-responder (8), critic (3).

4. **Length envelopes are absent on every template (Axis 2 avg 3.39).** "Short sentences (15-20 words)" governs sentence shape, not deliverable size. Templates that produce planning artifacts (planner, task-generator, roadmap), retrospectives (retrospective), and PRDs (explainer) do not cap section count, page count, or word count for the artifact. Output bloat is enabled by default.

5. **Tool-use directives are implicit (lived in frontmatter `tools_vscode` / `tools_copilot` arrays) rather than prose-explicit (Axis 5 avg 3.44).** Frontmatter tool inventories tell the platform what tools to expose; they do not tell the model "search first, verify, do not rely on memory". The contrarian role (independent-thinker) is the clearest miss: requires citations but never says "search before claiming". Same gap in analyst, planner, roadmap.

6. **The four .github/instructions/*.md files are pointer stubs that delegate to .agents/steering/. They are not auditable as standalone instructions.** All four score D (17-19/30). They function as Copilot entry-point breadcrumbs. The rubric scored them as-written; fixing the stubs is low leverage because the canonical content is in .agents/steering/ (separate audit scope).

7. **Banned vocab is rare but present.** "Comprehensive" hits 5 times across templates (planner, implementer, qa). "Crucial", "robust", "leverage", "delve", "foster", "showcase" all zero. The hits in templates appear in descriptive prose, not load-bearing instruction lines, so they do not move axis scores but should be cleaned during any rewrite pass.

## Fix leverage: which templates cascade widest

Every `templates/agents/*.shared.md` file generates two outputs (`src/vs-code-agents/*.agent.md`, `src/copilot-cli/*.agent.md`) via `python3 build/generate_agents.py`. Per ADR-036, the same content is also kept in sync with `src/claude/*.md` (hand-maintained but content-identical for universal sections). So one template fix = up to three downstream files.

Leverage rank by orchestrator-call frequency and downstream invocation surface (inferred from the orchestrator delegation table at `orchestrator.shared.md:181-191` and from agent invocation appearances across the codebase):

1. **`orchestrator.shared.md`** ,  top of the call graph. Every multi-step task routes through it. Already in B tier (27/35). Fixing Axis 6 (add reasoning directive) and Axis 2 (cap response length on each phase) would cascade to every workflow the system runs. Highest fix-leverage in the catalog despite being best-tier.

2. **`implementer.shared.md`** ,  invoked by orchestrator on every code-change workflow ("CODE changes" row of triage table). 959 LOC, B tier (27/35). Fixing Axis 6 (currently 3, raise to 5 with explicit "think before edit" on plan-validation step) prevents the most common shipping failure: code-first-think-never.

3. **`critic.shared.md`** ,  invoked on every plan validation. 491 LOC, B tier (26/35). Fixing Axis 6 (add "stress-test thoroughly before issuing verdict") and Axis 5 (add "read related ADRs and architecture files before judging") improves every plan-validation handoff orchestrator emits.

Secondary leverage cluster: `qa.shared.md`, `security.shared.md`, `analyst.shared.md` ,  each invoked on a common workflow lane (test, security review, research). Fix Axis 6 on these three to lift the average reasoning-depth score across the catalog by ~0.3.

Templates with lowest fix-leverage despite low scores: `independent-thinker.shared.md`, `high-level-advisor.shared.md`, `memory.shared.md`. Invoked rarely; rewriting them benefits a narrow workflow surface.

## Rewrite priority (templates)

1. `orchestrator.shared.md` ,  highest call-graph centrality, add reasoning directive, cap phase response length.
2. `implementer.shared.md` ,  most code surface area, add think-first on plan validation.
3. `critic.shared.md` ,  every plan goes through it, add reasoning + ADR-read directive.
4. `security.shared.md` ,  high-stakes, add threat-model think-first directive.
5. `qa.shared.md` ,  every test strategy goes through it, add reasoning + coverage tool directive.
6. `analyst.shared.md` ,  every research task, add tool-first "search before claiming" directive.
7. `architect.shared.md` ,  every ADR, add reasoning + ADR-precedent search directive.
8. `independent-thinker.shared.md` ,  role demands what file lacks; add reasoning + source-search directives.
9. `pr-comment-responder.shared.md` ,  strip 8 em-dashes; already B-tier elsewhere.
10. `retrospective.shared.md` ,  B+ already; only nit-level cleanup needed.

## Discipline self-check

- Zero em-dashes in this report.
- Banned vocab scan: zero occurrences of crucial, comprehensive, delve, robust, multifaceted, foster, showcase, underscore, tapestry, vibrant, pivotal, leverage-as-verb.
- file:line citations present on all 1-2 axis scores.

