#### Step 0.5 PriorArtBlock output schema

The gate emits a Markdown block embedded into the PRD as its first section, named `## Prior Art / Constraints`. The h2 heading MUST be exactly `## Prior Art / Constraints`; any trailing parenthetical (for example `## Prior Art / Constraints (auto-generated)`) is optional metadata. Step 9 check 9d matches by substring (`## Prior Art / Constraints`), so a trailing parenthetical does not break the check. The block has three required subsections; each must be present even if empty (an empty subsection contains a coverage note, not blank text):

```markdown
## Prior Art / Constraints

### Direct prior art from memory

- ADR-NNN ("[title]"): [one-line summary]. Relevance: [one-line]. Decision: honor | adapt | propose-amend with rationale.
- Episode YYYY-MM-DD ("[title]"): [one-line]. Relevance: [one-line]. Decision: [as above].
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

**Redaction pre-emit (BLOCKING)**: the `evidence` field carries the factual record that triggered the halt, which can include matched entity names, a quoted memory search, or text pasted from a ticket or log. The emitted block lands in git history (PR descriptions, session logs, metric tallies), so an `evidence` value that quotes `Alice@corp on prod-east-12.internal blocked on Bearer abc...` would disclose a credential, email, or internal hostname for the life of the history (CWE-209 information exposure through a diagnostic message, CWE-532 sensitive data in a log). Before emitting the `step0_5-halt` block, run the `evidence` field through the redactor and emit the redacted form:

```bash
python3 scripts/redact_secrets.py <file>      # or pipe the evidence text on stdin
```
<!-- vendor-portability-exec: scripts/redact_secrets.py -->

In Python: `from redact_secrets import redact; redact(evidence).text`. Matched token shapes (private keys, GitHub/Stripe/AWS/Slack tokens, JWTs, `Bearer` headers, emails, hex secrets of 32 or more chars) become `` `[redacted: <reason>]` ``. This mirrors the Step 0 `answer` redaction rule above; the same `scripts/redact_secrets.py` redactor and `.claude/rules/secret-redaction.md` policy apply. Redaction is a backstop, not a license to collect secrets.

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

After every Step 0.5 evaluation (whether pass or halt), append one line to `.agents/sessions/STEP-0.5-METRICS.md` through the canonical hardened writer `scripts/metrics_writer.py` (`safe_append_tally(path, line)`), not a hand-rolled `open(path, "a")`. The writer rejects a symlink at the tally path (CWE-59 link following), opens with `O_NOFOLLOW` to close the check-then-open race (CWE-367 TOCTOU), and holds an exclusive `flock` so concurrent `/spec` runs do not interleave lines. It creates the file lazily if absent. Write the header line `# Step 0.5 Metrics (one line per /spec invocation)` as the first record when the file is new. Each tally line uses the canonical `YYYY-MM-DDTHH:MM:SSZ` UTC timestamp form (no offset, no fractional seconds; the `parse_tally_line` helper at `tests/commands/step0_5_parser.py` enforces this exact shape):

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

   **Tier 5 operating-model elicitation (work-operating-model)**: when the Step 0.5 ProvisionalTier is 5 (or Step 3 later upgrades the actual tier to 5; in that case run this as a supplemental Step 1 elicitation before Step 6), invoke Skill(skill="work-operating-model") here to run the 5-layer interview against the involved team(s). Tier 5 specs are principal-level cross-team work; they almost always assume an operating model that does not match how the teams actually work. The skill elicits the five layers (decision rights, communication patterns, work intake, conflict resolution, retrospection). Output: an "Operating Model Context" section carried into the PRD. Tier 4 specs do NOT invoke this skill; Tier 4 is single-team architectural, where operating-model mismatch is rare. The elicited model is also read at Step 9 (drift checks): a proposed implementation that contradicts the elicited operating model is a Step 9 halt condition. **Halt condition**: the 5-layer interview reveals the proposing person does not have access to the relevant teams; halt and require sponsorship escalation before continuing.

   #### Step 1 Ontology elicitation (domain-driven design)

   Before the adversarial requirements interview at Step 2, elicit the problem's domain ontology so that every later artifact names the same concepts. Requirements written without an agreed ubiquitous language drift: two requirements call the same entity by two names, an acceptance criterion references a concept no design component owns, and the implementer reconstructs the model from scratch. Eliciting the ontology once, here, fixes the vocabulary the requirements interview, the spec-generator, and the completeness check all reuse. This sub-step does NOT add a new top-level step number: Step 0 First Principles already owns the front of the pipeline, and renumbering downstream steps (which reference each other by number) is forbidden. It is a sub-step of Step 1 (Clarify), and it runs once per `/spec` invocation.

   Elicit answers to the seven ontology prompts, in order. Each is grounded in the domain-driven-design reference in `software-engineering-library`:

   | Prompt | Ontology question |
   |---|---|
   | **O1 Entities** | What are the core domain entities (things identified by stable identity) and value objects (things identified by their values)? Name each. |
   | **O2 Ubiquitous language** | For each entity from O1, what is the single canonical name the team uses? Record synonyms to retire so two requirements never name one concept two ways. |
   | **O3 Relationships** | How do the entities relate (owns, references-by-identity, composed-of, derived-from)? One line per relationship. |
   | **O4 Aggregate boundaries** | Which entities cluster under a single aggregate root that owns their invariants and is the unit of transactional change? Name each aggregate root. |
   | **O5 Decision rules** | What domain rules or invariants must hold, and which entity or aggregate root enforces each? These trace forward to design decision rules. |
   | **O6 Bounded-context boundaries** | Which bounded context does this work live in? Where does its model stop and another context's model begin (the seam that needs translation)? |
   | **O7 Open ontology questions** | What concepts are still ambiguous or contested? Record them as open questions rather than guessing a wrong abstraction (CVA: the greatest risk is the wrong abstraction). |

   **Output (OntologyFragment)**: write the seven answers to `.agents/specs/ontology/<feature-slug>.md`, where `<feature-slug>` is the kebab-case feature name (the same slug the spec-generator uses for `REQ-NNN-{slug}.md`). Create the parent directory `.agents/specs/ontology/` lazily if absent (it is project-only and may not exist on a fresh checkout or vendored install). The fragment uses seven `## O1..O7` subheads, each containing the verbatim answer. This OntologyFragment is carried into Step 2 (the requirements interview reads it so questions reuse the canonical names), into Step 6 (spec-generator references entities by their O2 canonical name in REQ, DESIGN, and TASK artifacts and renders an `## Ontology` body section), and into the CI completeness check (which verifies every entity in `.agents/specs/requirements/REQ-NNN-{slug}.md`, `.agents/specs/design/DESIGN-NNN-{slug}.md`, and `.agents/specs/tasks/TASK-NNN-{slug}.md` appears in the OntologyFragment and every design decision rule traces to an O5 source).

   **Auto-mode behavior**: under auto-mode invocation (no human elicitation possible), the agent MAY populate the seven prompts from the source artifact (issue body, PR description, linked design doc) only when that artifact names the entities and rules verbatim. Free-form synthesis of a domain model the agent invents is prohibited; an invented ontology is worse than none because it stamps a wrong abstraction with false authority. When the source artifact lacks the named concepts, emit each unanswered prompt as an O7 open question and continue; the OntologyFragment is never a halt.

   **Degradation (empty or no-entity feature)**: a feature with no domain entities (a pure config change, a one-line doc fix, a formatting tweak) has a trivial ontology. Write the OntologyFragment with O1 set to `none (no domain entities; <one-line reason>)` and the remaining prompts set to `N/A`. A trivial OntologyFragment is still emitted so the CI completeness check can distinguish "elicited and found nothing" from "skipped". An empty-entity feature SHALL NOT produce a CI ontology-coverage FAIL: with zero entities in generated REQ, DESIGN, and TASK artifacts, the coverage check is vacuously satisfied.
