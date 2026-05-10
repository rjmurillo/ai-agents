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

**Tally instruction**: after each Step 0 evaluation (whether pass or halt), append one line to `.agents/sessions/STEP-0-METRICS.md`. Create the file lazily if absent, with header line `# Step 0 Metrics (one line per /spec invocation)`. Each tally line: `<ISO-8601 timestamp> | <pass|fail> | <halt-trigger-or-none> | <halt-question-or-none>`. Absence of the file does not block `/spec`; the tally is review-only data for the kill criteria above.

**Archival policy**: after each kill-criteria review (every 30 invocations or when a kill criterion fires, whichever comes first), rotate the tally file: rename `.agents/sessions/STEP-0-METRICS.md` to `.agents/sessions/STEP-0-METRICS-YYYYMMDD.md` (using the review date) and start a fresh file with the same header. The rotated file is the audit trail for that review window. The active file SHALL NOT exceed 100 entries before rotation.

---

### Step 0.5: Memory-First Gate (blocking, runs after Step 0)

After Step 0 passes, surface the backward-looking context the proposer should have read before drafting requirements. Step 0 asks "is this work demanded?" Step 0.5 asks "do we already know why the current state is the way it is?" Both gates fire, in order. The memory skill at `.claude/skills/memory/SKILL.md` declares the Memory-First Gate as BLOCKING under the `### Memory-First Gate (BLOCKING)` section ("Before changing existing systems, you MUST..."); this section wires it into `/spec`.

The gate composes three skills in sequence: `chestertons-fence` (frame: do not change without understanding why), `memory` (point-search prior decisions), `exploring-knowledge-graph` (multi-hop traversal of connected entities). Each answers a distinct question; the three layered together form the "Prior Art / Constraints" output that Step 6 carries into the PRD as its first section.

#### Step 0.5 ProvisionalTier (auto-classified, no user prompt)

Compute ProvisionalTier as `max(hours_tier, entity_tier)` from Step 0 answers. Used to depth-gate the knowledge-graph traversal without re-asking the proposer.

Hours extraction: scan Q4 for a numeric estimate followed by `hour`, `hours`, `h`, `hr`, `hrs`, `day`, `days`, `week`, or `weeks` (case-insensitive). Days multiply by 8; weeks multiply by 40. If no numeric estimate is found, default `hours_tier = 2`.

Hours mapping (upper bounds strictly less-than; 8h falls in Tier 3, not Tier 2):

| Q4 estimate | hours_tier |
|---|---|
| Less than 2 hours | 1 |
| 2 to less than 8 hours | 2 |
| 8 to less than 40 hours | 3 |
| 40 to less than 160 hours | 4 |
| 160 hours or more | 5 |

Entity count: count distinct named entities, files, or system components mentioned in Q3 and Q4 answers (after normalization defined below). Map:

| Distinct named entities in Q3+Q4 | entity_tier |
|---|---|
| 1 | 1 |
| 2 to 3 | 2 |
| 4 to 7 | 3 |
| 8 to 15 | 4 |
| More than 15 | 5 |

ProvisionalTier = `max(hours_tier, entity_tier)`. Step 3 may classify the actual tier higher; if the upgrade crosses a phase boundary (i.e., `phases_needed(actual_tier) > phases_needed(provisional_tier)`), append a supplemental sub-block (defined in the supplemental traversal hook section below).

#### Step 0.5 topic extraction

Topics are derived mechanically from Q3 and Q4 named entities. One topic per distinct entity. Normalization, applied in order:

