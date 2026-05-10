---
description: Define what to build. Transform a problem into testable requirements with acceptance criteria.
allowed-tools: Task, Skill, Read, Write, Glob, Grep
argument-hint: [problem-statement-or-issue-number]
---

@CLAUDE.md

Spec: $ARGUMENTS

If $ARGUMENTS is empty, ask the user what problem to solve. Do not proceed without a problem statement.

## Process

### Step 0: First Principles Gate (blocking, runs before Step 1)

Before any clarification work, answer six forcing questions. The gate exists because every retro citing wasted spec work in the last six months traces to a question this gate forces upfront. The strongest single citation is `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` Phase 6, where the retro itself names the question this gate asks ("is the framework worth building at all if its design space misses the dominant failure modes?") and explicitly defers it as out of scope. That deferral landed after 69 commits.

The six questions, asked in order:

| Label | Question |
|-------|----------|
| **Q1 Demand Reality** | Who has explicitly requested this? Name three or more individuals, teams, or systems by name. (Question is about requesters; production signals go to Q5.) |
| **Q2 Status Quo** | What is the exact workaround users do today, step by step? |
| **Q3 Desperate Specificity** | Name the single most blocked person or system right now. What exactly are they blocked on? |
| **Q4 Narrowest Wedge** | What is the smallest possible deliverable that unblocks Q3, measured in hours of implementation? |
| **Q5 Observation** | What direct production signal proves the gap exists? Cite a metric, log entry, error count, ticket, retro line, or trend. (Question is about signals; requesters go to Q1.) |
| **Q6 Future-fit** | If the system grows 10x, does this feature still make sense, or does it become a liability? |

Write the answers as a structured block (the `## Step 0 First Principles` block) with six `### Q1..Q6` subheads, each containing the author's verbatim answer. The block flows downstream as input: Step 1 (Clarify) reads it as problem context, Step 2 (`requirements-interview`) carries it into the PRD it produces, Step 3 (Tier classification) re-validates Q4 at Tier 5, Step 6 (`spec-generator`) formalizes the PRD into durable artifacts with this block as the first section, and Step 9 (critic pre-mortem) checks that Q1/Q3/Q4 did not drift. Do not paraphrase; downstream steps depend on the verbatim answers.

#### Step 0 gate logic

**Pass criteria** (all must be true):

1. All six fields have non-empty answers.
2. No answer contains a hedge phrase from the canonical list below.
3. Q1 passes the aspirational test.
4. Q3 passes the specificity test.
5. Q5 passes the speculative test.

**Canonical hedge phrase list** (a mix of multi-word phrases and a few unambiguous single-word entries `probably`, `eventually`, `someday`, all of which read as hedges in standard English. Case-insensitive word-boundary match: `\bphrase\b`. The hyphenated technical term `eventually-consistent` is exempted via a suffix-table lookup in `step0_parser.py:HEDGE_TECHNICAL_SUFFIXES`. Applied to author answers, not to system prompts or quoted instruction text):

| Phrase | Why it hedges |
|---|---|
| `would be nice` | aspirational |
| `would be useful` | aspirational |
| `would be helpful` | aspirational |
| `we believe` | belief, not observation |
| `we expect` | prediction, not observation |
| `we anticipate` | prediction, not observation |
| `we predict` | prediction, not observation |
| `we hope` | aspiration |
| `we assume` | assumption, not evidence |
| `stakeholders want` | unnamed audience |
| `users want` | unnamed audience |
| `customers want` | unnamed audience |
| `should we` | self-questioning, not commitment |
| `might be useful` | speculation |
| `might be needed` | speculation |
| `could be useful` | speculation |
| `probably` | hedging (single word, but unambiguous) |
| `eventually` | indefinite future |
| `someday` | indefinite future |
| `down the road` | indefinite future |
| `nice to have` | low-priority aspiration |
<!-- step0:hedge-table-end -->

Single words `should`, `might`, `could` are NOT hedges in this list. They conflict with RFC 2119 requirement language and produce false positives.

**Operational test for Q1 "aspirational"** (any one condition makes Q1 aspirational, triggering H3):

1. The answer names fewer than three specific requesters (people, teams, systems, or data sources). Q1 explicitly asks for three or more. A single named requester is not enough; either name three or document the deferral and re-invoke when the demand surfaces from more sources.
2. The answer uses future tense or conditional mood about demand existence (`would want`, `if customers start`, `when we have`, `would be useful`).
3. The answer is a generic category (`users in general`, `engineers`, `the team`, `stakeholders`, `developers`).

**Operational test for Q3 "specific"** (the answer must satisfy at least one):

1. A named individual (`Alice on the Payments team`).
2. A named team (`the Bleu/Delos rotation`, `the SRE on-call`).
3. A uniquely identified system or component with a version, environment, or instance qualifier (`the auth service in prod-east`, `the GraphQL pagination in get_pr_review_threads.py`).

Generic categories fail this test.

**Operational test for Q5 "speculative"** (Q5 is speculative if all three are absent. Any one of the three present prevents the halt):

