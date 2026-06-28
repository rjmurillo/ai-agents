---
name: world-model-diagnostic
version: 1.0.0
model: claude-sonnet-4-6
description: Twenty-minute diagnostic mapping a team to a world-model paradigm (vector DB, structured ontology, signal-fidelity). Use when you say "run the world model diagnostic", "audit our world model", "which world model architecture fits us", or "audit where we automate judgment". Use for AI readiness assessments and boundary-layer audits where automated judgment is safe. Do NOT use for mapping team operating rhythms or decision flows; use work-operating-model instead.
license: MIT
---

# World Model Diagnostic

Source: Jonathan Edwards (OB1 community), adapted for ai-agents.

## Purpose

Your job is not to hand back a polished readiness score. Your job is to **expose where information routing ends and editorial judgment begins**, then recommend the smallest credible starting sequence.

This diagnostic answers five questions:

1. Where does reality leave the clearest fingerprint in this business?
2. Which world-model paradigm fits the company right now?
3. Does the company have an explicit boundary layer?
4. Where is it most exposed to simulated judgment?
5. What should it build first, second, and third?

## Triggers

| Trigger phrase | Operation |
|----------------|-----------|
| `run the world model diagnostic` | Start the 20-minute structured audit |
| `audit our world model` | Same as above, conversational form |
| `which world model architecture fits us` | Map company to paradigm |
| `audit where we automate judgment` | Boundary-layer audit only |
| `what should we build first for a world model` | Skip to recommended build sequence |

## When to Use

**Use this skill when:**

- A team is choosing knowledge infrastructure (vector DB, ontology, telemetry pipeline) and needs to validate paradigm fit before investing.
- An organization is adopting agent-driven workflows and needs to know where automated judgment is safe.
- Leadership has thinned a management layer and wants to know where editorial judgment now lives.

**Use a different skill when:**

- You need a per-PR code or design review. Use `analyst` or `architect`.
- You need product strategy or roadmap prioritization. Use `roadmap`.
- The org has already picked a paradigm and needs implementation help. Skip to the relevant build skill.

## Non-Negotiable Rules

1. **Do not give a numeric readiness score.**
2. **Label every conclusion** as one of:
   - `Firm finding`: directly supported by the user's answer or confirmed prior record.
   - `Inference`: synthesis from available evidence.
   - `Open question`: unresolved or missing evidence that materially affects the recommendation.
3. **Keep the boundary layer central.** Database choice is downstream of boundary clarity.
4. **Start concrete, not abstract.** Ask about recent information flows, recent decisions, recent misses.
5. **Force ranking when discussing signal.** Ask the user to rank the top 3 to 5 sources by fidelity.
6. **Audit actual flows, not aspirational diagrams.**
7. **Do not let the model pretend judgment has been automated** when evidence shows interpretation still lives in people.
8. **Final recommendation must include**: paradigm fit, boundary-layer status, top three simulated-judgment exposures, and first/second/third build steps.
9. **Facts and interpretations cannot be presented with the same voice.**
10. **Stay lightweight.** Batch questions so the session finishes in about 20 minutes.

## Paradigm Mapping Contract

Map the company using these rules:

| Company Type | Paradigm | Reason |
|--------------|----------|--------|
| Under 100 people, strong senior team | `vector database` | Senior people can temporarily act as a human boundary layer. |
| Enterprise, regulated, or operationally complex | `structured ontology` | Boundary must be architectural because errors are expensive. |
| Platform business with high-fidelity signal (transactions, telemetry, operational exhaust) | `signal-fidelity` | Business already emits machine-readable truth with a higher ceiling. |
| Knowledge-work company (conversations, docs, soft context) | `vector database` | Hardest case. Pair with aggressive boundary-layer work first plus explicit outcome encoding. |

**When cues conflict**, use this priority order:

1. Highest-fidelity signal.
2. Cost of a bad interpretive decision.
3. Amount of senior human judgment available to absorb errors.

## Five-Principle Evaluation

Evaluate without numeric scoring:

| Principle | Question | Classifications |
|-----------|----------|----------------|
| signal fidelity | Where does reality leave the clearest fingerprint? | `clear` / `mixed` / `low` |
| earned structure | Letting structure emerge from work, or forcing schema too early? | `earned` / `partially earned` / `imposed` |
| outcome encoding | Close the loop between action and result in a machine-readable way? | `present` / `partial` / `missing` |
| organizational resistance | Capture signal as a byproduct of work or require extra documentation? | `byproduct` / `mixed` / `manual` |
| time in system | How long has relevant data been flowing through anything durable? | `running` / `starting` / `not started` |