2. **Run the adversarial requirements interview**: Invoke Skill(skill="requirements-interview") to walk the design tree before any further analysis. Pass the OntologyFragment from Step 1 into the interview so every question uses O2 canonical names and the output PRD includes an `## Ontology` section summarizing O1-O7. The skill grills the user on user stories, data model, integrations, failure modes, security, observability, and scope boundaries. For every question it must propose a recommended answer; if the codebase can answer it (grep the repo first), it does so without asking. Output is a structured PRD that every downstream step consumes. Carry the PRD forward unchanged through steps 3-9; do not drop sections.
3. **Classify complexity tier**: Task(subagent_type="analyst"): Read `.claude/skills/analyze/references/engineering-complexity-tiers.md`. Using the structured PRD from step 2, classify the problem as Tier 1-5 based on scope, ambiguity, cross-team dependencies, and reversibility. Return the tier number, rationale, and recommended spec depth. Use this to calibrate remaining steps:
   - Tier 1-2 (Entry/Mid): Simple acceptance criteria. Skip CVA if single use case.
   - Tier 3 (Senior): CVA analysis required. Cross-team input. Design review gate.
   - Tier 4 (Staff): Alternatives analysis mandatory. ADR required. Stakeholder alignment. Challenge: "can this be decomposed into a simpler tier?"
   - Tier 5 (Principal): Governance review. Multi-org consensus. Re-validate Step 0 Q4 (Narrowest Wedge) in the context of emerged complexity. If the wedge can be narrowed further without losing the unblocking value identified in Q3, narrow it before proceeding. Step 0 Q4 is the canonical wedge question for every tier.

   #### Step 3 problem-domain classification (Cynefin)

   The engineering-tier classification above measures *engineering* complexity (Entry to Principal). It does not measure *problem-domain* complexity. A Tier 2 engineering problem in a Complex domain still needs probe-sense-respond methodology, not "just build it." After the engineering-tier assignment, invoke Skill(skill="cynefin-classifier") to classify the problem domain as Clear, Complicated, Complex, or Chaotic. The two axes are orthogonal; carry both forward.

   Emit a 2D `tier x domain` classification block into the PRD frontmatter so Step 6 (spec-generator) and Step 9 (drift checks) read the same classification:

   ```text
   Engineering tier: N (rationale)
   Problem domain: Clear | Complicated | Complex | Chaotic (rationale)
   Methodology: <derived from the combination>
   ```

   Methodology guidance derives from the combination:

   - Tier 2 + Clear: standard acceptance-criteria spec (CRUD or pure UI).
   - Tier 2 + Complex: probe-sense-respond spec; build the smallest experiment first, then specify the rest from what the experiment reveals.
   - Any tier + Chaotic: halt (see below).

   **Halt condition (Chaotic domain)**: when `cynefin-classifier` classifies the domain as Chaotic, halt and do not proceed to Step 4. A Chaotic domain has no stable cause-and-effect to specify against; specifying before stabilizing bakes in assumptions that the next incident invalidates. Recommend stabilization work first, then re-invoke `/spec` once the domain settles into Complex or Complicated. Emit the recommendation as a single line: "Domain is Chaotic; stabilize before specifying. Re-invoke /spec after the system reaches a steady state." All other domain classifications (Clear, Complicated, Complex) are soft annotations that flow into the PRD; only Chaotic halts.