1. The answer contains a direct quote (text in `"..."` or fenced block) from a ticket, message, comment, log, or document.
2. The answer cites a metric, log entry, file path, commit SHA, PR number, or named artifact.
3. The answer names a specific person, team, or system that described the problem.

**Halt triggers** (any one fires the halt):

| ID | Trigger |
|---|---|
| H1 | Any answer contains a hedge phrase from the canonical list. |
| H2 | Q5 fails the speculative test. |
| H3 | Q1 fails the aspirational test. |
| H4 | Q3 fails the specificity test. |
| H5 | Fewer than six questions answered (partial completion). |

When any trigger fires, halt and do not proceed to Step 1.

**Halt emission format** (machine-readable; every halt MUST emit a fenced code block with info-string `step0-halt` containing five `key: value` lines):

````
```step0-halt
trigger: H3
question: Q1 Demand Reality
answer: "users would want this"
test_failed: aspirational test condition 2 (future-tense `would want`)
deferral: Re-invoke /spec after naming three or more specific requesters by name.
```
````

The five fields are:

1. `trigger`: `H1`, `H2`, `H3`, `H4`, or `H5`.
2. `question`: number and label that failed (`Q3 Desperate Specificity`).
3. `answer`: the author's answer verbatim (or the matched hedge phrase quoted) on a single line; multi-line answers fold to one line with `\n` escapes.
4. `test_failed`: name the rule that was violated (e.g., `Q3 specificity test conditions 1, 2, 3 all failed`).
5. `deferral`: a single-line instruction telling the author what to do.

Downstream callers (orchestrators, review skills, CI gates) parse this block by its `step0-halt` info-string. Free-form prose halts that omit the fenced block are non-conforming and SHALL be re-emitted in this format.

**Auto-mode behavior**: under auto-mode invocation (no human elicitation possible), the agent MUST halt with reason `STEP_0_REQUIRES_ELICITATION`, list each unanswered question, and return to the orchestrator. The agent MAY populate Step 0 from the source artifact (issue body, PR description) only when the source artifact contains the required structured fields verbatim. Free-form synthesis of Step 0 answers by the agent is prohibited. (Note: `STEP_0_REQUIRES_ELICITATION` is a prose convention in this version; no orchestrator caller currently parses it. Future iteration will add machine-readable halt protocol.)

**Kill criteria for the gate itself**: at 30 invocations, this gate is reviewed against four kill criteria documented in `REQ-006-13`:

1. False-positive rate ≥30% (halts followed by re-invocation with cosmetic word changes).
2. Bypass rate ≥20%.
3. Author abandonment ≥3 sessions in 7 days.
4. 30 consecutive passes with zero halts (recalibration trigger, not a kill).

If any criterion fires, the gate is loosened or removed in a follow-up PR.

**Tally instruction**: after each Step 0 evaluation (whether pass or halt), append one line to `.agents/metrics/STEP-0-METRICS.md`. Create the file lazily if absent, with header line `# Step 0 Metrics (one line per /spec invocation)`. Each tally line: `<ISO-8601 timestamp> | <pass|fail> | <halt-trigger-or-none> | <halt-question-or-none>`. Absence of the file does not block `/spec`; the tally is review-only data for the kill criteria above.

**Archival policy**: after each kill-criteria review (every 30 invocations or when a kill criterion fires, whichever comes first), rotate the tally file: rename `.agents/metrics/STEP-0-METRICS.md` to `.agents/metrics/STEP-0-METRICS-YYYYMMDD.md` (using the review date) and start a fresh file with the same header. The rotated file is the audit trail for that review window. The active file SHALL NOT exceed 100 entries before rotation.

---

1. Clarify the problem. Step 0 already captured demand (Q1), status quo (Q2), specificity (Q3), wedge (Q4), observation (Q5), and future-fit (Q6). **Do not re-elicit Q1-Q6 here.** Step 1 scope is narrower: clarify constraints, non-functional requirements, integration touch points, and edge cases not already addressed by the Q4 wedge.
2. **Run the adversarial requirements interview**: Invoke Skill(skill="requirements-interview") to walk the design tree before any further analysis. The skill grills the user on user stories, data model, integrations, failure modes, security, observability, and scope boundaries. For every question it must propose a recommended answer; if the codebase can answer it (grep the repo first), it does so without asking. Output is a structured PRD that every downstream step consumes. Carry the PRD forward unchanged through steps 3-9; do not drop sections.
3. **Classify complexity tier**: Task(subagent_type="analyst"): Read `.claude/skills/analyze/references/engineering-complexity-tiers.md`. Using the structured PRD from step 2, classify the problem as Tier 1-5 based on scope, ambiguity, cross-team dependencies, and reversibility. Return the tier number, rationale, and recommended spec depth. Use this to calibrate remaining steps:
   - Tier 1-2 (Entry/Mid): Simple acceptance criteria. Skip CVA if single use case.
   - Tier 3 (Senior): CVA analysis required. Cross-team input. Design review gate.
   - Tier 4 (Staff): Alternatives analysis mandatory. ADR required. Stakeholder alignment. Challenge: "can this be decomposed into a simpler tier?"
   - Tier 5 (Principal): Governance review. Multi-org consensus. Re-validate Step 0 Q4 (Narrowest Wedge) in the context of emerged complexity. If the wedge can be narrowed further without losing the unblocking value identified in Q3, narrow it before proceeding. Step 0 Q4 is the canonical wedge question for every tier.