1. Strip leading path separators (`/`, `\`) AND leading dots (`.`).
2. Lowercase the string.
3. Trim leading and trailing whitespace.
4. Collapse internal separator runs (whitespace, `-`, `_`) to a single hyphen, so `spec pipeline`, `spec-pipeline`, and `spec_pipeline` all normalize to `spec-pipeline`.

Example: `.claude/commands/spec.md` normalizes to `claude/commands/spec.md` (rule 1 strips the leading dot and any leading slashes). `spec pipeline` normalizes to `spec-pipeline`. These are distinct topics.

The agent lists the derived topics explicitly in the Step 0.5 preamble before running any searches. Auto-mode adjudication (defined under entity discovery below) compares discovered entity names against Q answers using the same normalization.

#### Step 0.5 skill invocation sequence

Invoke the three skills in order. Each emits content into a named subsection of the PriorArtBlock.

1. **chestertons-fence (frame)**. Invoke `Skill(skill="chestertons-fence")` with `target` set to the Q3 system path and `change` set to the Q4 wedge description. The skill runs git archaeology, PR/ADR search, and dependency analysis on the target. Output (PRESERVE | MODIFY | REPLACE | REMOVE recommendation plus rationale) feeds the `### Direct prior art from memory` subsection.
2. **memory (point search)**. For each topic from the topic-extraction step, invoke the memory skill via `Skill(skill="memory")` with at minimum 3 distinct query variants per topic. The skill internally calls `search_memory.py`. Distinct queries share no significant token roots; for example, for topic `spec-pipeline`: `spec pipeline`, `spec command BLOCKING`, `clarification gate why`. Result entries with non-zero matches feed the `### Direct prior art from memory` subsection.

   **Invocation contract (security)**: the canonical flow is `Skill(skill="memory")`, which already passes topics via argv-vector internally. If the agent's environment lacks the `Skill` tool and must invoke the script directly as a fallback, the agent MUST use an argv list, not shell string concatenation: `subprocess.run(["python3", ".claude/skills/memory/scripts/search_memory.py", topic], shell=False, ...)`. String concatenation of topics into a shell command line is forbidden because Q3+Q4 entity strings are author-controlled and the topic normalization rule does not strip shell metacharacters. CWE-78 (OS Command Injection) applies. If the agent cannot use either the Skill wrapper OR argv-vector invocation, it MUST first reject any topic matching `[^\w\-\./ ]` and emit a coverage note explaining the rejection.
3. **exploring-knowledge-graph (traversal)**. Invoke `Skill(skill="exploring-knowledge-graph")` with the topic list. Depth matches ProvisionalTier:

| ProvisionalTier | Phases run | Effect |
|---|---|---|
| 1 or 2 | Phases 1-2 (shallow) | Semantic entry plus 1-hop memory expansion |
| 3 | Phases 1-4 (medium) | Adds entity discovery and entity relationships |
| 4 or 5 | Phases 1-5 (deep) | Adds entity-linked memories |

Discovered entities and projects feed the `### Connected context from exploring-knowledge-graph` subsection.

#### Step 0.5 degradation rules

| Failure | Behavior |
|---|---|
| `chestertons-fence` skill unavailable | Emit `### Coverage notes` entry: "chestertons-fence unavailable; git archaeology skipped; confidence low." Continue. |
| Forgetful MCP unavailable for memory | Degrade to Serena-only via the existing `search_memory.py --lexical-only` fallback. Emit coverage note: "Forgetful MCP unavailable; Serena-only search; results may be incomplete." Continue. |
| Forgetful MCP unavailable for exploring-knowledge-graph | Skip the skill (no fallback exists). Emit coverage note: "exploring-knowledge-graph skipped: Forgetful MCP unavailable." Continue. |
| Memory search returns 0 results for a topic after at minimum 3 distinct queries | Emit coverage note for that topic: "no results for `<topic>` after 3 distinct queries; absence of evidence, not evidence of absence." Not a halt. |

None of the above failures halt Step 0.5. They are recorded in the coverage notes subsection so Step 9 check 9d can distinguish "search ran and found nothing" from "search did not run".

#### Step 0.5 entity adjudication

When `exploring-knowledge-graph` discovers an entity or project name that does not appear in Step 0 Q1, Q3, or Q4 (after applying the topic normalization above), the proposer adjudicates each discovered entity as one of: `in-scope`, `out-of-scope`, or `blast-radius`.

- `in-scope`: the entity is acknowledged as part of the spec's scope; record name and one-line relationship to the spec.
- `out-of-scope`: the entity is deliberately excluded; record name and one-line reason.
- `blast-radius`: the entity is connected but the proposer did not previously acknowledge it; record name and one-line risk note.

In auto-mode (no human present), the agent applies the four-rule normalization defined under topic extraction above (strip leading dots and path separators, lowercase, trim, collapse internal separator runs to single hyphens) to BOTH the discovered entity name AND the Q1+Q3+Q4 answers, then performs case-insensitive substring match. A match resolves the entity as `in-scope` automatically. No match resolves the entity as `blast-radius` (conservative). A human proposer in a later turn may override blast-radius classifications that auto-mode conservatively assigned.

The blast-radius halt threshold differs by mode:

| Mode | Blast-radius count to trigger halt |
|---|---|
| Human (proposer adjudicates each entity) | 2 or more |
| Auto (string-match only) | 3 or more |

The halt itself, the metrics tally, and the supplemental traversal hook are defined in the next section of this gate.

#### Step 0.5 PriorArtBlock output schema

The gate emits a Markdown block embedded into the PRD as its first section, named `## Prior Art / Constraints`. The block has three required subsections; each must be present even if empty (an empty subsection contains a coverage note, not blank text):

```markdown
## Prior Art / Constraints

### Direct prior art from memory

- ADR-NNN ("[title]"): [one-line summary]. Relevance: [one-line]. Decision: honor | adapt | propose-amend with rationale.
- Episode YYYY-MM-DD ("[title]"): [one-line]. Relevance: [one-line]. Decision: [as above].
- Causal pattern: [name]. Relevance: [one-line]. Decision: [as above].
- (chestertons-fence recommendation: PRESERVE | MODIFY | REPLACE | REMOVE; rationale.)

### Connected context from exploring-knowledge-graph

- Connected entity: [normalized name, type]. Adjudication: [in-scope | out-of-scope | blast-radius]. Note: [one-line].
- Linked project: [name]. Why it matters: [one-line].
- (Traversal depth: shallow | medium | deep, matched to Tier N.)

### Coverage notes

- [Topic `<name>`]: [searched N variants; results: count]. Confidence: [high if N >= 3 distinct queries with no shared roots, low otherwise].
- [Skill or MCP availability notes per the degradation rules above.]
```

This block is the input to Step 9 check 9d, which verifies that at least one subsection has either evidence content or a justified coverage note.

#### Step 0.5 halt criteria

Halt triggers fire BEFORE the PriorArtBlock is emitted to the PRD. When any halt fires, the gate emits a machine-readable halt block (defined below) and STOPs. Do not proceed to Step 1.

| ID | Trigger |
|---|---|
| H6 | Spec proposes removing an ADR constraint and memory search returned no result for the constraint name. |
| H7 | Spec proposes bypassing a documented protocol and memory search returned no result for the protocol name plus "why". |
| H8 | Spec proposes deleting more than 100 lines of existing code and memory search returned no result for the component plus "purpose". |
| H9 | Spec proposes refactoring a component flagged complex (cyclomatic > 10) and memory search returned no result for the component plus "edge case". |
| H10 | Spec proposes changing behavior of a validator, linter, hook, or shared infrastructure component without prior-art citation in PriorArtBlock. |
| H11 | Adjudicated blast-radius entities meet or exceed the threshold (human mode: 2; auto mode: 3). |

H11 is the most common trigger; the H6-H10 set encodes Memory-First Gate's documented BLOCKING conditions (`.claude/skills/memory/SKILL.md` lines 78-85).

#### Step 0.5 halt block format

Every halt MUST emit a fenced code block with info-string `step0_5-halt` containing exactly five `key: value` lines.

H11 (blast-radius) example, citing REQ-008 AC-09:

````
```step0_5-halt
trigger: H11
check: AC-09 blast-radius adjudication
evidence: 3 unmatched entities marked blast-radius (entity-a, entity-b, entity-c)
test_failed: blast-radius count >= auto-mode threshold (3)
deferral: Revise Step 0 Q4 to name blast-radius entities or add explicit out-of-scope entries; then re-run Step 0.5.
```
````

H6 (Memory-First BLOCKING change type) example, citing REQ-008 AC-13. H7-H10 use the same shape with the corresponding trigger ID and BLOCKING-type description:

````
```step0_5-halt
trigger: H6
check: AC-13 memory-first BLOCKING change type
evidence: spec proposes removing ADR-040 constraint; memory search "ADR-040" returned no results across 3 query variants
test_failed: REQ-008 AC-13 trigger H6 (remove ADR constraint with no memory hit)
deferral: Cite the memory entry that authorizes removing this constraint, OR amend the spec to preserve the constraint, OR escalate via ADR review; then re-run Step 0.5.
```
````

Field semantics:

1. `trigger`: one of `H6`, `H7`, `H8`, `H9`, `H10`, `H11`.
2. `check`: short name of the failed check, citing the AC ID (`AC-09` for H11; `AC-13` for H6-H10).
3. `evidence`: factual record of what triggered the halt (matched entity names, search query that returned no result, etc.); single line, escape newlines as `\n`.
4. `test_failed`: name the rule that was violated.
5. `deferral`: a single-line instruction telling the proposer how to unblock and re-run.

Free-form prose halts that omit the `step0_5-halt` info-string are non-conforming and SHALL be re-emitted in this format. Downstream callers (orchestrators, review skills, CI gates) parse this block by its info-string. The Step 0.5 halt block is structurally identical to Step 0's `step0-halt` block (same five fields) except for the info-string and the `check` field replacing `question`.

#### Step 0.5 supplemental traversal hook (cross-step)

Step 3 (Tier classification) may set the actual tier higher than ProvisionalTier. When the actual tier requires more knowledge-graph phases than were already run, run the additional phases as a supplemental traversal and append the results to PriorArtBlock as a `### Supplemental (Phase N)` sub-block. Do NOT replace the original subsections.

Trigger formula:

```
phases_needed(T) = 2  if T <= 2
phases_needed(T) = 4  if T == 3
phases_needed(T) = 5  if T >= 4

run_supplemental = (actual_tier > provisional_tier) AND (phases_needed(actual_tier) > phases_needed(provisional_tier))
```

Example: ProvisionalTier was 2 (ran Phases 1-2 shallow). Step 3 classifies actual tier as 4. `phases_needed(4) = 5` and `phases_needed(2) = 2`, so run Phases 3-5 as supplemental and append `### Supplemental (Phase 5)` listing the new entity-linked memories surfaced. The original `### Connected context from exploring-knowledge-graph` subsection is preserved unchanged; the supplemental sub-block sits beneath it.

#### Step 0.5 metrics tally

After every Step 0.5 evaluation (whether pass or halt), append one line to `.agents/sessions/STEP-0.5-METRICS.md`. Create the file lazily if absent, with header line `# Step 0.5 Metrics (one line per /spec invocation)`. Each tally line uses the canonical `YYYY-MM-DDTHH:MM:SSZ` UTC timestamp form (no offset, no fractional seconds; the `parse_tally_line` helper at `tests/commands/step0_5_parser.py` enforces this exact shape):

```
<YYYY-MM-DDTHH:MM:SSZ> | <pass|fail> | <halt-trigger-or-none> | <halt-check-or-none>
```

Examples:

```
2026-05-10T04:30:00Z | pass | none | none
2026-05-10T05:15:00Z | fail | H11 | AC-09 blast-radius adjudication
2026-05-10T05:20:00Z | fail | H6 | AC-13 memory-first BLOCKING change type
```

Absence of the file does not block `/spec`; the tally is review-only data for the kill criteria.

**Archival policy**: rotation fires when the active file reaches 100 entries (the canonical trigger per REQ-008 line 92 and the failure-mode table at REQ-008 line 122). On rotation: rename `.agents/sessions/STEP-0.5-METRICS.md` to `.agents/sessions/STEP-0.5-METRICS-YYYYMMDD.md` (rotation date) and start a fresh file with the same header. The 30-invocation cadence governs the SEPARATE kill-criteria review schedule and does not by itself trigger rotation; if a kill criterion fires before 100 entries are reached, the gate is loosened or removed in a follow-up PR (the file may rotate at that point if the change warrants).

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
9. Task(subagent_type="critic"): You are a skeptical reviewer. Run a pre-mortem: assume this spec ships and fails. What broke first? What was missing? Then run four binary checks against the final PRD; the critic SHALL NOT return APPROVED while any of 9a/9b/9c/9d is FAIL. Checks 9a/9b/9c validate Step 0 (forward-looking demand) drift. Check 9d validates Step 0.5 (backward-looking prior art) elicitation.

   - **Check 9a, Demand Reality drift**:
     - PASS: PRD acceptance criteria, user stories, OR success metric reference at least one entity (person, team, system, metric, ticket, file path) named in Step 0 Q1.
     - FAIL otherwise. On FAIL: cite Q1 entities and the PRD's current entities verbatim.
   - **Check 9b, Desperate Specificity drift**:
     - PASS: PRD user stories or acceptance criteria still treat the Q3-named blocked entity as the primary unblocking target.
     - FAIL if (a) the spec's primary user shifted to a different audience, OR (b) Q3's named entity does not appear in the PRD. On FAIL: cite Q3's entity and the PRD's current primary user verbatim.
   - **Check 9c, Narrowest Wedge drift**:
     - PASS: every PRD acceptance criterion either traces to the Q4 wedge or narrows it.
     - FAIL if any acceptance criterion adds scope beyond Q4 without a documented wedge revision. On FAIL: cite Q4 verbatim and list the AC entries that exceed the wedge.
   - **Check 9d, Prior Art / Constraints elicitation**:
     - PASS: the PRD contains a "## Prior Art / Constraints" section with at least one sub-section ("### Direct prior art from memory", "### Connected context from exploring-knowledge-graph", or "### Coverage notes") that has either evidence content or a justified coverage note.
     - FAIL conditions (any one triggers FAIL): (a) the section is absent; (b) all three sub-sections are empty AND no coverage note is present; (c) the Step 0.5 BLOCK itself in `.claude/commands/spec.md` (between the `### Step 0.5: Memory-First Gate` heading and the next `\n---\n` delimiter) contains the partial-implementation guard token (string `step0.5:incomplete-without-2b` wrapped in HTML-comment delimiters). Note: the same token appears in this 9d FAIL clause as documentation; check 9d MUST scope its match to the Step 0.5 block boundaries to avoid a tautological self-trigger from this Step 9 text.
     - On FAIL: surface as a blocking finding. The critic SHALL NOT return APPROVED while check 9d is FAIL.

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
