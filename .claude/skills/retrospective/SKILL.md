---
name: retrospective
version: 0.1.0
model: claude-sonnet-4-6
description: Extract learnings from a session or task through structured retrospective frameworks. Gathers evidence, runs Five Whys and fishbone diagnosis, scores atomicity, and writes a canonical retrospective artifact. Use to turn execution experience into institutional knowledge. Do NOT use for in-conversation correction capture (use the reflect skill).
license: MIT
metadata:
  domains: [retrospective, learning-extraction, root-cause-analysis, continuous-improvement]
  type: workflow
  inputs: [scope-description, session-log, git-history]
  outputs: [retrospective-markdown-file]
  adr: ADR-008, ADR-017, ADR-037
---

# Retrospective

Turn execution experience into institutional knowledge. This skill orchestrates a fixed
Phase 0 through Phase 5 workflow that gathers evidence, generates insights, diagnoses root
causes, decides actions, scores atomicity, and persists learnings. The long-form rubrics
live verbatim in `references/`; this file is the orchestration contract.

This skill replaces the former `retrospective` agent (`.claude/agents/retrospective.md`).
Lifecycle hooks can invoke a skill but not an agent, so the retrospective workflow moves
here to be callable from `Skill("retrospective")` and from `/retro fill <date>` (Issue #2531).

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `run a retrospective` | Full Phase 0..5 workflow over the given scope |
| `retro fill` | Fill an unfilled auto-retro skeleton for a date |
| `extract learnings from this session` | Phase 0..4 over the current session |
| `diagnose this failure` | Phase 0..2 root-cause analysis, then stop |
| `what did we learn` | Phase 4 atomicity-scored learning extraction |

---

## When to Use

| Situation | Use This Skill? |
|-----------|-----------------|
| Session ended with meaningful work and you want learnings persisted | Yes |
| An unfilled auto-retro skeleton exists in `.agents/retrospective/` | Yes (fill it) |
| Diagnosing why a task failed (Five Whys, fishbone) | Yes |
| Capturing a single in-conversation correction ("no", "wrong") | No, use `reflect` |
| Saving a quick checkpoint with no analysis | No, use `session-end` |

The output artifact is a Markdown file. The Learning Extraction Template in
`references/learning-template.md` defines the exact structure. Save to
`.agents/retrospective/YYYY-MM-DD-[scope].md`. When filling an auto-retro skeleton, write
to the existing `YYYY-MM-DD-auto-retro.md` file produced by the Stop hook.

---

## Inputs

| Input | Source | Required |
|-------|--------|----------|
| Scope | User argument (session, task, date, PR) | Yes |
| Session log | `.agents/sessions/` most recent for the period | When available |
| Git history | `git log` over the period | When available |
| GitHub activity | PRs and issues for the period (via the `github` skill) | Optional enrichment |

Treat the session log as the system of record for what happened. Git history and GitHub
activity are derived evidence that corroborate or extend it. When a source is unavailable,
degrade gracefully: produce the artifact from the evidence you have and mark the missing
sections, never substitute invented data.

---

## Process

The workflow is six sequential phases. Phase 0 gathers facts. Phases 1 and 2 interpret them.
Phase 3 decides actions. Phase 4 extracts and scores learnings. Phase 5 persists them. Each
phase links to the rubric and template it uses. Run them in order; do not interpret before
you observe.

### Phase 0: Data Gathering

Gather facts before interpretation. Observation precedes diagnosis.

- Run the **4-Step Debrief** (Observe, Respond, Analyze, Apply): see
  [frameworks.md, 4-Step Debrief](references/frameworks.md#activity-4-step-debrief).
- Build the **Execution Trace** chronology: see
  [frameworks.md, Execution Trace Analysis](references/frameworks.md#activity-execution-trace-analysis).
- Run **Outcome Classification** (Mad, Sad, Glad): see
  [frameworks.md, Outcome Classification](references/frameworks.md#activity-outcome-classification).

Evidence sources: the most recent session log under `.agents/sessions/`, `git log` for the
period, and optional GitHub activity through the `github` skill. Do not use raw `gh`.

### Phase 1: Generate Insights

Make meaning from data. Look past symptoms to find causes.

- **Five Whys** is mandatory for every failure: see
  [frameworks.md, Five Whys](references/frameworks.md#activity-five-whys).
- **Fishbone Analysis** for complex failures with multiple contributing factors: see
  [frameworks.md, Fishbone Analysis](references/frameworks.md#activity-fishbone-analysis).
- **Force Field Analysis** when a pattern recurs despite knowing better: see
  [frameworks.md, Force Field Analysis](references/frameworks.md#activity-force-field-analysis).
- **Patterns and Shifts** for multi-session trends: see
  [frameworks.md, Patterns and Shifts](references/frameworks.md#activity-patterns-and-shifts).
- **Learning Matrix** for quick categorization when short on time: see
  [frameworks.md, Learning Matrix](references/frameworks.md#activity-learning-matrix).

### Phase 2: Diagnosis

Prioritize findings for action. Diagnostic priority order: critical error patterns, success
analysis, near misses, efficiency opportunities, skill gaps, traceability health. The full
priority order, traceability metrics, and diagnosis template live in
[diagnosis-and-actions.md, Diagnosis](references/diagnosis-and-actions.md#diagnosis).

For each root cause that Five Whys surfaces, store a root-cause pattern for future
prevention: see
[diagnosis-and-actions.md, Root Cause Pattern Management](references/diagnosis-and-actions.md#root-cause-pattern-management).

If the work touched diagnosis or action classification, stop here for the `diagnose this
failure` trigger; otherwise continue to Phase 3.

### Phase 3: Decide What to Do

Move from insights to action.

- **Action Classification** (Keep, Drop, Add, Modify): see
  [diagnosis-and-actions.md, Action Classification](references/diagnosis-and-actions.md#activity-action-classification).
- **SMART Validation** of every proposed learning before storage: see
  [diagnosis-and-actions.md, SMART Validation](references/diagnosis-and-actions.md#activity-smart-validation).
- **Dependency Ordering** of the resulting actions: see
  [diagnosis-and-actions.md, Dependency Ordering](references/diagnosis-and-actions.md#dependency-ordering).

### Phase 4: Learning Extraction

Transform insights into stored knowledge. Score every learning 0 to 100 percent for
atomicity and reject vague statements. The scoring rubric, quality thresholds, worked
examples, and evidence-based tagging live in
[diagnosis-and-actions.md, Atomicity Scoring](references/diagnosis-and-actions.md#atomicity-scoring).

Assemble the artifact using the byte-exact
[Learning Extraction Template](references/learning-template.md). Save to
`.agents/retrospective/YYYY-MM-DD-[scope].md`. When filling an auto-retro skeleton, overwrite
the placeholder sections in the existing `YYYY-MM-DD-auto-retro.md` and remove the UNFILLED
banner.

### Phase 5: Persist and Close

Persist learnings to memory and evaluate the retrospective itself.

- Persist learnings with atomicity at or above 70 percent to Serena memory (ADR-037). Search
  for existing patterns before creating new entries to avoid duplicates: see
  [diagnosis-and-actions.md, Memory Protocol](references/diagnosis-and-actions.md#memory-protocol).
- Close with **+/Delta**, **ROTI**, and **Helped, Hindered, Hypothesis**: see
  [frameworks.md, Closing Activities](references/frameworks.md#closing-activities).
- Route any P0 or P1 delta item to a GitHub issue through the `github` skill; store P2 and P3
  items in backlog memory.

---

## Success Criteria

Before the retrospective is complete, confirm:

- [ ] One Markdown file exists at `.agents/retrospective/YYYY-MM-DD-[scope].md` (or the
  existing auto-retro skeleton was filled and its UNFILLED banner removed).
- [ ] The artifact structure matches the
  [Learning Extraction Template](references/learning-template.md) byte-for-byte, with
  placeholders filled.
- [ ] Every extracted learning carries an atomicity score and an evidence reference.
- [ ] Learnings at or above 70 percent atomicity are persisted to Serena memory, or the
  memory write failure is noted in the artifact.

---

## Boundaries

- This skill reads evidence and writes one artifact plus memory entries. It does not open PRs
  itself; it routes delta items to the `github` skill.
- Memory and GitHub are integration points. A failed memory call degrades to a documented
  fallback (write the artifact, note the memory write failed), never a silent context loss.
- Keep entry points thin. The Stop hook and `/retro fill` parse inputs and call this skill;
  they do not re-implement the workflow.

---

## References

- [frameworks.md](references/frameworks.md): Phase 0, 1, and closing activity rubrics
  (4-Step Debrief, Execution Trace, Outcome Classification, Five Whys, Fishbone, Force Field,
  Patterns and Shifts, Learning Matrix, +/Delta, ROTI, Helped/Hindered/Hypothesis).
- [diagnosis-and-actions.md](references/diagnosis-and-actions.md): Phase 2, 3, 4, and 5
  rubrics (diagnosis priority and traceability, root-cause patterns, action classification,
  SMART validation, atomicity scoring, evidence-based tagging, memory protocol).
- [learning-template.md](references/learning-template.md): the byte-exact Learning Extraction
  Template that the output artifact must match.
- `.claude/agents/retrospective.md`: the source agent body these references were lifted from
  (canonical source for the rubrics; retired once the skill ships).
