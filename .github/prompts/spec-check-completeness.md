# Implementation Completeness Check

You are validating that the implementation satisfies all acceptance criteria from the specification.

## Task

1. Extract all acceptance criteria from the specification
2. Check if the implementation satisfies each criterion
3. Identify any missing functionality or edge cases

## Acceptance Criteria Sources

Look for acceptance criteria in:

- Explicit "Acceptance Criteria" sections
- "Given/When/Then" scenarios
- "Done Definition" or "Definition of Done"
- Numbered requirements with measurable outcomes
- Test cases or test scenarios

## Evaluation Guidelines

For each acceptance criterion, assess:

1. **Functionality**: Does the code implement the required behavior?
2. **Edge Cases**: Are boundary conditions handled?
3. **Error Handling**: Are failure scenarios addressed?
4. **Integration**: Does it work with existing code?

## Output Format

Output your analysis in this format:

```markdown
### Acceptance Criteria Checklist

- [x] Criterion 1: [description] - SATISFIED
  - Evidence: [file:line or description]
- [ ] Criterion 2: [description] - NOT SATISFIED
  - Missing: [what's needed]
- [~] Criterion 3: [description] - PARTIALLY SATISFIED
  - Implemented: [what's done]
  - Missing: [what's needed]

### Missing Functionality

1. [Specific missing feature or behavior]
2. [Edge case not handled]

### Edge Cases Not Covered

1. [Boundary condition]
2. [Error scenario]

### Implementation Quality

- **Completeness**: X% of acceptance criteria satisfied
- **Quality**: [assessment of implementation quality]
```

End your analysis with a GitHub Alert block matching the verdict:

For PASS:

```markdown
> [!TIP]
> **VERDICT: PASS**
> Implementation aligns with specification requirements. [Brief explanation]
```

For PARTIAL:

```markdown
> [!WARNING]
> **VERDICT: PARTIAL**
> Most criteria satisfied but minor gaps exist. [Brief explanation]
```

For FAIL:

```markdown
> [!CAUTION]
> **VERDICT: FAIL**
> Critical acceptance criteria not satisfied. [Brief explanation]
```

**IMPORTANT**: The alert block must contain exactly `VERDICT: PASS`, `VERDICT: PARTIAL`, or `VERDICT: FAIL` (no brackets around the token).

After the alert block, append a final literal verdict line on its own line, outside any block, with no markdown formatting:

```text
VERDICT: PASS
```