4. Search for existing solutions in the codebase (grep for related patterns). Use the PRD's Integrations and Data model sections to scope the search.

   #### Step 4 provenance and dependency gates

   Before generating artifacts, run two skills that bracket the buy-vs-build gate (Step 4a): ownership is established first (before Step 4a), then dependency choices are scrutinized second (after Step 4a). They do not run back to back; the Step 4a verdict falls between them, so the numbered order below is logical sequence, not adjacency.

   1. **Ownership first (`analysis-provenance`)**. Before the spec proposes changing any validator, linter, hook, or shared infrastructure component, invoke Skill(skill="analysis-provenance") to identify who owns it. The skill reports provenance as UPSTREAM, LOCAL, VENDOR, or UNKNOWN, plus the owner and last-touched signal. Emit an ownership block carried into the PRD's Prior Art / Constraints section: `<component>: provenance <UPSTREAM|LOCAL|VENDOR|UNKNOWN>; owner <name-or-team-or-none>`. This runs BEFORE Skill(skill="buy-vs-build-framework") at Step 4a: you cannot make a sound build/buy decision about a component until you know whether it is yours to change. **Halt condition**: provenance returns UNKNOWN (no identifiable owner) for a shared component the spec proposes to change; halt and request ownership escalation before continuing.
   2. **Dependency scrutiny (`programming-advisor`)**. When the spec proposes a new external dependency (a library, SaaS, or OSS package), invoke Skill(skill="programming-advisor") to evaluate it. Output: a dependency assessment (maintenance, license, supply-chain, fit) carried into the PRD. This fires after the Step 4a buy-vs-build verdict resolves to build-with-a-dependency or buy; it does not fire when the codebase search at Step 4 already found a usable in-repo solution. **Halt condition**: the buy-vs-build verdict at Step 4a is "buy" but no vendor evaluation was performed; halt and complete the evaluation before generating artifacts.

   Order of operations across Step 4 and Step 4a: provenance (this step, ownership) then buy-vs-build (Step 4a, the build/buy/partner/defer decision) then programming-advisor (this step, dependency scrutiny). Each output is a structured block carried into Step 6 as PRD input.
