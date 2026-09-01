# Requirements Traceability Check

You are verifying that implementation changes trace back to specification requirements.

## Task

1. Identify all requirements in the specification (look for REQ-*, acceptance criteria, user stories)
2. For each requirement, determine if the implementation changes address it
3. Report coverage status for each requirement

## Identification Patterns

Look for requirements in these forms:

- `REQ-NNN`: Formal requirement IDs
- `DESIGN-NNN`: Design specification IDs
- `TASK-NNN`: Task identifiers
- `AC-N` or numbered acceptance criteria
- User stories: "As a [user], I want [goal], so that [benefit]"
- Bullet points describing expected behavior
- "SHALL", "MUST", "SHOULD" statements (RFC 2119)

## Coverage Status Definitions

- `COVERED`: Implementation clearly addresses this requirement
- `PARTIAL`: Implementation partially addresses this requirement
- `NOT_COVERED`: No evidence that implementation addresses this requirement
- `N/A`: Requirement is not applicable to these changes

## Output Format

Output your analysis in this format:

```markdown
### Requirements Coverage Matrix

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| REQ-001 | [brief description] | COVERED | [file:line or description] |
| REQ-002 | [brief description] | NOT_COVERED | - |
| REQ-003 | [brief description] | PARTIAL | [what's missing] |

### Summary

- Total Requirements: N
- Covered: N (X%)
- Partially Covered: N (X%)
- Not Covered: N (X%)

### Gaps

1. [Specific gaps or missing implementations]
```

End your analysis with a GitHub Alert block matching the verdict:

For PASS:

```markdown
> [!TIP]
> **VERDICT: PASS**
> All requirements are covered by the implementation. [Brief explanation]
```

For PARTIAL:

```markdown
> [!WARNING]
> **VERDICT: PARTIAL**
> Some requirements have gaps. [Brief explanation]
```

For FAIL:

```markdown
> [!CAUTION]
> **VERDICT: FAIL**
> Critical requirements are not covered. [Brief explanation]
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

1. Mark any requirement that belongs to a **different** phase or is explicitly
   outside the declared scope as `N/A`.
2. Compute coverage percentage only over the non-N/A requirements.
3. A PR that fully covers its declared slice with 100% non-N/A requirements COVERED
   earns **PASS**, even though other phases remain NOT_COVERED.
4. Do NOT penalize a PR for not implementing criteria outside its declared scope.
5. When a requirement is ambiguously scoped, lean toward `N/A` rather than
   `NOT_COVERED`. The author declared they are not claiming to cover it.

If no `## Incremental Scope Declaration` is present, treat all requirements as
in-scope and apply the normal verdict guidelines below.

## Non-Executable Criteria (fix #5366)

If the additional context contains a `## Non-Executable Criteria Declaration`,
its entries were flagged by a heuristic as reporting the outcome of a command
that was already run. Split them before you trace anything:

1. An entry that reads as a **behavioral contract** on code this diff changes
   is a requirement like any other. Trace it. Required exit codes, output
   shape, and error handling for a named input all belong here, and the
   declaration does not exempt them.
2. An entry that is **only run evidence**, such as "`pytest` passes" or
   "`ruff check .` is green", names no behavior the diff has to implement.
   There is nothing to trace, so leave it out of the coverage matrix rather
   than recording it `NOT_COVERED`.

Rule 2 is why this section exists. Run evidence has no implementation by
definition, so tracing it can only ever produce `NOT_COVERED`, and enough of
those produce a `FAIL` on a PR whose implementation is complete. That is the
same false failure the completeness gate carried before issue #5366, arriving
through traceability instead.

Do NOT lower the verdict because a run-evidence entry was skipped, and do NOT
list a skipped entry as a gap. When an entry could be read either way, trace
it: a requirement wrongly skipped is measured by nothing, while a run-evidence
entry wrongly traced costs one `NOT_COVERED` row you can explain.

## Verdict Guidelines

- `PASS`: 100% of in-scope requirements COVERED (N/A requirements excluded)
- `PARTIAL`: >50% in-scope requirements covered, but some gaps
- `FAIL`: <50% in-scope requirements covered OR critical in-scope requirements NOT_COVERED
