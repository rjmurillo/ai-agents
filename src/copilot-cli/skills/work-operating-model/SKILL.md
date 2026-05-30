---
name: work-operating-model
version: 1.0.0
model: claude-sonnet-4-6
description: "Run a 5-layer interview to elicit how a team actually works (rhythms, decisions, dependencies, institutional knowledge, friction) and emit a structured operating model. Use when you say \"elicit operating model\", \"interview team operating model\", \"how does this team actually work\", or \"validate operating model\". Do NOT use for code analysis (use the analyst agent), external audience narratives (use the explainer agent), or retrospectives (use the retrospective agent)."
license: MIT
---

# Work Operating Model

A conversation-first elicitation skill. Surface what is documented, what is tacit, and where the two disagree. Output is a structured operating model that downstream agents (`architect`, `roadmap`, `orchestrator`) can read.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `elicit operating model` | Start the 5-layer interview |
| `interview team operating model` | Start the 5-layer interview |
| `how does this team actually work` | Start the 5-layer interview |
| `resume operating model interview` | Continue from the last completed layer |
| `validate operating model` | Run scripts/validate_operating_model.py against an output JSON |

## When to Use

**Use this skill when:**

- You need a baseline of team practice before an ADR, retrospective, or scope decision.
- A new agent or skill needs to be customized to a team's actual cadences and decision rights.
- A planning conversation keeps getting derailed by missing context about how the team operates.

**Do not use this skill when:**

- The question is about code, not people-process. Use the `analyst` agent.
- You need a strategic narrative for an external audience. Use the `explainer` agent.
- A retrospective is what you actually need. Use the `retrospective` agent.

## Distinction From Adjacent Capabilities

| Capability | Investigates | Output |
|------------|--------------|--------|
| `analyst` agent | Code, repo state, bug paths | Findings document |
| `explainer` agent | Concepts, decisions for a reader | Explainer prose |
| `retrospective` agent | A bounded past period | Learning matrix |
| **work-operating-model** | **Team operating reality (people-process)** | **Structured operating model JSON** |

## The 5 Layers

The interview proceeds in order. Each layer answers one question and produces one section of the output JSON. Skip a layer only when the team explicitly cannot answer it; record the gap in `metadata.skipped_layers`.

| # | Layer | Question | Output Section |
|---|-------|----------|----------------|
| 1 | Rhythms | When does work happen, and on what cadence? | `rhythms` |
| 2 | Decisions | Who decides what, and how is the decision recorded? | `decisions` |
| 3 | Dependencies | Who do you wait on, and who waits on you? | `dependencies` |
| 4 | Institutional Knowledge | What lives in someone's head and not in a doc? | `institutional_knowledge` |
| 5 | Friction | What is broken or slow that the team has accepted? | `friction` |

For the full prompt list per layer, read `references/layer-questions.md`. For the output JSON contract, read `references/entry-contract.md`.

## Process

The interview runs in three phases.

### Phase 1: Open

1. **Open**: Confirm scope (team name, what they own, size). Write the `team` section.

### Phase 2: Layer Pass

2. **Layer pass**: For each layer 1 through 5, ask the question, capture answers, record them in the relevant output section. After each layer, summarize back to the user and confirm before moving on.
3. **Distinguish**: For every captured item, mark it as `documented` (link the doc) or `tacit` (note the source person). Disagreement between sources is a finding, not an error.

### Phase 3: Close and Validate

4. **Close**: Write the JSON to `<workspace>/operating-model.json` (caller chooses workspace). Optionally also emit `USER.md`, `SOUL.md`, `HEARTBEAT.md` as human-readable views derived from the JSON. The JSON is canonical; the markdown files are projections.
5. **Validate**: Run `python3 .claude/skills/work-operating-model/scripts/validate_operating_model.py <path-to-json>`. Exit 0 means the schema holds.

## Scripts

| Script | Purpose | Exit Codes |
|--------|---------|------------|
| `scripts/validate_operating_model.py <path>` | Validate operating-model.json against schema v1.0.0 | 0 ok, 1 schema failure, 2 invalid usage |

Pass `--skip-path-validation` to bypass CWE-22 path containment when reading fixtures from outside the repo (tests only).

## Resume Across Sessions

The interview is long. To resume:

1. Read the existing `operating-model.json`.
2. Inspect `metadata.completed_layers`. The next layer is the first one not in that list.
3. Continue from the start of that layer.

Do not silently rewrite an earlier layer. If a previous answer needs to change, open the discussion, then update the section and append to `metadata.revisions`.

## Output Contract (Summary)

The full schema is in `references/entry-contract.md`. The minimum valid document has:

- `schema_version`: `"1.0.0"`
- `team`: object with `name`
- `rhythms`, `decisions`, `dependencies`, `institutional_knowledge`, `friction`: each present, each an object (may be empty if a layer was skipped)
- `metadata`: object with `interview_date` (`YYYY-MM-DD`), `interview_status` (`in_progress` or `complete`), `completed_layers` (list)

The validator (`scripts/validate_operating_model.py`) enforces these and returns a non-zero exit on schema failure.

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Treat the interview as a survey to fill in alone | Misses tacit knowledge entirely | Hold the conversation; capture during the talk |
| Merge `documented` and `tacit` into one bucket | Erases the gap that is the whole point | Tag every item explicitly |
| Skip layer 4 because it is hard | Layer 4 is where most useful findings live | Ask anyway; if unanswered, record it in `metadata.skipped_layers` with a reason |
| Edit the JSON by hand without reopening the conversation | Drift between model and reality | Re-interview, then update |
| Run the interview once and call the model done | Operating models drift | Re-validate quarterly; bump `metadata.interview_date` |

## Verification Checklist

Before declaring an operating model complete:

- [ ] All 5 layers either captured or explicitly skipped (recorded in `metadata.skipped_layers`).
- [ ] Every item in every layer marked `documented` or `tacit`.
- [ ] `metadata.interview_status` is `complete`.
- [ ] `python3 .claude/skills/work-operating-model/scripts/validate_operating_model.py operating-model.json` exits 0.
- [ ] The team representative has read the final JSON (or its `USER.md` projection) and agreed.

## References

- `references/layer-questions.md` - prompt list per layer
- `references/entry-contract.md` - full output JSON schema
- `scripts/validate_operating_model.py` - schema validator
