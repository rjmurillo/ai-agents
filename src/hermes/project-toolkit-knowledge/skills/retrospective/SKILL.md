---
name: retrospective
version: 0.1.0
description: "Extract learnings from a session or task: gather evidence, Five Whys, atomicity score, retrospective artifact. Use when you say \"run a retrospective\", \"retro fill\", \"list pending retros\", or \"extract learnings from this session\", when editing a docs/retros file, or when a retro is owed after a red main, revert, or user correction. Do NOT use for in-conversation correction capture (use reflect)."
license: Apache-2.0
argument-hint: "[fill <YYYY-MM-DD> | list | <scope>]"
user-invocable: true
---

# Retrospective

<!-- vendor-portability: declared. This skill reads the consumer's most recent session log under .project-toolkit/sessions/ as evidence and writes the retrospective artifact to .project-toolkit/retrospective/YYYY-MM-DD-[scope].md (creating the directory on demand). The session-log read is best-effort (the skill notes the source as absent when missing); the retrospective path is a write target. A vendored install without .project-toolkit/ gathers from git history alone and creates the output directory. -->

Turn execution experience into institutional knowledge. This skill orchestrates a fixed
Phase 0 through Phase 5 workflow that gathers evidence, generates insights, diagnoses root
causes, decides actions, scores atomicity, and persists learnings. The long-form rubrics
live verbatim in `references/`; this file is the orchestration contract.

This skill owns the long-form rubrics the retrospective agent loads from `references/`.
It is callable from `Skill("retrospective")` and from `/retrospective fill <date>`.

**Argument dispatch.** The request is $ARGUMENTS. When its first word is exactly
`fill` or `list`, follow references/skeleton-fill.md instead of treating it as a
scope. It lists pending skeletons, or fills one dated skeleton by running the
Phase 0..5 workflow below on that file. Any other argument is the scope.
A bare `/retrospective` with no arguments asks for that scope; it does not list
skeletons, which the retired `/retro` did. Use `/retrospective list` for that.
The Stop hook that once invoked it automatically was deleted, so a
retrospective is written when someone asks for one.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `run a retrospective` | Full Phase 0..5 workflow over the given scope |
| `retro fill` | Fill a dated auto-retro skeleton, or list pending ones; arguments and procedure in references/skeleton-fill.md |
| `extract learnings from this session` | Phase 0..4 over the current session |
| `diagnose this failure` | Phase 0..2 root-cause analysis, then stop |
| `what did we learn` | Phase 4 atomicity-scored learning extraction |

---

## When to Use

| Situation | Use This Skill? |
|-----------|-----------------|
| A `reflect` pass produced a HIGH-confidence finding | Yes |
| `main` went red, or a merge was reverted or force-fixed | Yes |
| A correction exposed a systemic failure | Yes |
| A session ended and nothing above fired | No, a calendar is not a trigger |
| An unfilled auto-retro skeleton exists in `.project-toolkit/retrospective/` | Yes (fill it) |
| Diagnosing why a task failed (Five Whys, fishbone) | Yes |
| Capturing a single in-conversation correction ("no", "wrong") | No, use `reflect` |
| Saving a quick checkpoint with no analysis | No, use `/checkpoint` |

The output artifact is a Markdown file. The Learning Extraction Template in
`references/learning-template.md` defines the exact structure. Save to
`.project-toolkit/retrospective/YYYY-MM-DD-[scope].md`. Nothing writes new auto-retro
skeletons: the Stop hook that produced them was deleted. Skeletons
already on disk are historical and still fillable; when filling one, write to
its existing `YYYY-MM-DD-auto-retro.md`.

---

## Inputs

| Input | Source | Required |
|-------|--------|----------|
| Scope | User argument (session, task, date, PR) | Yes |
| Session log | `.project-toolkit/sessions/` most recent for the period | When available |
| Git history | `git log` over the period | When available |
| GitHub activity | PRs and issues for the period (via the `github` skill) | Optional enrichment |

Treat the session log as the system of record for what happened. Git history and GitHub
activity are derived evidence that corroborate or extend it. When a source is unavailable,
degrade gracefully: produce the artifact from the evidence you have and mark the missing
sections, never substitute invented data.