(or `VERDICT: PARTIAL` / `VERDICT: FAIL`). The CI extractor (`.github/actions/ai-review/action.yml`) anchors on a plain end-of-line `VERDICT: <TOKEN>` pattern; the bolded `> **VERDICT: PASS**` inside the alert block is for human readers and does NOT match the extractor (Refs PR #1965 sed anchor tightening).

## Incremental Scope (fix #2255)

If the additional context contains an `## Incremental Scope Declaration`, the PR
explicitly delivers only a named slice (e.g. "Phase 2", "PR 1 of 3") of the full
parent issue. Apply these rules:

1. Mark any acceptance criterion that belongs to a **different** phase or is
   explicitly outside the declared scope as `N/A`.
2. Evaluate completeness only over the non-N/A criteria.
3. A PR that fully satisfies its declared slice with all non-N/A criteria met
   earns **PASS**, even though other phases remain unimplemented.
4. Do NOT emit PARTIAL or FAIL because criteria outside the declared scope are
   unmet. Those are expected to be deferred.
5. When a criterion is ambiguously scoped, lean toward `N/A` rather than
   treating it as a gap. The author declared they are not claiming to cover it.

If no `## Incremental Scope Declaration` is present, treat all criteria as
in-scope and apply the normal verdict guidelines below.

## Non-Executable Criteria (fix #5366)

You review a diff. You have no shell, so you cannot re-run a command someone
else already ran. A criterion that reports how such a run turned out is
unverifiable by construction, not unmet. Marking it `[~] PARTIALLY SATISFIED`
fails the whole gate closed on every re-run no matter how correct the
implementation is, because `PARTIAL` is a failure token in
`scripts/ai_review_common/verdict.py`.

The exemption is narrow. It covers **historical run evidence** and nothing
else: a claim that a named command was executed and produced a result.
Examples: "`uv run python scripts/validation/pre_pr.py` passes", "`pytest`
exits 0", "`ruff check .` is green", "`make build` completes successfully",
"manually verified locally". Each reports a run. None of them says what the
code must do.

A **behavioral contract** stays in scope even when it is phrased with a
command, because the diff establishes it and you can check it. Keep in scope:

- A required exit code: "the wrapper exits 2 on a malformed config".
- A required output shape: "`--json` emits one object per finding".
- Required error handling for a named input: "an empty ref is rejected with a
  non-zero exit".
- Required behavior of a command the diff adds or changes: "the new `--strict`
  flag fails on a warning".
- A conditional whose subject is the code under review: "the wrapper returns
  zero when `pytest` passes" asserts what the wrapper must do.

The discriminator: does the criterion report **a run that already happened**,
or state **behavior this diff must establish**? Only the first is `N/A`. When
both readings stay open, keep the criterion in scope and evaluate it from the
diff. A criterion wrongly marked `N/A` is measured by nothing.

Apply these rules:

1. Mark a historical-run-evidence claim `N/A`, never `PARTIALLY SATISFIED` and
   never `NOT SATISFIED`. State the reason in one line: the claim reports a run
   you cannot perform.
2. Evaluate completeness only over the non-N/A criteria, exactly as the
   Incremental Scope rules above do.
3. Do NOT emit `PARTIAL` or `FAIL` because a historical-run-evidence claim
   could not be re-executed.
4. If the additional context carries a `## Non-Executable Criteria
   Declaration`, its entries were classified by
   `scripts/ci/spec_nonexecutable_criteria.py`, which fires only when a named
   command is the subject of the result verb. Mark each listed criterion `N/A`
   unless it reads as a behavioral contract on code this diff changes; in that
   case keep it in scope and say why. The declaration is a hint, not an
   override, and it is deliberately narrower than rule 1, so rule 1 still
   applies to a claim it does not name.

This covers only the claim that a command ran and produced a result. It does
not excuse an unimplemented behavior. "The validator rejects an empty ref" is
verifiable from the diff and stays in scope even when the PR also claims a test
run proves it. This repo's PR template puts command evidence under `## Testing`
and `## Author Pre-flight`; a run-evidence line under `## Acceptance criteria`
is misfiled evidence, not a gap in the implementation.

## Ontology Coverage (issue #1925)

The specification may carry a domain ontology. The canonical OntologyFragment lives
at `.agents/specs/ontology/<feature-slug>.md` (seven `## O1..O7` sections), and each
`REQ-NNN-{slug}.md` may render an `## Ontology` body section naming the entities it
touches. When an ontology is present, fold these two checks into the existing
PASS/PARTIAL/FAIL verdict. Do NOT introduce a new top-level verdict token: the CI
extractor in `.github/actions/ai-review/action.yml` reads the plain
`VERDICT: <TOKEN>` line and validates the token against its allowlist. A new
ontology token would require a coordinated allowlist update; without that change,
the gate returns `NEEDS_REVIEW` instead of the intended domain verdict.

Run entity coverage and decision-rule traceability only when an OntologyFragment
exists. A requirement-level `## Ontology` section emitted without a fragment is
local degraded-run evidence, not a canonical source; record the ontology checks as
`N/A` and do not lower the verdict for ontology coverage in that case.

1. **Entity coverage**: when an OntologyFragment exists, every domain entity
   referenced anywhere in generated spec artifacts (`REQ-NNN-{slug}.md`,
   `DESIGN-NNN-{slug}.md`, and `TASK-NNN-{slug}.md`) must
   appear in the OntologyFragment by its canonical O2 name. The requirement's `## Ontology`
   section is evidence that the requirement uses those names; it cannot introduce an
   entity absent from the fragment. When no OntologyFragment exists, the
   requirement's `## Ontology` section is local evidence only. An entity named in a
   requirement but absent from the OntologyFragment is a ubiquitous-language drift:
   it means two artifacts may name the same concept differently. Treat one such gap
   as a minor gap (lean PARTIAL); treat a requirement whose primary entity is
   entirely absent from the OntologyFragment as a critical gap (lean FAIL).
2. **Decision-rule traceability**: when an OntologyFragment exists, every domain decision rule in
   `.agents/specs/design/DESIGN-NNN-{slug}.md` should trace to an `## O5`
   decision-rule source in the OntologyFragment. An unsourced decision rule is a
   PARTIAL-level gap.

Degradation (no spurious failures):

- If the specification carries NO OntologyFragment, the ontology checks are `N/A`;
  do not lower the verdict for its absence. Requirement-level `## Ontology` sections
  from degraded runs are local evidence only, not a substitute fragment.
- If the OntologyFragment exists but declares `none (no domain entities)` and the
  generated REQ, DESIGN, and TASK artifacts also reference no domain entities,
  entity coverage is vacuously satisfied; do not emit PARTIAL or FAIL for an
  empty-entity feature. If any generated spec artifact names domain entities while
  the fragment declares none, treat that as a critical entity-coverage gap.

Record ontology findings in the Missing Functionality section, not as a separate
verdict token.

## Verdict Guidelines

- `PASS`: All in-scope acceptance criteria satisfied (N/A criteria excluded) and, when
  an ontology is present, entity coverage and decision-rule traceability hold (or are
  vacuously satisfied for an empty-entity feature)
- `PARTIAL`: Most in-scope criteria satisfied but minor gaps exist, including a single
  ontology entity-coverage or decision-rule-traceability gap
- `FAIL`: Critical in-scope acceptance criteria not satisfied, OR a requirement's
  primary entity is entirely absent from the ontology when an ontology is present