4a. **Buy-vs-build gate (BLOCKING for new capabilities)**: If the PRD proposes a new capability classified as Context (per Wardley/Moore: undifferentiating support work) or introduces a new module, scanner, validator, or pipeline component, invoke Skill(skill="buy-vs-build-framework") at the **Quick tier** (Phase 1 + Phase 2 lite) before continuing to step 5. The skill must produce: (a) a one-line core-vs-context classification, (b) the existing tools/services evaluated (CodeQL, Dependabot, gh CLI, OSS Scorecard, vendor SaaS, etc.), and (c) an explicit build/buy/partner/defer recommendation. **Skip this step only for**: pure bug fixes, doc-only changes, refactors with no new capability surface, or work that extends an already-approved capability without adding a new tool/scanner/validator. Record the gate outcome in the PRD under a new `Buy-vs-build decision` section. If the recommendation is buy/partner/defer, halt the spec and route the user to the recommended path before generating REQ/DESIGN/TASK artifacts. Failure pattern this gate prevents: action-matching to implementation skills (e.g., `security-detection`) without challenging the build decision itself, as in #1843 where 9 hours were spent reimplementing a CWE-22 scanner CodeQL already provides. See `.agents/retrospective/2026-05-06-action-matching-over-decision-gating.md`.
5. **CVA analysis (conditional)**: If the complexity tier is 3-5, or Tier 1-2 with multiple use cases, invoke Skill(skill="cva-analysis"): identify commonalities across the PRD's user stories, then variabilities, then relationships. Otherwise (Tier 1-2 single-use-case), set `CVA summary: N/A (single-use-case Tier 1-2)` and proceed.
6. **Formalize the PRD into durable artifacts**:

   **First ask the multi-site opt-in prompt.** Before invoking spec-generator, ask the user verbatim:

   ```text
   Is this a multi-site contract change? (y/n)
   ```

   Record the answer as `multi_site_opt_in` (boolean). The Co-change checklist subsection below reads this flag to decide whether to emit the checklist via the opt-in branch. The prompt is mandatory; do not skip it.

   Then invoke Skill(skill="spec-generator"). Pass every PRD section from step 2 (Problem, User stories, Ontology, Data model, Integrations, Failure modes, Security, Observability, Acceptance criteria, Out of scope, Deferred, Open questions) plus the complexity tier from step 3, the buy-vs-build decision from step 4a (which may be `N/A (bug fix / doc / refactor)` for skipped runs), the CVA summary from step 5 (which may be the `N/A` placeholder for skipped runs), the `multi_site_opt_in` flag from this step, and the OntologyFragment from the Step 1 ontology elicitation (the contents of `.agents/specs/ontology/<feature-slug>.md`). The spec-generator reads the OntologyFragment so every emitted requirement references each entity by its O2 canonical name, and renders an `## Ontology` section in the requirement body (the section contract is in `.claude/skills/spec-generator/SKILL.md`). Do not let a requirement introduce an entity that is absent from the OntologyFragment; if the interview surfaced a new concept, add it to the OntologyFragment first (O1/O2) so the vocabulary stays single-sourced and the CI completeness check has one canonical vocabulary source. The spec-generator skill reads the bundled schema, writes, and validates each file:
   - `.agents/specs/requirements/REQ-NNN-{slug}.md` (one per requirement, EARS syntax)
   - `.agents/specs/design/DESIGN-NNN-{slug}.md`
   - `.agents/specs/tasks/TASK-NNN-{slug}.md`
   The full PRD must be passed as input so the spec-generator skill does not re-ask questions the interview already answered. Acceptance criteria use EARS syntax (`WHEN ... THE SYSTEM SHALL ... SO THAT ...`). The skill validates every emitted file with `validate_spec_frontmatter.py` and does not report completion until it exits 0; this closes the frontmatter enum drift the validator was added to catch.

   #### Step 6 Security section (threat-modeling)

   Do not hand-wave the PRD's Security section. Invoke Skill(skill="threat-modeling") and map its structured output into the section. The skill runs the OWASP Four-Question Framework by default (STRIDE is an acceptable substitute when the team prefers it). It produces:

   - Identified threats (each named, not "consider security implications").
   - Trust boundaries (each named).
   - Abuse cases (each named).
   - Recommended mitigations, each mapped to an acceptance criterion.

   That structured output replaces the Security subsection prose. **Tier-gating**: threat modeling is mandatory at Tier 3+ (where an ADR or design doc is also produced). Tier 1-2 specs may skip it with an explicit "no security surface" justification recorded in the Security section; most Tier 1-2 specs are CRUD or pure UI, and over-applying threat modeling there produces noise. **Halt condition**: `threat-modeling` returns "no threats identified" for a spec that touches shared infrastructure; flag for analyst review (suspicious; most specs touching shared infra have at least one threat).

   #### Step 6 Observability section (slo-designer)

   Do not hand-wave the PRD's Observability section. Invoke Skill(skill="slo-designer") and map its structured output into the section. The skill produces:

   - SLIs (Service Level Indicators): what is measured and how.
   - SLOs (Service Level Objectives): numeric targets with rationale.
   - Error budgets: derived from the SLOs.
   - Alert thresholds: derived from the error budgets.

   That structured output replaces the Observability subsection prose. **Tier-gating**: SLO design is mandatory at Tier 3+. Tier 1-2 specs may use the lightweight "what metric proves this works" formulation instead of a full SLO set. **Halt condition**: `slo-designer` returns SLIs without measurable definitions; flag for analyst review.

   #### Step 6 Tier 4-5 ADR generation and review (BLOCKING)

   For Tier 4-5 specs, an ADR is mandatory and its review is BLOCKING (AGENTS.md fires the adr-review skill on any ADR create/edit). After the REQ/DESIGN/TASK files are generated:

   1. Invoke Skill(skill="adr-generator") to produce `ADR-NNN-{slug}.md`. The ADR cross-references the driving REQ; the REQ cross-references the ADR as the architectural decision it implements. Maintain this bidirectional ADR<->REQ link: the ADR names the REQ id in its context, and the REQ names the ADR id in its rationale.
   2. Immediately invoke Skill(skill="adr-review") as a BLOCKING gate. The verdict gates the spec from advancing to Step 7. **Halt condition**: `adr-review` returns REQUEST_CHANGES; halt and do not proceed to Step 7 until the ADR is revised and re-reviewed. A second halt fires if the new ADR contradicts an existing ADR (the `doc-accuracy` skill at Step 7 also catches this); resolve the contradiction or amend the existing ADR before continuing.

   Tier scope difference: Tier 4 produces a single-decision ADR (single-team architectural). Tier 5 produces a governance-level ADR with broader impact; the Tier 5 governance review explicitly cites the ADR and the `adr-review` verdict. Tiers 1-3 do NOT auto-generate an ADR (over-application produces ADR sprawl).

   #### Co-change checklist (REQ-012-04, REQ-012-05)

   When the requirement touches a shared token (a regex pattern, an enum value, an exit-code table, a status string) that appears at more than one site, the generated `REQ-NNN-{slug}.md` MUST include a `## Co-change checklist` section listing every site. Verdict-token cascade is the canonical failure mode: a single-token addition can require three or more commits when the implementer discovers missing sites one at a time through bot review. The checklist forces discovery at spec time, not review time.

   Emit the section when EITHER condition holds:

   1. **Opt-in (proposer flag)**: the user answered "yes" to a Step 6 prompt "Is this a multi-site contract change?" earlier in the run.
   2. **Auto-detect (documentation only at this milestone; not enforced in code)**: the PRD scope touches both `scripts/validation/**` AND `.claude/hooks/**` simultaneously, OR Step 0 Q4 mentions a token literal (a regex pattern in backticks, an enum value in ALL_CAPS, a quoted status string). Enforcement of this rule is deferred; the spec author is responsible for emitting the section when the heuristic applies.

   Section placement: after the last `### Acceptance Criteria` subsection and before `### Rationale`. Header is exactly `## Co-change checklist` (level-2, case-sensitive).

   Each entry follows this format, one line per site:

   ```text
   - [ ] {file_path}:{line_or_section} -- {what changes}
   ```

   - `{file_path}` is repo-relative (no leading `/`).
   - `{line_or_section}` is a line number when known, otherwise a section name in quotes.
   - `{what changes}` is a single phrase, not a full sentence.
   - The `-- ` separator is distinct from standard markdown list conventions in this repo and is machine-parseable for future linting.

   Concrete example, from a verdict-token cascade. Adding a new verdict token (for example `NEEDS_REVISION`) to the quality-gate vocabulary requires edits at every site that pattern-matches the existing tokens:

   ```markdown
   ## Co-change checklist

   - [ ] scripts/ai_review_common/verdict.py:"_KNOWN_VERDICT_TOKENS" -- add NEEDS_REVISION to the frozenset
   - [ ] scripts/ai_review_common/verdict.py:"_EXTRACT_VERDICT_PATTERN" -- extend regex alternation
   - [ ] .github/actions/pr-quality-gate/action.yml:"validity" -- add to valid input list
   - [ ] .github/workflows/pr-quality-gate.yml:"blockingVerdicts" -- decide whether to block
   - [ ] .github/workflows/pr-quality-gate.yml:"exit_code" -- map to exit code per ADR-035
   - [ ] .claude/skills/review/references/analyst.md -- document new verdict in axis prose
   - [ ] .claude/skills/review/references/architect.md -- document new verdict in axis prose
   - [ ] .claude/skills/review/references/qa.md -- document new verdict in axis prose
   - [ ] .claude/skills/review/references/security.md -- document new verdict in axis prose
   - [ ] .claude/skills/review/references/devops.md -- document new verdict in axis prose
   - [ ] .claude/skills/review/references/roadmap.md -- document new verdict in axis prose
   - [ ] .github/prompts/pr-quality-gate-analyst.md -- mirror axis prose
   - [ ] .github/prompts/pr-quality-gate-architect.md -- mirror axis prose
   - [ ] .github/prompts/pr-quality-gate-qa.md -- mirror axis prose
   - [ ] .github/prompts/pr-quality-gate-security.md -- mirror axis prose
   - [ ] .github/prompts/pr-quality-gate-devops.md -- mirror axis prose
   - [ ] .github/prompts/pr-quality-gate-roadmap.md -- mirror axis prose
   ```

   Each entry follows the documented contract literally: bare `{file_path}:{line_or_section}` with no backticks. When `{line_or_section}` is not a line number, quote it (for example, `"validity"`). `{what changes}` is a single phrase. The worked example pins the exact byte-level shape that future checklist linters will pattern-match against; do not paraphrase the separator or drop `--`.

   The checklist surfaces 17 sites for a single token. Without it, the implementer discovers each one through a separate bot-review round trip.
