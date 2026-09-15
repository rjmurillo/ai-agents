---
name: spec
version: 1.0.0
description: Turn a problem into testable requirements with acceptance criteria, through a first-principles gate, a memory-first prior-art gate, and a PRD schema. Use when you say `spec this out`, `what should we build`, or `define the requirements`, and run it before plan. Do NOT use to sequence work into milestones (use plan), do NOT use to write the code (use build), and do NOT use to emit the REQ, DESIGN and TASK files directly (use spec-generator, which this invokes).
license: MIT
allowed-tools: Task, Skill, Read, Write, Glob, Grep
argument-hint: problem-statement-or-issue-number
user-invocable: true
---

# Spec

<!-- vendor-portability: contributor-scoped citation. The retrospective at
     .agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md is the evidence for
     why the Step 0 gate exists and lives upstream in the rjmurillo/ai-agents
     repo; it is cited, not resolved at runtime (ADR-083, issue #5632). -->

Define what to build: a problem turned into requirements each of which can be
judged pass or fail, gated twice before any of it is written.

Migrated from the spec command under ADR-064, which makes skills the single
user-invocable surface. The command file is gone, so its path is named here in
plain text rather than as a citation to something a reader could open.

## Triggers

`spec this out`, `what should we build`, `define the requirements`,
`turn this into acceptance criteria`

## Arguments

Spec: $ARGUMENTS

If `$ARGUMENTS` is empty, ask the user what problem to solve. Do not proceed
without a problem statement.

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

The pass criteria, hedge phrase validation table, script-resolution rules, kill criteria, and archival policy are in the `spec-generator` skill's `references/spec-step0-gates.md`.

### Step 0.5: Memory-First Gate

**Bound the search.** If three tool calls have not surfaced anything useful, stop searching and switch to first-principles reasoning. Document what you tried (which tool, what query, what came back) so the user can extend the search if the answer matters more than your time budget suggests.

Runs after Step 0 and before Step 1. It searches prior art before any new spec
work, halts when the search shows the question is already answered, and runs the
Check 9 series over the result. The gate in full, including its halt criteria,
halt block format, metrics tally and every check, is in
`references/step-0-5-memory-gate.md`. Read it before running the gate: the halt
conditions are the point, and a summary of them is not the gate.

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

- **Output schema**: Include a `Buy-vs-build decision` section recording: core-vs-context classification, alternatives evaluated, recommendation (build/buy/partner/defer), and rationale. Required for any spec that introduces a new capability; mark `N/A (bug fix / doc / refactor)` otherwise.

## Output

No em dashes or en dashes in anything this skill writes.
Use commas, periods, colons, parentheses, hyphens, or restructure.

Structured requirements document. Mirror the PRD schema produced in step 2; do not collapse to acceptance criteria alone.

- **Problem statement** (1-2 sentences)
- **User stories** (who, action, observable outcome)
- **Ontology** (Step 1 OntologyFragment summary: canonical O2 names, relationships, aggregate boundaries, decision rules, bounded-context boundaries, open questions)
- **Data model** (entities, identity, invariants, lifecycle; entity names match the OntologyFragment O2 names)
- **Integrations** (external systems, failure modes, idempotency)
- **Failure modes** (retries, partial failures, conflicts, replay, schema evolution; initially drafted at Step 2 and written into the artifacts at Step 6, then augmented in place by the Step 9 `pre-mortem` skill: failure scenarios, modes, early warnings, prevention)
- **Security** (authn, authz, secrets, PII, input validation; populated from the Step 6 `threat-modeling` skill: threats, trust boundaries, abuse cases, mitigations; or an explicit "no security surface" justification at Tier 1-2)
- **Observability** (logs, metrics, traces, alerts; populated from the Step 6 `slo-designer` skill: SLIs, SLOs, error budgets, alert thresholds; or a lightweight "what metric proves this works" line at Tier 1-2)
- **Acceptance criteria** (numbered, EARS syntax, each independently testable as pass/fail)
- **Out of scope** (explicit exclusions to prevent creep)
- **Deferred** (decisions punted with owners)
- **Open questions** (unresolved unknowns with owners)
- **CVA summary** (what is common, what varies, what relationships exist)
- **Buy-vs-build decision** (core-vs-context classification, alternatives evaluated, recommendation: build/buy/partner/defer, rationale; or `N/A (bug fix / doc / refactor)` when step 4a was skipped)
- **Complexity classification** (engineering tier 1-5 from Step 3, plus problem domain Clear/Complicated/Complex/Chaotic from the Step 3 `cynefin-classifier` skill, plus derived methodology)
- **Operating Model Context** (Tier 5 only; the 5-layer model elicited by the Step 1 `work-operating-model` skill: decision rights, communication patterns, work intake, conflict resolution, retrospection; omit at Tier 1-4)
- **ADR cross-reference** (Tier 4-5 only; the `ADR-NNN-{slug}.md` produced by the Step 6 `adr-generator` skill and its `adr-review` verdict, with the bidirectional ADR<->REQ link; omit at Tier 1-3)

## Writing Style

Applies to `AskUserQuestion`, replies to user-facing questions, and findings (review output, analysis reports, retro write-ups, PR descriptions). `AskUserQuestion` format is structure; this section is prose quality.

Rules:

- **Gloss jargon on first use per skill invocation**, even if the user pasted the term. Jargon is a term of art from one subfield, the kind the retired list enumerated: `idempotent`, `N+1`, `backpressure`, `CSRF`, `quorum`, `cache stampede`. Do not gloss ordinary engineering vocabulary, and do not gloss a term the reader's next action does not depend on. One parenthetical, five to twelve words, once per skill run rather than once per response. Skip only when the user-turn override applies. Good: `N+1 (one query per row instead of one query for all rows)`. Bad: a clause-by-clause definition of the access pattern and its performance behavior.
- **Frame questions in outcome terms**: what pain is avoided, what capability unlocks, what user experience changes. Bad: "Do you want to use Redis or Postgres?" Good: "Redis cuts the auth check from 40ms to 2ms but adds a second store to operate. Postgres keeps one store but the auth check stays at 40ms. Which trade do you want?"
- **Short sentences, concrete nouns, active voice.** Subject does verb to object. "The worker drops the message" beats "messages may be dropped under certain conditions."
- **Close decisions with user impact**: what the user sees, waits for, loses, or gains. Every option in a question should end on the consequence to the person who runs the system or uses it.

### User-Turn Override

If the current user message asks for terse output, says "no explanations," "just the answer," "skip the gloss," "I know what X means," or sets caveman mode, skip this section. The override applies to the current turn only and resets on the next user message unless the override is sticky (caveman mode, explicit "stay terse for the rest of this session").

## Completeness Principle: Boil the Lake

AI makes completeness cheap. The marginal cost of covering one more edge case, one more error path, one more test is roughly zero. Use that. Recommend the complete lake. Flag the ocean.

`builder-ethos.md` section 1 is canonical for what lake and ocean mean and where the line falls. Do not restate those definitions here. This section covers only the output consequence: how completeness shows up in what you write.

### Completeness Scores

When recommending options that differ in **coverage** (same kind of thing, more or less of it), include a `Completeness: X/10` score on each option.

- `10`: all edge cases, all error paths, all known callers handled.
- `7`: happy path plus the obvious error cases. Some edges punted with a TODO or an issue.
- `5`: happy path plus one or two failure modes. Several known edges left bare.
- `3`: shortcut. Demo path only. Caller is on their own for everything else.
- `1`: stub. Compiles, returns the right type, does not do the work.

When options differ in **kind** (different approaches, different trade spaces, not comparable on a coverage axis), write:

> `Note: options differ in kind, not coverage. No completeness score.`

Do not fabricate scores. Do not score one option and skip the others. Do not score across incomparable options to manufacture a winner.

Example, coverage-differentiated:

> Option A: add null check at `auth.ts:47`. Completeness: 4/10. Fixes the reported white screen. Leaves three other middlewares with the same bug.
>
> Option B: extract a `requireSession` helper and route all four middlewares through it. Completeness: 9/10. Fixes the reported bug plus the three latent ones. Leaves the websocket path (separate auth flow) for a follow-up.

## Confusion Protocol

For high-stakes ambiguity, **stop and ask**. Do not guess. Do not pick the option that feels right and rationalize it after.

Triggers:

- **Architecture**: which boundary owns this, which service consumes it, which model speaks for the domain. Wrong call here costs weeks of unwind.
- **Data model**: schema shape, identity, ownership, consistency semantics. Wrong call here propagates into every reader and migration that follows.
- **Destructive scope**: deletes, rewrites, migrations, anything irreversible or expensive to roll back. Wrong call here destroys work or shared state.
- **Missing context**: the request references a person, project, decision, or constraint you do not know. Wrong call here ships against assumptions instead of facts.

Format when triggered:

1. **Name the ambiguity in one sentence.** What is unclear and why it matters. Example: `Unclear whether the new session-cleanup job should delete the log file or just mark it archived. Affects every downstream consumer that reads old sessions for analytics.`
2. **Present 2 to 3 options with trade-offs.** Each option lands on a consequence the user can evaluate. Use the Completeness scoring rule above when the options differ in coverage.
3. **Ask.** Single, specific question. Use `AskUserQuestion` when the answer is one of a small set; use plain prose when the answer is open-ended.

Do not trigger this protocol for:

- Routine coding inside a clearly scoped task.
- Obvious changes where the answer is unambiguous from the code, the rules, or the user's prior message.
- Style or naming choices the author can make and the reviewer can correct cheaply.

Triggering this protocol on routine work wastes the user's time and trains them to skim past genuine ambiguity. Not triggering it on high-stakes ambiguity ships against assumptions and costs weeks.

Default for ambiguous-but-low-cost cases: act minimally, flag what you assumed, name what you skipped. The user can correct on the next turn.

### Unattended runs

Unattended: no human reads `AskUserQuestion` (scheduled trigger, fleet worker, headless session). Never end on a question: unread, it stalls.

Instead: record the ambiguity, options with trade-offs, branch taken, and why, to the per-issue handoff or the run's report; take the safest reversible branch and continue.

Ask First items (architecture, new ADRs, breaking, security) get no guess: halt only that branch; continue elsewhere.

## Scripts

Two helpers ship inside this skill so an installed plugin can run the gates
without a toolkit checkout. Resolve them from this skill's own directory, not
from a repository path.

Both live in this skill's own `scripts/` directory, named here without a
leading path so nobody reads them as the upstream tree they were copied from.

| Script | Purpose | Exit codes |
|--------|---------|------------|
| `redact_secrets.py` | Redacts secrets from Step 0 and Step 0.5 tally text before any durable write. BLOCKING: a failure means do not write. | 0 clean, 1 redaction applied or logic error, 2 config error |
| `metrics_writer.py` | The single safe append point for the metrics tally files. Refuses a symlinked target (CWE-59) and opens with `O_NOFOLLOW` where the platform supports it. | 0 appended, 1 refused or logic error, 2 config error |

`spec-entity-aliases.json` ships in this skill's `data/` directory beside them:
the alias table Step 0.5 uses to normalize topic names. All three are byte-identical copies of their canonical
sources, pinned by `tests/skills/test_spec_bundle_parity.py`, so a toolkit run
and an installed-plugin run cannot disagree.

## Verification

- [ ] Step 0 answered all six forcing questions before any clarification work
- [ ] Step 0.5 ran and its halt criteria were evaluated, not skimmed
- [ ] Every acceptance criterion is numbered, in EARS syntax, and independently pass/fail
- [ ] Requirement names match the Step 1 OntologyFragment canonical names
- [ ] Out of scope and Deferred are both populated, or explicitly empty
- [ ] The buy-vs-build section is filled, or marked N/A with its reason
- [ ] Complexity tier recorded, and the Tier 5 sections present only at Tier 5

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Skipping Step 0 because the problem seems obvious | Every retro citing wasted spec work in the last six months traces to a question this gate forces upfront | Answer the six questions, even quickly |
| Treating Step 0.5 as a formality | Its job is to halt when the question is already answered, and a skim cannot halt | Read the halt criteria in the reference and apply them |
| Acceptance criteria that restate the user story | A criterion nobody can fail is not a criterion | Write each one so a reader can say pass or fail from evidence |
| Speculative requirements | YAGNI: a requirement for a need nobody has yet becomes waste plus a constraint | Specify what is needed now, and record the rest under Deferred |
| Collapsing the output to acceptance criteria alone | Downstream plan and build read the ontology, data model and failure modes, not just the criteria | Mirror the full PRD schema |

## Extension Points

- **New evaluation axis.** Add a row to the axes list and a matching Verification
  checkbox, so the axis is both stated and checked.
- **Different gate content.** Step 0.5 lives in `references/step-0-5-memory-gate.md`;
  a project that searches prior art differently edits that file, not the process.
- **Additional output section.** The Output list is the PRD schema. Adding a
  section there is what makes downstream skills able to rely on it.
