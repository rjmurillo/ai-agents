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

## Ontology Coverage (issue #1925)

The specification may carry a domain ontology. The canonical OntologyFragment lives
at `.agents/specs/ontology/<feature-slug>.md` (seven `## O1..O7` sections), and each
`REQ-NNN-{slug}.md` may render an `## Ontology` body section naming the entities it
touches. When an ontology is present, fold these two checks into the existing
PASS/PARTIAL/FAIL verdict. Do NOT introduce a new top-level verdict token: the CI
extractor in `.github/actions/ai-review/action.yml` anchors on a plain
`VERDICT: PASS|PARTIAL|FAIL` line, so an `ONTOLOGY-INCOMPLETE` token would not match
and would silently drop the verdict.

1. **Entity coverage**: every domain entity referenced in a requirement's statement
   or acceptance criteria must appear in the OntologyFragment (by its canonical O2
   name) or in that requirement's `## Ontology` section. An entity named in a
   requirement but absent from the ontology is an ubiquitous-language drift: it means
   two artifacts may name the same concept differently. Treat one such gap as a minor
   gap (lean PARTIAL); treat a requirement whose primary entity is entirely unnamed in
   the ontology as a critical gap (lean FAIL).
2. **Decision-rule traceability**: every domain decision rule in `design.md` should
   trace to an `## O5` decision-rule source in the OntologyFragment. An unsourced
   decision rule is a PARTIAL-level gap.

Degradation (no spurious failures):

- If the specification carries NO OntologyFragment and NO `## Ontology` sections, the
  ontology checks are `N/A`; do not lower the verdict for their absence.
- If the OntologyFragment exists but declares `none (no domain entities)` (a config
  change, doc fix, or formatting tweak), entity coverage is vacuously satisfied; do
  not emit PARTIAL or FAIL for an empty-entity feature.

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