4. Search for existing solutions in the codebase (grep for related patterns). Use the PRD's Integrations and Data model sections to scope the search.
5. **CVA analysis (conditional)**: If the complexity tier is 3-5, or Tier 1-2 with multiple use cases, invoke Skill(skill="cva-analysis"): identify commonalities across the PRD's user stories, then variabilities, then relationships. Otherwise (Tier 1-2 single-use-case), set `CVA summary: N/A (single-use-case Tier 1-2)` and proceed.
6. **Formalize the PRD into durable artifacts**: Task(subagent_type="spec-generator"). Pass every PRD section from step 2 (Problem, User stories, Data model, Integrations, Failure modes, Security, Observability, Acceptance criteria, Out of scope, Deferred, Open questions) plus the complexity tier from step 3 and the CVA summary from step 5 (which may be the `N/A` placeholder for skipped runs). The spec-generator agent writes:
   - `.agents/specs/requirements/REQ-NNN-{slug}.md` (one per requirement, EARS syntax)
   - `.agents/specs/design/DESIGN-NNN-{slug}.md`
   - `.agents/specs/tasks/TASK-NNN-{slug}.md`
   The full PRD must be passed as input so spec-generator does not re-ask questions the interview already answered. Acceptance criteria use EARS syntax (`WHEN ... THE SYSTEM SHALL ... SO THAT ...`).
7. Task(subagent_type="analyst"): You are a requirements analyst. Your job is to find gaps, ambiguities, and untestable requirements. Review every PRD section, not just acceptance criteria. For each requirement, ask: can this be verified pass/fail? Flag anything vague.
8. Invoke Skill(skill="decision-critic"): challenge assumptions before committing
9. Task(subagent_type="critic"): You are a skeptical reviewer. Run a pre-mortem: assume this spec ships and fails. What broke first? What was missing? Then run three binary Step 0 validity checks against the final PRD; the critic SHALL NOT return APPROVED while any of 9a/9b/9c is FAIL.

   - **Check 9a, Demand Reality drift**:
     - PASS: PRD acceptance criteria, user stories, OR success metric reference at least one entity (person, team, system, metric, ticket, file path) named in Step 0 Q1.
     - FAIL otherwise. On FAIL: cite Q1 entities and the PRD's current entities verbatim.
   - **Check 9b, Desperate Specificity drift**:
     - PASS: PRD user stories or acceptance criteria still treat the Q3-named blocked entity as the primary unblocking target.
     - FAIL if (a) the spec's primary user shifted to a different audience, OR (b) Q3's named entity does not appear in the PRD. On FAIL: cite Q3's entity and the PRD's current primary user verbatim.
   - **Check 9c, Narrowest Wedge drift**:
     - PASS: every PRD acceptance criterion either traces to the Q4 wedge or narrows it.
     - FAIL if any acceptance criterion adds scope beyond Q4 without a documented wedge revision. On FAIL: cite Q4 verbatim and list the AC entries that exceed the wedge.

## Evaluation Axes

1. **Problem clarity** - Is the right problem being solved? Could a reframing yield 10x impact?
2. **Requirement testability** - Can each requirement be verified pass/fail?
3. **Completeness** - No gaps between problem statement and acceptance criteria?
4. **Traceability** - REQ to DESIGN to TASK linkage established?
5. **Feasibility** - Buildable within constraints? Existing code to leverage?

## Principles

- **CVA**: Identify commonalities first, then variabilities, then relationships. Greatest risk is the wrong abstraction.
- **YAGNI**: Only specify what is needed now. Speculative requirements create waste.
- **Separation of Concerns**: Each requirement addresses one concern. Mixed concerns signal a missing decomposition.

## Output

Structured requirements document. Mirror the PRD schema produced in step 2; do not collapse to acceptance criteria alone.

- **Problem statement** (1-2 sentences)
- **User stories** (who, action, observable outcome)
- **Data model** (entities, identity, invariants, lifecycle)
- **Integrations** (external systems, failure modes, idempotency)
- **Failure modes** (retries, partial failures, conflicts, replay, schema evolution)
- **Security** (authn, authz, secrets, PII, input validation)
- **Observability** (logs, metrics, traces, alerts)
- **Acceptance criteria** (numbered, EARS syntax, each independently testable as pass/fail)
- **Out of scope** (explicit exclusions to prevent creep)
- **Deferred** (decisions punted with owners)
- **Open questions** (unresolved unknowns with owners)
- **CVA summary** (what is common, what varies, what relationships exist)
