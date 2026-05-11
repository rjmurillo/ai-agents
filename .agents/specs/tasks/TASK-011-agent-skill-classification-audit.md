---
type: task
id: TASK-011
title: Execute agent-skill classification audit and post results
status: todo
priority: P1
complexity: M
estimate: 9h
related:
  - DESIGN-011
assignee: implementer
created: 2026-05-10
updated: 2026-05-10
author: spec
tags:
  - catalog-consolidation
  - agents
  - audit
---

# TASK-011: Execute agent-skill classification audit and post results

## Design Context

- **DESIGN-011**: Agent-Skill Classification Audit Design.
- **REQ-011**: Agent-Skill Classification Audit (Phase 1 of issue #2003).
- **PRD**: `.agents/specs/PRD-agent-skill-classification-audit.md`.

## Objective

Produce the Phase 1 audit deliverable for issue #2003: a 23-row table classifying every agent in `.claude/agents/` against five criteria, with verdicts and Phase 2 backlog, committed at `.agents/audits/2026-05-10-agent-skill-classification-audit.md` and linked from a comment on issue #2003.

## Scope

### In scope

- Read all 23 agent files in `.claude/agents/` (excluding `AGENTS.md`, `CLAUDE.md`).
- Score each against c1, c2, c3, c4, c5, and `has_shared_template` per DESIGN-011 §C2.
- Apply verdict rule per DESIGN-011 §C3.
- Write audit markdown file per DESIGN-011 §C4 Output 1.
- Post or edit issue #2003 comment per DESIGN-011 §C4 Output 2.
- Generate Phase 2 backlog inside the audit file per DESIGN-011 §C5.
- File a separate issue for the Phase 3 CI check (a one-paragraph stub referencing this audit).

### Out of scope

See PRD §9.

## Acceptance Criteria

(Each maps to one or more PRD §8 AC.)

- [ ] **TAC-1** (covers AC-1, AC-3, AC-4, AC-7, AC-8): file `.agents/audits/2026-05-10-agent-skill-classification-audit.md` exists with exactly 23 data rows, every cell populated, every score has an evidence citation, `has_shared_template` and `c5_frontmatter_bytes` columns present.
- [ ] **TAC-2** (covers AC-5, AC-6, AC-11): every row has a verdict from the enum {skill, context-fork-skill, keep-as-agent, merge-into-X}; verdict assignment follows the discriminator-2-of-4 rule with documented isolation exceptions for orchestrator / analyst / critic / pr-comment-responder.
- [ ] **TAC-3** (covers AC-2): a comment on issue #2003 exists (created or edited) containing the marker `<!-- agent-skill-audit:2026-05-10 -->` and a link to the committed file plus a verdict-count summary.
- [ ] **TAC-4** (covers AC-9): the audit file footer includes total agents, count by verdict, total bytes saved if all `skill` AND `context-fork-skill` verdicts migrate (both are shape-mismatch refactor candidates per the discriminator), and citations to ADR-030, ADR-036, `agent-consolidation-process.md`.
- [ ] **TAC-5** (covers AC-10): the audit file's "Phase 2 backlog" section lists every row with `verdict != keep-as-agent`, each with a one-line rationale.
- [ ] **TAC-6** (covers AC-12): a separate GitHub issue exists for the Phase 3 CI check, linked from this audit's footer.
- [ ] **TAC-7** (NFR-1, NFR-2): `git status` after the audit shows changes only under `.agents/audits/`, `.agents/specs/`, `.agents/metrics/` (if metrics line appended). No changes under `.claude/agents/`, `templates/agents/`, or `src/`.
- [ ] **TAC-8** (NFR-3): every assertion in the audit cites a file path, line number, PR number, or git SHA.
- [ ] **TAC-9** (NFR-4): execution completed in less than 10 hours of reviewer time (revised bound; original wedge of 6h proved too aggressive for manual c2 scoring; track in session log).

## Implementation Plan

### Step 1: Capture baseline (15 min)

- Record current `git rev-parse HEAD` SHA.
- Run `ls .claude/agents/*.md | grep -v -E '(AGENTS|CLAUDE)\.md' | wc -l`; expect 23.
- If count differs, halt; ask maintainer (catalog drift).

### Step 2: Mechanical scoring (90 min, scriptable)

For each agent name (alphabetical):

- **c1**: detect both literal and descriptive forms of `Task(subagent_type=...)`:
  - **Literal**: `grep -rEln 'subagent_type[[:space:]]*[:=][[:space:]]*["'"'"']?'${agent}'["'"'"']?' .claude/commands/ templates/commands/` (matches `Task(subagent_type="agent")` and YAML/JSON key-value forms; uses POSIX `[[:space:]]` for `grep -E` portability across BSD and GNU grep)
  - **Descriptive**: also check `.claude/commands/*.md` for paragraphs containing both `Task(subagent_type=...)` (literal `...` placeholder) AND a parenthesized agent list naming `${agent}` (e.g., `.claude/commands/review.md:32` invokes `roadmap` this way). Match per `re.search(rf'Task\s*\(\s*subagent_type\s*=\s*\.\.\.\s*\)[^\n]*?\(([^)]+)\)', text)` and check if `${agent}` appears in the captured list. (Use Python `re` for this match because the descriptive paragraph form is harder to express portably in `grep -E`; the actual audit script uses Python.)
  - Yes/No + matched `file:line` for whichever form fired.
- **c5_frontmatter_bytes**: extract via `awk '/^---$/{n++} n==2{print NR; exit}' .claude/agents/${agent}.md` then `head -n {N} | wc -c`.
- **c5_full_body_bytes**: `wc -c .claude/agents/${agent}.md`.
- **has_shared_template**: `test -f templates/agents/${agent}.shared.md`.

### Step 3: Schema-drift discovery (90 min)

For each agent, search PR history:

- `gh search prs --repo rjmurillo/ai-agents --state all --limit 20 -- ":${agent}: schema OR enum OR frontmatter"`
- Inspect 0-3 most relevant PRs for CodeRabbit/Copilot review threads on agent output.
- c4 = Yes if 2+ schema-drift threads found in distinct PRs; No if zero; Unknown if agent has no parseable output history.

### Step 4: Pipeline analysis for c3 (90 min)

For each agent identified in c1 as invoked from a slash command:

- For each invoking slash command, list all other Task/Skill invocations in that command file.
- Check if any sibling is a skill (`.claude/skills/{name}/SKILL.md` exists).
- c3 = Yes/No/N/A.

### Step 5: Reference-vs-reasoning scoring for c2 (120 min)

Human reviewer for each agent:

- Open `.claude/agents/${agent}.md`.
- Count structured-reference elements: format spec sections, decision tables, anti-pattern lists, validation rule lists, schema references.
- Estimate ratio: ≥70% / 50-69% / <50%.
- Record evidence one-liner (counts + dominant element).

### Step 6: Verdict assignment (45 min)

For each agent:

- Compute `discriminator_score`.
- Apply rule per DESIGN-011 §C3.
- Document isolation_exception in `verdict_rationale` if verdict = keep-as-agent.
- Document `merge-into-X` target if `overlap_with_other_agent >= 70%` is asserted.

### Step 7: Document assembly (45 min)

- Build the markdown table (DESIGN-011 §C4 Output 1).
- Compute footer: total agents, verdict counts, total c5_frontmatter_bytes saved.
- Write file `.agents/audits/2026-05-10-agent-skill-classification-audit.md`.
- Append metrics line to `.agents/metrics/agent-skill-audit-runs.tsv`.

### Step 8: Issue #2003 comment (15 min)

- Build short comment body (≤500 words): link to committed file, verdict-count summary, top 3 Phase 2 candidates.
- Search existing comments on #2003 for marker `<!-- agent-skill-audit:2026-05-10 -->`.
- If found, edit; else create.

### Step 9: Phase 3 CI check stub issue (15 min)

- File a new GitHub issue titled `Phase 3 CI check: detect new agents matching skill discriminator (from #2003 audit)`.
- Body references this audit, includes the discriminator rule, and notes that implementation is non-trivial (per #2003 acceptance criteria).
- Link the new issue from the audit footer.

### Step 10: Validation (15 min)

- Walk PRD §8 AC-1..AC-12; check each.
- Run `git status`; confirm scope.
- Update session log.

## Files Affected

| Action | Path | Purpose |
|--------|------|---------|
| Create | `.agents/audits/2026-05-10-agent-skill-classification-audit.md` | Phase 1 deliverable |
| Append | `.agents/metrics/agent-skill-audit-runs.tsv` | Re-run diff support |
| (Comment) | GitHub issue #2003 | Per AC-2 |
| (Issue) | New GitHub issue | Phase 3 CI check stub per AC-12 |
| (Read-only) | `.claude/agents/*.md` (23 files) | Audit input |
| (Read-only) | `.claude/commands/*.md`, `templates/commands/*.md` | c1 detection |
| (Read-only) | `templates/agents/*.shared.md` | has_shared_template detection |
| (Read-only) | `.claude/skills/*/SKILL.md` | c3 sibling detection |

No modifications to `.claude/agents/`, `templates/agents/`, `src/`.

## Estimate

9 hours total (per breakdown below; Q4 wedge of 6h was the original estimate, refined to 9h after manual c2 scoring proved more time-intensive than projected), broken down as:

- Steps 1, 8, 9, 10: 60 min (setup + GitHub I/O + validation)
- Steps 2, 3, 4: 270 min (mechanical + lookup work; partially scriptable)
- Step 5: 120 min (human-judgment scoring; cannot be scripted)
- Steps 6, 7: 90 min (decision + write)

If Step 5 expands beyond 120 min, complete with `<50%` for the remaining agents and flag in PRD §11 open questions.

## Risks

- **R-1**: Step 4 may exceed 90 min if PR history is sparse or noisy. Mitigation: cap per-agent search at 20 PRs; if no signal in 10 min, mark Unknown.
- **R-2**: Step 5 c2 scoring may be inconsistent. Mitigation: each c2_evidence cell records the count, not the gestalt; another reviewer can re-verify by recounting.
- **R-3**: Catalog changes between Step 1 and Step 7. Mitigation: re-check git SHA at Step 7; if changed, re-verify only the modified rows.
- **R-4**: Issue comment fails (auth, rate limit). Mitigation: file is canonical; comment is a pointer; failure is recoverable.
