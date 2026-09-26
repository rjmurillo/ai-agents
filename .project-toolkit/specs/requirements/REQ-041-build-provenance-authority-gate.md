---
type: requirement
id: REQ-041
title: Establish provenance and authority before build changes validation semantics
status: implemented
priority: P1
category: functional
source: issue-5387
related:
  - DESIGN-039
  - TASK-050
  - REQ-038
created: 2026-09-26
updated: 2026-09-26
author: spec
tags:
  - skills
  - build
  - routing
  - validation
---

# REQ-041: Establish provenance and authority before build changes validation semantics

## Step 0 First Principles

### Q1 Demand Reality

Issue #5387, filed by rjmurillo under epic #5390. Issue #5389 (the
reachability eval) is blocked on it. DESIGN-036 left `validation-authority` as
`explicit-only`, and its routing rationale names #5387 as the issue that
defines its adjunct trigger.

### Q2 Status Quo

A validator fails during `/build`. The implementer edits whatever file makes
the check pass. That can be the validator, a generated mirror under `src/`,
or a baseline snapshot. `/build` names neither `analysis-provenance` nor
`validation-authority`, so nothing asks who owns the failing check first.

### Q3 Desperate Specificity

The `build` skill. Its Phase 3 slices are the only place an implementation
agent edits code, and no step there checks ownership of a validator.

### Q4 Narrowest Wedge

One deterministic trigger script, one decision-record validator, one new
`build` phase, one consume step in `/test` and `/review`, and two routing
changes. About four hours.

### Q5 Observation

Measured on `main` at `9dbb923ed` on 2026-09-26:
`validation-authority` has routing role `explicit-only`, and its rationale
says "issue #5387 will define this skill's own adjunct trigger".
`analysis-provenance` is a `nested-helper` of `spec-generator` only.
`templates/skills/build.SKILL.md.tmpl` names neither skill.
`check_provenance.py` has no generated-mirror signal, so it reports a file
under `src/claude/` as LOCAL.

### Q6 Future-fit

The trigger reads the generated-output roots from `build_all.py`, so a new
generated root needs no trigger change. The record grows with the number of
validation targets in one change, not with the catalog.

## Problem statement

`/build` can change validation semantics without first proving who owns the
check and which location is allowed to change.

## User stories

- As a maintainer, I see a record that names the owner, the authority, and
  the permitted change location before any validator edit lands.
- As an implementer who hits a failing generated mirror, the gate sends me to
  the template that generates it.
- As an implementer of an ordinary feature, the gate skips with a stated
  reason and costs one script call.
- As the #5389 eval author, I see both skills classified as conditional
  adjuncts of `build`.

## Ontology

- **Validation target**: a file whose change can alter a pass or fail result,
  a severity, a baseline, or an accepted or rejected fixture case.
- **Trigger**: the script that decides from changed paths and verified effects
  whether the gate runs.
- **Provenance category**: `LOCAL`, `GENERATED`, `VENDOR`, `UPSTREAM`, or
  `UNKNOWN`.
- **Diagnosis**: `implementation-defect`, `local-config-defect`,
  `stale-generated-output`, `baseline-update`, `upstream-defect`, or
  `unknown`.
- **Decision record**: a JSON file with one entry per validation target.
- **Permitted change location**: the one path that the record allows the
  build to edit for that target.

## Data model

A record holds `trigger` (the trigger output) and `targets`. Each target holds
`target`, `component`, `provenance` (`category`, `owner`, `evidence`,
`canonical_source`), `authority` (`contract`, `diagnosis`,
`permitted_change_location`, `escalation`), and, for a baseline update,
`baseline_justification` (`policy_source`, `reason`, `added_entries`).

## Integrations

- `build` runs the trigger before Phase 3, and on activation composes
  `analysis-provenance`, then `validation-authority`, then the record check.
- `validation-authority` owns the record contract and its validator.
- `test` Gate 4 and `review` Stage 1 re-run the record check when a record
  path is handed to them.
- `build/scripts/build_all.py` renders the mirrors.

## Failure modes

- Empty changed-path list: the trigger exits 2.
- Record file missing or not valid JSON: the validator exits 2.
- Unknown provenance or unknown diagnosis: the validator exits 1 with a
  blocking diagnostic, and the build stops editing that target.
- `build_all.py` absent (a vendored install): the trigger skips the
  generated-root cue, keeps every other cue, and reports the gap.

## Security

Both scripts read local files and write JSON to stdout. The trigger parses
`build_all.py` with `ast` and never imports or runs it. Neither script opens a
network connection or starts a subprocess.

## Observability

The trigger prints its decision, matched cues, and reason. The validator
prints a JSON summary with target count, counts by category, and defects.

## Acceptance criteria

1. WHEN a change can alter validation semantics, THE `build` skill SHALL run
   `analysis-provenance` and then `validation-authority` before Phase 3.
2. The `build` process SHALL order provenance first and authority second.
3. The trigger SHALL activate on path cues and on verified effect cues, and
   SHALL skip an unrelated source change with a stated reason.
4. IF a target is `GENERATED`, THEN the permitted change location SHALL be its
   canonical source. IF a target is `VENDOR` or `UPSTREAM`, THEN the permitted
   change location SHALL NOT be the target.
5. IF the diagnosis is `baseline-update`, THEN the record SHALL cite an
   existing policy source and a reason, and SHALL justify each added entry.
6. IF provenance or diagnosis is unknown, THEN the validator SHALL exit 1
   with a blocking diagnostic.
7. WHEN `/test` or `/review` receives a record path, THEY SHALL re-run the
   record check against the current changed paths.
8. Tests SHALL cover a local validator change and a local configuration fix
   (positive), and a vendored validator, a generated mirror, an unjustified
   baseline refresh, an unknown owner, and an unrelated source change
   (negative or edge).
9. The routing manifest SHALL classify both skills as `conditional-adjunct`
   with invoker `build`.
10. Generated mirrors SHALL change only through `build/scripts/build_all.py`.

## Out of scope

- Blocking legitimate validator improvements on LOCAL targets.
- Treating every failed check as an upstream defect.
- Running the gate for changes that cannot affect validation semantics.

## Deferred

- Scored LLM activation accuracy. Owner: #5389.

## Open questions

None.

## CVA summary

Common: every validation target needs an owner, an authority, a diagnosis,
and one permitted change location. Varies: the provenance category decides
which location is legal. Relationship: the category bounds the location, and
the diagnosis bounds the extra evidence.

## Buy-vs-build decision

N/A (bug fix): the fix composes two existing skills and adds two scripts.

## Complexity classification

Tier 2, Clear domain. Methodology: test-first, one slice per script.
