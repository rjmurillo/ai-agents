---
name: spec
description: Define what to build. Transform a problem into testable requirements with acceptance criteria.
argument-hint: problem-statement-or-issue-number
allowed-tools: Task, Skill, Read, Write, Glob, Grep
user-invocable: true
---

<!-- Copilot CLI: project instructions (CLAUDE.md) load via the plugin instructions tree; no include directive needed. -->
Spec: the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message)

If the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message) is empty, ask the user what problem to solve. Do not proceed without a problem statement.

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

### Step 0.5: Memory-First Gate (blocking, runs after Step 0)

After Step 0 passes, surface the backward-looking context the proposer should have read before drafting requirements. Step 0 asks "is this work demanded?" Step 0.5 asks "do we already know why the current state is the way it is?" Both gates fire, in order. The `memory-gate` skill declares the gate as BLOCKING under its `## Memory-First Gate (BLOCKING)` section ("Before changing existing systems, you MUST..."); this section wires it into `/spec`.

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

1. Trim leading and trailing whitespace.
2. Strip leading path separators (`/`, `\`) AND leading dots (`.`).
3. Lowercase the string.
4. Collapse internal separator runs (whitespace, `-`, `_`) to a single hyphen, so `spec pipeline`, `spec-pipeline`, and `spec_pipeline` all normalize to `spec-pipeline`.
5. Look up the result of rule 4 in `.agents/dictionaries/spec-entity-aliases.json` (exact match on the normalized string against the `aliases` keys). On a hit, substitute the canonical value; on a miss, keep the rule-4 result unchanged. This collapses known synonyms (for example `memory-skill` to `memory`, `spec` to `spec-pipeline`) so distinct names for the same entity search as one topic. Adjudication and matching use the post-substitution canonical string.

Example: `.claude/commands/spec.md` normalizes to `claude/commands/spec.md` (rule 2 strips the leading dot and any leading slashes); this string is not an alias key, so rule 5 leaves it unchanged. `spec pipeline` normalizes to `spec-pipeline` after rule 4; `spec` normalizes to `spec` after rule 4, then rule 5 substitutes the canonical `spec-pipeline`, so both resolve to the same topic.

The agent lists the derived topics explicitly in the Step 0.5 preamble before running any searches. Auto-mode adjudication (defined under entity discovery below) compares discovered entity names against Q answers using the same normalization.

#### Step 0.5 skill invocation sequence

Invoke the three skills in order. Each emits content into a named subsection of the PriorArtBlock.

1. **chestertons-fence (frame)**. Invoke `skill: "chestertons-fence"` with `target` set to the Q3 system path and `change` set to the Q4 wedge description. The skill runs git archaeology, PR/ADR search, and dependency analysis on the target. Output (PRESERVE | MODIFY | REPLACE | REMOVE recommendation plus rationale) feeds the `### Direct prior art from memory` subsection.
2. **memory (point search)**. For each topic from the topic-extraction step, invoke the memory skill via `skill: "memory"` with at minimum 3 distinct query variants per topic. The skill internally calls `search_memory.py`. Distinct queries share no significant token roots; for example, for topic `spec-pipeline`: `spec pipeline`, `spec command BLOCKING`, `clarification gate why`. Result entries with non-zero matches feed the `### Direct prior art from memory` subsection.

   **Invocation contract (security)**: the canonical flow is `skill: "memory"`, which already passes topics via argv-vector internally. If the agent's environment lacks the `Skill` tool and must invoke the script directly as a fallback, resolve `search_memory.py` in this order: (1) `<skill_dir>/../memory/scripts/search_memory.py`, where `<skill_dir>` is the base directory printed when this spec skill loads; (2) `.claude/skills/memory/scripts/search_memory.py`, only after confirming the current repo is this toolkit source checkout. If neither path exists, emit a coverage note naming both paths tried and skip the direct memory point-search fallback. When invoking the resolved script, the agent MUST use an argv list, not shell string concatenation: `subprocess.run(["python3", resolved_search_memory_py, topic], shell=False, ...)`. String concatenation of topics into a shell command line is forbidden because Q3+Q4 entity strings are author-controlled and the topic normalization rule does not strip shell metacharacters. CWE-78 (OS Command Injection) applies. If the agent cannot use either the Skill wrapper OR argv-vector invocation, it MUST first reject any topic matching `[^\w\-\./ ]` and emit a coverage note explaining the rejection.
3. **exploring-knowledge-graph (traversal)**. Invoke `skill: "exploring-knowledge-graph"` with the topic list. Depth matches ProvisionalTier:

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
| Forgetful MCP unavailable for exploring-knowledge-graph | Skip the skill (no fallback exists). Emit coverage note: "exploring-knowledge-graph skipped: Forgetful MCP unavailable." Continue. |
| Memory search returns 0 results for a topic after at minimum 3 distinct queries | Emit coverage note for that topic: "no results for `<topic>` after 3 distinct queries; absence of evidence, not evidence of absence." Not a halt. |

None of the above failures halt Step 0.5. They are recorded in the coverage notes subsection so Step 9 check 9d can distinguish "search ran and found nothing" from "search did not run".

#### Step 0.5 entity adjudication

When `exploring-knowledge-graph` discovers an entity or project name that does not appear in Step 0 Q1, Q3, or Q4 (after applying the topic normalization above), the proposer adjudicates each discovered entity as one of: `in-scope`, `out-of-scope`, or `blast-radius`.

- `in-scope`: the entity is acknowledged as part of the spec's scope; record name and one-line relationship to the spec.
- `out-of-scope`: the entity is deliberately excluded; record name and one-line reason.
- `blast-radius`: the entity is connected but the proposer did not previously acknowledge it; record name and one-line risk note.

In auto-mode (no human present), the agent applies topic normalization rules 1-5 to the discovered entity name. For each Q1+Q3+Q4 answer, it applies rules 1-4 to the full answer, splits the normalized answer on `-` to recover its token sequence, then evaluates every contiguous token span after applying rule 5 alias lookup to that span. The agent then performs whole-token equality, not substring match: the discovered entity matches a Q answer only when the entity's canonical normalized value equals a canonicalized contiguous token span inside that answer. A single-token alias such as `spec` can therefore match discovered `spec-pipeline`, and a multi-token alias such as `spec command` can match the same entity. Case-insensitivity is already handled by rule 3 (lowercase) of the normalization, so no separate case fold is applied at match time. A match resolves the entity as `in-scope` automatically. No match resolves the entity as `blast-radius` (conservative). A human proposer in a later turn may override blast-radius classifications that auto-mode conservatively assigned.

Whole-token equality closes the substring bypass (CWE-863, broken access control). Under the old substring rule, a token-rich Q1 such as `auth-service payment-service billing-service` (normalized to `auth-service-payment-service-billing-service`) made almost any short discovered name "match" as a substring, so genuinely connected blast-radius entities resolved to `in-scope` and never counted toward the halt threshold. Worked example with the token rule: discovered `service-mesh` (tokens `service`, `mesh`) does NOT match that answer, because `service mesh` never appears as a contiguous token run; the lone `service` tokens are followed by `payment`/`billing`, not `mesh`. Discovered `auth-service` (tokens `auth`, `service`) DOES match, because `auth service` is a contiguous token run at the answer's head.

The blast-radius halt threshold differs by mode:

| Mode | Blast-radius count to trigger halt |
|---|---|
| Human (proposer adjudicates each entity) | 2 or more |
| Auto (whole-token equality only) | 3 or more |

The halt itself, the metrics tally, and the supplemental traversal hook are defined in the `spec-generator` skill's `references/spec-prior-art-schema.md`.

The PriorArtBlock output schema, halt criteria, halt block format, supplemental traversal hook, metrics tally, and process steps 1 through 9 are in the `spec-generator` skill's `references/spec-prior-art-schema.md`.

   - **Check 9e, Operating-model drift (Tier 5 only)**:
     - Applies only when the spec is Tier 5 and Step 1 invoked `work-operating-model` (the "Operating Model Context" section is present in the PRD). For Tier 1-4, this check is N/A and does not gate.
     - PASS: the spec's proposed implementation is consistent with the operating model elicited at Step 1 (decision rights, communication patterns, work intake, conflict resolution, retrospection).
     - FAIL if the proposed implementation contradicts the elicited operating model (for example, it assumes decision rights the elicited model places elsewhere). On FAIL: cite the contradicting operating-model layer and the PRD element that conflicts; halt and require either a spec revision or an explicit operating-model amendment.

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
