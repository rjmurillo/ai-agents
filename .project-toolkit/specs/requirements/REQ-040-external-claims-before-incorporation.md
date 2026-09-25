---
type: requirement
id: REQ-040
title: Verify external claims before research writes a durable artifact
status: implemented
priority: P1
category: functional
source: issue-5388
related:
  - DESIGN-038
  - TASK-049
  - REQ-038
created: 2026-09-25
updated: 2026-09-25
author: spec
tags:
  - skills
  - research
  - routing
---

# REQ-040: Verify external claims before research writes a durable artifact

## Step 0 First Principles

### Q1 Demand Reality

Issue #5388, filed by rjmurillo under epic #5390. Issue #5389 (the
reachability eval) is blocked on it. DESIGN-037 kept
`ai-agents-external-claims` as `explicit-only` and named #5388 as the issue
that defines its adjunct trigger.

### Q2 Status Quo

A contributor runs `/research`. The skill fetches pages, writes the analysis
document, writes a Serena memory, and drafts an issue body. Vendor numbers and
third-party statements flow into all three with no source, date, or
confidence recorded. Verification happens only when the contributor thinks to
run `ai-agents-external-claims` by hand.

### Q3 Desperate Specificity

The `research` skill. Its Phase 2, 4, and 5 writes are the only path from a
fetched page to a committed artifact, and none of them checks a claim.

### Q4 Narrowest Wedge

One claim ledger with a deterministic validator, one gate step in `research`
before its first write, and one routing change. About three hours.

### Q5 Observation

REQ-038 Q5, measured on `main` at `95383d276` on 2026-09-24:
`ai-agents-external-claims` had no exact-name inbound reference from any
skill template, skill reference file, or agent body. Its routing rationale on
`main` at `4bb5af2fa` still says "issue #5388 will define this skill's own
adjunct trigger".

### Q6 Future-fit

The ledger is one file per research run. It grows with the number of claims
in that run, not with the catalog. At 10x the skill catalog nothing changes.

## Problem statement

The `research` skill can persist third-party claims without a primary source,
a date, a confidence, or a conservative fallback.

## User stories

- As a reader of a research analysis, I see which external claims were
  checked, against what source, on what date, and at what confidence.
- As a research author with no network access, the run still finishes, and
  each unchecked claim is removed or qualified with the gap recorded.
- As the #5389 eval author, I see `ai-agents-external-claims` classified as a
  conditional adjunct of `research`.

## Ontology

- **External claim**: an assertion whose truth depends on a source outside
  this repository. Categories: `vendor`, `api`, `statistic`, `legal`,
  `project-status`, `comparative`.
- **Durable artifact**: a file the run persists: the analysis document, the
  Serena memory, or the issue body.
- **Claim ledger**: a JSON file that records the activation decision and one
  entry per external claim.
- **Disposition**: `verified`, `narrowed`, `qualified`, or `removed`.
- **Source kind**: `primary`, `secondary`, or `none`.
- **Claim gate**: the `research` step that validates the ledger and the
  artifact text before any durable write.

## Data model

A ledger holds `artifact` (the destination path), `activation` (`decision`
and `reason`), and `claims`. Each claim holds `id`, `claim`, `category`,
`time_sensitive`, `source` (`kind`, `url`, `published`, `accessed`,
`secondary_reason`), `confidence` (`high`, `medium`, `low`, `none`),
`disposition`, `final_wording`, and `gap`.

## Integrations

- `research` runs the gate after Phase 1 and before Phase 2.
- `ai-agents-external-claims` owns the ledger contract and the validator.
- `autoplan` names the gate in its research row.
- `build/scripts/build_all.py` renders the mirrors.

## Failure modes

- No network or no authority: disposition `qualified` or `removed`, source
  kind `none`, gap recorded. The run continues.
- A ledger file that is not valid JSON: the validator exits 2.
- The artifact still carries a removed claim, or lacks a kept wording: the
  validator exits 1, and the run does not write.

## Security

The validator reads two local files and writes JSON to stdout. It opens no
network connection and runs no subprocess. Fetched content stays data under
the existing untrusted-content rule.

## Observability

The validator prints a JSON summary: decision, claim count, counts by
disposition, and the defect list. The ledger itself is the audit record.

## Acceptance criteria

1. The `autoplan` research row SHALL name the external-claims gate.
2. WHEN a research run is about to write a durable artifact, THE `research`
   skill SHALL run the claim gate first, and SHALL NOT write while the gate
   fails.
3. The activation decision SHALL depend on claim content (the six
   categories), not on the file extension of the artifact.
4. IF the run holds only repository-internal facts, THEN the ledger SHALL
   record `decision: skip` with a non-empty reason and no claims.
5. Each activated claim SHALL record the atomic claim, source, dates,
   confidence, final wording, and gap, and the validator SHALL refuse a claim
   that lacks a required field.
6. IF a claim is not supported by a primary source, THEN its disposition
   SHALL be `narrowed`, `qualified`, or `removed`, never `verified`.
7. WHEN the artifact text is given, THE validator SHALL refuse a kept final
   wording that is absent from it, and a removed claim whose text is present.
8. Tests SHALL cover a vendor claim, a statistic, a time-sensitive claim, a
   secondary-source-only claim, an internal-only skip, and an unavailable
   source.
9. The routing manifest SHALL classify `ai-agents-external-claims` as
   `conditional-adjunct` with invoker `research`.
10. Generated mirrors SHALL change only through `build/scripts/build_all.py`.

## Out of scope

- Re-verifying facts proven by this repository's code or tests.
- Requiring web access for every research request.
- Detecting external claims in free text by pattern matching.

## Deferred

- Scored LLM activation accuracy. Owner: #5389.

## Open questions

None.

## CVA summary

Common: every claim needs a source kind, a confidence, a disposition, and a
final wording. Varies: primary against secondary against unavailable
sources, and time-sensitive against stable claims. Relationship: the source
kind bounds the disposition and the confidence.

## Buy-vs-build decision

N/A (bug fix): the fix composes two existing skills and adds one validator.

## Complexity classification

Tier 2, Clear domain. Methodology: test-first, one slice.