## Process

### Phase 1: Orientation

1. **Memory check.** Search the project's memory layer (per the memory architecture in `AGENTS.md`) for prior diagnostic context. Use Serena memories or Forgetful. Treat every result as a hint, not confirmed fact. If memory tooling is unavailable, skip this step and note the gap in the final assessment. Suggested queries:
   - `world model`
   - `boundary layer`
   - Strategic context hints from prior sessions.
   - The company name, once known (re-run after Phase 2 intake if the name surfaces there).
2. **Tell the user what the diagnostic will do**:
   - Intake on signal, data, and decision flow.
   - Paradigm classification.
   - Boundary audit on the highest-value information flows.
   - Final assessment with fact-versus-inference labels.
3. **State the persistence plan.** The diagnostic produces three artifacts (intake summary, boundary audit summary, final assessment). Persist them via the repo's memory tooling unless the user declines. See "Persistence" below.

### Phase 2: Intake

Keep to two or three batches of questions, not long isolated lists.

**Required coverage**:

- Company size, industry, business model.
- Regulated, safety-critical, or high-cost-of-error environment?
- Top three to five data sources ranked by fidelity.
- Where decisions currently get made.
- Where editorial judgment currently lives.
- Which management or synthesis layers have been removed or thinned.
- How outcomes are recorded today.
- Data capture: byproduct of work or separate burden?
- How long any durable system has been running.

**Strong prompt patterns**:

- "What are the three places reality leaves the cleanest fingerprint in this business?"
- "Which decisions still depend on someone saying, 'ignore that, that's normal'?"
- "Where did you remove a human layer and keep the information flow, but lose the interpretation?"

### Phase 3: Classification

After intake, state:

- **Company case**: description of the company type or situation.
- **Recommended paradigm**: vector database, structured ontology, or signal-fidelity.
- **Main reason the fit is right.**
- **Primary caveat or failure mode to watch.**

Treat as provisional until the boundary audit is done.

### Phase 4: Boundary Audit

Audit five to ten flows. If time is tight, top five only.

For each flow capture:

| Field | Description |
|-------|-------------|
| Flow name | e.g., "Customer support ticket prioritization." |
| Source | Where data originates. |
| Consumer | Who or what acts on it. |
| Current human editor or reviewer | Who interprets today. |
| Classification | `act on this` versus `interpret this first`. |
| Reason for label | Why that classification applies. |
| What goes wrong if the editor disappears | Risk assessment. |
| Exposure level | `high` / `medium` / `low`. |

**Prioritize flows** that can move money, customers, roadmap, risk, or staffing.

**If a flow looks factual at the source but interpretive at the output**, call that out explicitly. Clean inputs do not guarantee trustworthy judgment.

### Phase 5: Final Assessment

Return in this order:

1. Company case.
2. Paradigm fit.
3. Five-principle readout.
4. Boundary-layer status.
5. Top simulated-judgment exposures.
6. Starting sequence.
7. Confidence markers (firm findings / inferences / open questions).
8. Shift since last run, if a prior diagnostic exists in memory.

**Output contract** (consumable by downstream skills such as `analyst` or `architect`):

````markdown
## Firm Findings
- {fact directly supported by evidence}
- {fact directly supported by evidence}

## Inferences
- {synthesis from available evidence}
- {synthesis from available evidence}

## Open Questions
- {unresolved issue affecting recommendation}
- {unresolved issue affecting recommendation}

## Paradigm Fit
- Paradigm: {vector database | structured ontology | signal-fidelity}
- Boundary status: {explicit | implicit | missing}

## Recommended Build Order
1. **First**: {usually boundary layer and flow labeling}
2. **Second**: {usually highest-fidelity capture and outcome encoding}
3. **Third**: {usually paradigm-specific retrieval or structure layer}
````

**Only move the order around when evidence is strong.**

A JSON variant of the same shape is acceptable when a downstream tool consumes the output programmatically. Keep the field names identical (`firm_findings`, `inferences`, `open_questions`, `paradigm`, `boundary_status`, `build_order`).

**Self-check before returning**: Verify the output includes all eight items from the list above. If any item is missing, add it before responding. If an item cannot be filled due to missing evidence, include it with an `Open question` label.

## Persistence

Save exactly three artifacts via the repo's memory tooling, unless the user declines. Use Serena `write_memory` or the equivalent Forgetful entry point. Key the entries by company slug so future runs can detect drift.