7. **Analyst review (doc-accuracy + golden-principles, then gap check)**. Run two skills in sequence before the gap-and-ambiguity check, each gating the spec from advancing to Step 8:

   1. Invoke Skill(skill="doc-accuracy") to scan for contradictions between the spec and existing docs, ADRs, and code. Common case: the spec proposes behavior that contradicts a documented ADR constraint or an existing design doc. **Halt condition**: `doc-accuracy` finds a contradiction with an existing ADR; halt and require an explicit ADR amendment proposal before continuing (do not silently override the ADR).
   2. Invoke Skill(skill="golden-principles") to scan the spec's design proposals for SOLID, KISS, DRY, and YAGNI violations (CLAUDE.md already declares these as standards; making them explicit here catches violations before they ship). **Halt condition**: `golden-principles` finds a violation; halt and require either a justification recorded in the PRD or a design change.

   Then Task(subagent_type="analyst"): You are a requirements analyst. Your job is to find gaps, ambiguities, and untestable requirements. Review every PRD section, not just acceptance criteria. For each requirement, ask: can this be verified pass/fail? Flag anything vague. Integrate the `doc-accuracy` and `golden-principles` findings into your verdict; these checks are additive to the existing gap-and-ambiguity review, not a replacement for it.
8. Invoke Skill(skill="decision-critic"): challenge assumptions before committing
9. Task(subagent_type="critic"): You are a skeptical reviewer. **For the pre-mortem portion, invoke Skill(skill="pre-mortem") explicitly** rather than running an ad-hoc pre-mortem inline. The skill runs prospective-hindsight analysis with a structured methodology: assume the spec ships and fails, then work backward. Map its output into the PRD's Failure Modes section: failure scenarios (specific), failure modes (categorized), early warning signs (named), and prevention measures. **Pre-mortem halt condition**: if `pre-mortem` identifies a failure mode the spec does not address (no mitigation and no acceptance criterion that checks for it), flag it for the proposer. The pre-mortem skill is additive; the four binary drift checks below still run.

   Then run the binary drift checks against the final PRD; the critic SHALL NOT return APPROVED while any of 9a/9b/9c/9d is FAIL, and for Tier 5 specs the critic SHALL NOT return APPROVED while 9e is FAIL. Checks 9a/9b/9c validate Step 0 (forward-looking demand) drift. Check 9d validates Step 0.5 (backward-looking prior art) elicitation. For Tier 5 specs, also run the operating-model drift check (9e below).

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
     - Evaluate 9d independently from ontology checks: missing or present `## Ontology` and `## Data model` content cannot satisfy, fail, or distract from the required `## Prior Art / Constraints` section. Locate the literal prior-art section first; if it exists with the required subsection evidence or coverage note, 9d passes even when ontology coverage is checked later.
     - PASS: the PRD contains a "## Prior Art / Constraints" section with at least one sub-section ("### Direct prior art from memory", "### Connected context from exploring-knowledge-graph", or "### Coverage notes") that has either evidence content or a justified coverage note.
     - FAIL conditions (any one triggers a blocking FAIL): (a) the section is absent; (b) all three sub-sections are empty AND no coverage note is present; (c) the Step 0.5 BLOCK itself in `.claude/commands/spec.md` (between the `### Step 0.5: Memory-First Gate` heading and the next `\n---\n` delimiter) contains the partial-implementation guard token (string `step0.5:incomplete-without-2b` wrapped in HTML-comment delimiters). Note: the same token appears in this 9d FAIL clause as documentation; check 9d MUST scope its match to the Step 0.5 block boundaries to avoid a tautological self-trigger from this Step 9 text.
     - On FAIL: report the verdict as FAIL and surface the gap as a blocking finding. The critic SHALL NOT return APPROVED while check 9d is a FAIL: a missing, absent, or empty Prior Art / Constraints section is a blocking gap, so the critic reports a FAIL verdict with a blocking finding and withholds APPROVED.

