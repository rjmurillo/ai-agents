---
type: design
id: DESIGN-011
title: Agent-Skill Classification Audit Design
status: draft
priority: P1
related:
  - REQ-011
  - TASK-011
adr: ADR-030
created: 2026-05-10
updated: 2026-05-10
author: spec
tags:
  - catalog-consolidation
  - agents
  - audit
---

# DESIGN-011: Agent-Skill Classification Audit Design

## Requirements Addressed

- **REQ-011**: Agent-skill classification audit (Phase 1 of issue #2003).

## Design Overview

The audit is a **read-only, single-pass markdown table** generator. It reads `.claude/agents/*.md`, scores each against five criteria, applies a deterministic verdict rule, and writes one markdown file plus one GitHub issue comment.

There are two reasonable implementation strategies:

| Strategy | Pros | Cons | Recommendation |
|----------|------|------|----------------|
| **A. Manual reviewer-driven** | High c2 (subjective) accuracy; reviewer judgment captured directly | Slow; not repeatable across reviewers | Default for this Phase 1 |
| **B. Script-assisted** | Repeatable; c1/c4/c5/has_shared_template scored by script; reviewer only adjudicates c2/c6 | Up-front script cost; c2 still requires human | Defer to Phase 2 if a re-audit is needed |

This design specifies **Strategy A** for Phase 1 (matches Q4 wedge of 6 hours). Script extraction may be derived in Phase 2 if scaling to skills (Wave 2 #1950) or to periodic re-audits.

## Component Details

### C1. Agent enumerator

- Input: `.claude/agents/` directory listing.
- Filter: `*.md` excluding `AGENTS.md` and `CLAUDE.md`.
- Output: ordered list of 23 agent names (alphabetical).
- Failure: list less than 23 → halt, ask reviewer (catalog drift since spec was written).

### C2. Per-criterion scorer

For each agent, score five criteria.

#### c1: Invoked from slash command via `Task(subagent_type=...)`

- Method: grep slash command files for three patterns matching the actual call forms in this repo:
  - `subagent_type[[:space:]]*[:=][[:space:]]*["']?{agent}["']?` (matches `subagent_type="agent"`, `subagent_type=agent`, and `subagent_type: agent`; uses POSIX `[[:space:]]` for `grep -E` portability)
  - `Task[[:space:]]*\([[:space:]]*[^)]*["']?{agent}["']?` (matches `Task(subagent_type="agent", ...)` and variants)
  - **Descriptive form**: paragraphs in `.claude/commands/*.md` that contain both `Task(subagent_type=...)` (with a literal `...` placeholder) AND a parenthesized agent list naming `{agent}`. Example: `.claude/commands/review.md:32` reads `Task(subagent_type=...) agent (analyst, architect, qa, security, devops, roadmap)` and invokes `roadmap` this way. Match per `re.search(rf'Task\s*\(\s*subagent_type\s*=\s*\.\.\.\s*\)[^\n]*?\(([^)]+)\)', text)` and check if `{agent}` appears in the captured list. (The Python `re` module supports `\s`; the equivalent shell form for `grep -E` is `Task[[:space:]]*\([[:space:]]*subagent_type[[:space:]]*=[[:space:]]*\.\.\.[[:space:]]*\)`.) This form was missed by the first two patterns and produced a false c1=No for `roadmap` until round 3 of audit corrections.
- Search paths: `.claude/commands/` and `templates/commands/`.
- Yes if any match found in a slash command file.
- No if matches only in other agent files (peer-to-peer invocation).
- Evidence: matched `file:line`.

#### c2: Body composition (≥70% reference)

- Method: human reviewer counts structured-reference elements: format spec sections, decision tables, anti-pattern lists, validation rule lists, schema references.
- ≥70% if reference elements occupy ≥70% of body line count by visual estimate.
- 50-69% if mixed.
- <50% if predominantly reasoning/methodology prose.
- Evidence: one-line description (e.g., "5 decision tables, 3 anti-pattern lists, format-spec section dominates 320 of 410 body lines").

#### c3: Sibling artifact in same pipeline is a skill

- Method: identify the slash command(s) that invoke this agent (from c1 evidence). For each pipeline, list other artifacts the slash command invokes. Check if any are skills (`.claude/skills/{name}/SKILL.md`).
- Yes if at least one pipeline-sibling is a skill.
- No if all pipeline siblings are agents.
- N/A if no single pipeline invokes this agent (e.g., generic `analyst`, `critic` invoked from many).
- Evidence: pipeline name + sibling skill name (e.g., "/spec pipeline: requirements-interview is a skill").

#### c4: Schema/format drift caught by review automation

- Method: `gh search prs --repo rjmurillo/ai-agents --json number,title -- "agent {agent}" --search "in:body schema OR enum OR frontmatter"` plus inspection of CodeRabbit comment threads on PRs that touched this agent's outputs.
- Yes if 2+ schema-drift comment threads found across distinct PRs.
- No if no drift evidence found in PR history.
- Unknown if agent has no PR history producing parseable artifacts (e.g., pure-advisor agents).
- Evidence: PR number(s) + thread count.

#### c5: Frontmatter bytes (load-budget criterion)

- Method: `awk '/^---$/{n++} n==2{print NR; exit}' agent.md` then `head -n {N} agent.md | wc -c`.
- Output: integer bytes from start of file through closing `---` of YAML frontmatter.
- Also record `wc -c agent.md` for full body size.
- Evidence: byte counts.

#### has_shared_template (ADR-036 dual-source check)

- Method: `test -f templates/agents/{agent}.shared.md && echo Yes || echo No`.
- Evidence: result of test.

### C3. Verdict assigner

Decision rule (per `verdict_decision_thresholds: discriminator-2-of-4`, with hard/soft isolation split reconciling PRD AC-6 + the audit's verdict rule):

```text
discriminator_score = count(c1=Yes) + count(c2=>=70%) + count(c3=Yes) + count(c4=Yes)
# c2 50-69% counts as 0; c4 Unknown counts as 0; c3 N/A counts as 0

isolation = hard | soft | none
  hard: agent body documents that it MUST NOT see/pollute parent's context
        (per #2003 counter-signal: orchestrator routing, critic adversarial
        review, analyst bias-free investigation). context: fork still leaks
        parent working state and breaks the asymmetry the agent depends on.
  soft: agent benefits from a fresh sub-context but does not require
        parent-context exclusion. context: fork (skill mode) serves.
  none: no isolation requirement.

verdict = keep-as-agent       if isolation = hard (regardless of score)
verdict = context-fork-skill  if score >= 2 AND isolation = soft
verdict = skill               if score >= 2 AND isolation = none
verdict = keep-as-agent       if score < 2  (no shape mismatch detected)
verdict = merge-into-X        if overlap_with_other_agent >= 70%  (Phase 2)
```

`overlap_with_other_agent` is sourced from `.agents/governance/agent-consolidation-process.md` Phase 1 capability matrix. For Phase 1 of this audit, this is human judgment; quantitative scoring deferred to Phase 2.

The hard/soft split was added to reconcile (a) the originally-collapsed `isolation_exception` flag in this design, (b) PRD AC-6's "cannot be satisfied by `context: fork`" language, and (c) the actual Phase 1 audit's `keep-as-agent` assignment for `analyst`/`critic`/`orchestrator`. See the audit document's "Verdict rule" section for the canonical statement.

### C4. Audit document writer

- Output 1: `.agents/audits/2026-05-10-agent-skill-classification-audit.md`. Schema:

  ```markdown
  ---
  type: audit
  id: AUDIT-2026-05-10-agent-skill
  source: GH-2003
  parent_epic: GH-1944
  authority: [ADR-030, ADR-036, agent-consolidation-process.md]
  created: 2026-05-10
  git_sha: <sha at audit time>
  agent_count: 23
  ---

  # Agent-Skill Classification Audit (2026-05-10)

  ## Authority and method

  ## Audit table

  | agent | c1 | c1_evidence | c2 | c2_evidence | c3 | c3_evidence | c4 | c4_evidence | c5_frontmatter_bytes | c5_full_body_bytes | has_shared_template | discriminator_score | verdict | verdict_rationale |
  |-------|----|-------------|----|-------------|----|-------------|----|-------------|---------------------|--------------------|--------------------|--------------------|---------|-------------------|
  | adr-generator | … | … | … | … | … | … | … | … | … | … | … | … | … | … |
  | … (22 more rows) | … | … | … | … | … | … | … | … | … | … | … | … | … | … |

  ## Summary

  - Total agents: N
  - Verdict counts: skill=N, context-fork-skill=N, keep-as-agent=N, merge-into-X=N
  - Total c5_frontmatter_bytes saved if all skill verdicts migrated: N bytes (% of catalog)

  ## Phase 2 backlog (verdict ≠ keep-as-agent)

  - **{agent}**: {verdict_rationale}
  - …

  ## Out of scope (per PRD §9)

  ## Notes
  ```

- Output 2: GitHub issue comment on #2003.
  - Body: short (≤500 words) with link to committed file, summary table (verdict counts only), and Phase 2 backlog list.
  - Tool: `gh issue comment 2003 --body-file <tempfile> --repo rjmurillo/ai-agents`.
  - Idempotency: if a previous comment from the same author starts with marker `<!-- agent-skill-audit:2026-05-10 -->`, edit it; otherwise create new.

### C5. Phase 2 backlog generator

- Input: rows where `verdict != keep-as-agent`.
- Output: bullet list, one per row: `**{agent}**: verdict={verdict}; {verdict_rationale}; refactor target = {target_path or 'TBD'}`.
- Embedded in audit document at "Phase 2 backlog" section.
- Each bullet becomes a candidate for a separate filed issue per `phase_2_3_governance: separate-issues`.

## Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Output format | Markdown table | Reviewable in PR; renders on GitHub; greppable |
| Storage | `.agents/audits/` (new directory) | Convention matches `.agents/analysis/`, `.agents/critique/`, etc. |
| Filename pattern | `YYYY-MM-DD-agent-skill-classification-audit.md` | Date prefix supports re-audits without overwrite; matches retrospective convention |
| Issue comment marker | HTML comment `<!-- agent-skill-audit:YYYY-MM-DD -->` | Idempotent edit detection |
| Verdict assignment | Human reviewer applying documented rule | Phase 1 is small (23 agents); script overhead not justified |
| Tool stack | gh CLI, grep, awk, test | Existing in repo; no new dependencies |

## Security Considerations

- No credentials accessed.
- No file modifications under `.claude/agents/`, `templates/agents/`, `src/`.
- gh CLI uses existing user authentication.
- Issue comment posting follows GitHub's content rules; no PII or secrets.

## Testing Strategy

- **Manual verification per AC**: walk through PRD §8 AC-1..AC-12 against the produced audit file.
- **Schema verification**: validate REQ-011, DESIGN-011, TASK-011 frontmatter against `.agents/governance/spec-schemas.md` (the very anti-pattern this audit addresses).
- **Determinism check (NFR-1)**: re-run c1, c3, c4, c5, has_shared_template scoring and confirm byte-identical output.
- **Read-only check (NFR-2)**: `git status` after audit run shows changes only to `.agents/audits/`, `.agents/specs/`, and (optionally) `.agents/metrics/`.
- **Coverage check (AC-3)**: row count equals output of `ls .claude/agents/*.md | grep -v -E '(AGENTS|CLAUDE)\.md' | wc -l`.

## Alternatives Considered

| Alternative | Why not chosen |
|-------------|----------------|
| Build a Python scorer script for all 5 criteria | Premature; 23 agents is manually tractable; c2 requires human anyway |
| Use `eval-skill-overlap.py` for quantitative ranking | Overkill for Phase 1; deferred per Q4 wedge |
| Score only the 4 original criteria, skip c5 | Loses load-budget impact data; the truncation context (user-reported this session) makes c5 essential |
| Output JSON instead of markdown | GitHub-rendered markdown is the durable artifact convention in `.agents/`; JSON would need a renderer |
| Inline the table in the issue comment | GitHub issue comments truncate large tables; committed file is canonical, comment links to it (matches `evidence_artifact_location: both`) |

## Migration Path

This audit is the first artifact under `.agents/audits/`. Future audits (skill-side per #1950, periodic re-runs) follow the same convention.

## Open Design Questions

See PRD §11. Specifically:
- c2 scoring rubric for borderline cases.
- c3 "same pipeline" definition for multi-pipeline agents.
- Whether to extract a script for Phase 2 / re-audits.