### 1. Intake Summary

- Entry name: `diagnostic-{company-slug}-intake`
- Body: company name, size, industry; top three to five signal sources ranked by fidelity; where judgment lives; the five-principle classifications; date.

### 2. Boundary Audit Summary

- Entry name: `diagnostic-{company-slug}-boundary`
- Body: number of flows audited; flows classified as `act on this`; flows classified as `interpret this first`; flows missing a human editor; high-exposure flows; date.

### 3. Final Assessment

- Entry name: `diagnostic-{company-slug}-assessment`
- Body: paradigm; boundary status; top three exposures; build sequence (first, second, third); open questions; date.

If the user prefers files on disk for working notes, use a repo-relative path under `.agents/analysis/diagnostics/{company-slug}/` with date-prefixed filenames (`YYYY-MM-DD-intake.md`, `YYYY-MM-DD-boundary-audit.md`, `YYYY-MM-DD-assessment.md`, `YYYY-MM-DD-full-diagnostic.md`). Do not write outside the repo.

## Interview Style

- Ask one batch at a time.
- Stay direct and strategic.
- If the user gives vague answers, push for one concrete example.
- If the company obviously fits the knowledge-work case, say so directly.
- If the company wants to automate judgment rather than routing, name that as the risk.
- If the boundary layer is missing, say it plainly. Most companies land there.

## Paradigm Definitions

### Vector Database

- **Best for**: knowledge work, under 100 people, strong senior team.
- **Trade-off**: relies on a human boundary layer to interpret retrieval.
- **Risk**: loses effectiveness as senior judgment thins out.
- **Example**: a startup using Pinecone plus Claude with five senior engineers reviewing outputs.

### Structured Ontology

- **Best for**: enterprise, regulated, operationally complex.
- **Trade-off**: high upfront structure cost, but errors are expensive.
- **Risk**: over-engineered schema before patterns emerge.
- **Example**: a healthcare system with an explicit medical ontology and compliance rules.

### Signal-Fidelity

- **Best for**: platform business with transactional data, telemetry, operational exhaust.
- **Trade-off**: requires genuinely high-fidelity signal (most companies do not have this).
- **Risk**: mistaking soft signals (emails, notes) for hard signals (transactions, metrics).
- **Example**: an e-commerce platform using transaction logs and user behavior telemetry.

## Common Pitfalls

### Mistaking "we have data" for "we have signal"

- **Pattern**: the company has lots of emails, docs, meeting notes.
- **Reality**: these are interpretive artifacts, not clean signal.
- **Fix**: classify as a knowledge-work case, then pair vector DB with aggressive boundary work.

### Automating judgment that should stay human

- **Pattern**: "AI will decide which customer requests are urgent."
- **Reality**: urgency often requires context only humans have.
- **Fix**: the boundary audit shows `interpret this first`, so keep a human in the loop and use AI for routing only.

### Building structure before patterns emerge

- **Pattern**: "We need a full ontology before we start."
- **Reality**: most structure should be earned from observed work.
- **Fix**: start with a vector DB plus outcome encoding and let the schema emerge.

### Missing the boundary layer entirely

- **Pattern**: "Our data is clean, we can just feed it to the model."
- **Reality**: most "clean" data still requires interpretation.
- **Fix**: run an explicit boundary audit and label every flow as act-on-this versus interpret-first.

## Integration

Companion skills (when present in this repo):

- `work-operating-model` (issue #1806). Use after the diagnostic to map the internal operating model.
- `panning-for-gold` (issue #1802). If the diagnostic surfaces unstructured brain dumps, extract threads before retrieval design.
- `codebase-documenter` (issue #1803). For an engineering-org variant, follow the diagnostic with a documentation pass.

If a companion is not yet ported, return the diagnostic output and let the operator route follow-on work manually.

## Verification

- [ ] Output includes all eight Phase 5 items (company case through shift-since-last-run).
- [ ] Every conclusion labeled as `Firm finding`, `Inference`, or `Open question`.
- [ ] Paradigm fit matches the Paradigm Mapping Contract rules above.
- [ ] Boundary audit covers at least the top three highest-exposure flows.
- [ ] No numeric readiness score appears anywhere in the output.

<!-- vendor-portability: declared. This skill offers an optional on-disk note path under .agents/analysis/diagnostics/{company-slug}/ when the user prefers files. The path is an opt-in write target created on demand; the diagnostic runs in-conversation without it. Issue #2050. -->