A session log or transcript you will read on more than one turn, or one too large to
read whole, costs its full size on every turn that carries it. Distill it once with
`distill_artifact.py` (usage: context-optimizer skill, Tool Details: Distill
Artifact) and use the digest to locate evidence. When it lacks a detail, search the
raw source for that detail and read the matching lines with their context.

---

Folded rule: before you create or edit a retrospective file, or decide whether a retro is owed, read [retros](references/rule-retros.md).

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

Evidence sources: the most recent session log under `.project-toolkit/sessions/`, `git log` for the
period, optional GitHub activity through the `github` skill (never raw `gh`), and an explicit
native Copilot journal via `extract_evidence.py --journal <events.jsonl>` (bounded tool receipts).
Where the journal reader does not ship (the Hermes pack), the journal is reported unavailable.

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
`.project-toolkit/retrospective/YYYY-MM-DD-[scope].md`. When filling an auto-retro skeleton, overwrite
the placeholder sections in the existing `YYYY-MM-DD-auto-retro.md` and remove the UNFILLED
banner.

### Phase 5: Persist and Close

Persist learnings to memory and evaluate the retrospective itself.

- Persist learnings with atomicity at or above 70 percent to repository memory with the `memory` skill (ADR-126). Search
  for existing patterns before creating new entries to avoid duplicates: see
  [diagnosis-and-actions.md, Memory Protocol](references/diagnosis-and-actions.md#memory-protocol).
- Close with **+/Delta**, **ROTI**, and **Helped, Hindered, Hypothesis**: see
  [frameworks.md, Closing Activities](references/frameworks.md#closing-activities).
- Record each actionable delta item in the artifact's `Findings for the owner` table, classed
  from the frozen completion contract: see
  [frameworks.md, Delta Triage](references/frameworks.md#activity-delta-triage). Do not file a
  GitHub issue or write a backlog memory file. The owner decides what becomes tracked work.

---

## Success Criteria

Before the retrospective is complete, confirm:

- [ ] One Markdown file exists at `.project-toolkit/retrospective/YYYY-MM-DD-[scope].md` (or the
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
  or file issues; it lists delta items for the owner in the artifact.
- Memory and GitHub are integration points. A failed memory call degrades to a documented
  fallback (write the artifact, note the memory write failed), never a silent context loss.
- Keep the fill entry point thin. `references/skeleton-fill.md` parses the arguments and
  resolves the file; the Phase 0..5 workflow above does the analysis.

---

## Scripts

| Script | Purpose | Exit codes |
|---|---|---|
| `scripts/run_retrospective.py` | Orchestrate Phase 0 to Phase 5 and write the retrospective artifact. | `0` artifact written; `1` a supplied learning scored below the persistence threshold (still written); `2` usage or configuration error; `3` unexpected external failure. |
| `scripts/extract_evidence.py` | Gather Phase 0 evidence (session log, git history, optional `--journal`) for the scope. | `0` evidence gathered (sources may be marked absent); `2` usage or configuration error; `3` unexpected external failure. |
| `scripts/score_atomicity.py` | Score a candidate learning against the 70% persistence threshold. | `0` at or above threshold; `1` below threshold (refine or reject); `2` usage or configuration error. |

## References

- [frameworks.md](references/frameworks.md): Phase 0, 1, and closing activity rubrics
  (4-Step Debrief, Execution Trace, Outcome Classification, Five Whys, Fishbone, Force Field,
  Patterns and Shifts, Learning Matrix, +/Delta, ROTI, Helped/Hindered/Hypothesis).
- [diagnosis-and-actions.md](references/diagnosis-and-actions.md): Phase 2, 3, 4, and 5
  rubrics (diagnosis priority and traceability, root-cause patterns, action classification,
  SMART validation, atomicity scoring, evidence-based tagging, memory protocol).
- [learning-template.md](references/learning-template.md): the byte-exact Learning Extraction
  Template that the output artifact must match.
- [recursive-extraction.md](references/recursive-extraction.md): the agent's Phase 5 templates
  (candidate list, delegation request, termination rules, artifact block).
- [handoff-example.md](references/handoff-example.md): a filled example of the agent's
  structured handoff block.
- [skeleton-fill.md](references/skeleton-fill.md): the `fill` and `list` operations for
  auto-retro skeletons, including the untrusted-data rules for their filenames and bodies.
- `.claude/agents/retrospective.md`: the agent that loads these references. The references
  are the canonical home of the rubrics; the agent keeps only the gates and load conditions.
