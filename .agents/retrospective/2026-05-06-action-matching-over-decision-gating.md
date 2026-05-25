# Retrospective: Action-matching over decision-gating

**Date**: 2026-05-06
**Issue**: #1847
**Canonical example**: #1843 (CWE-22 scanner reinvention)

## Summary

The agent skill router and `/spec` command both default to action-matching: when a
user request mentions an action verb ("scan for path traversal", "validate input",
"detect leaks"), the router finds the implementation skill that already does that
action (`security-detection`, `pipeline-validator`) and dispatches. No step in the
flow asks the prior question: *should we build this at all, given that an industry
tool already provides it?*

The result is fast, confident routing to the **wrong layer of the decision tree**.
The build/buy/partner/defer choice is bypassed entirely.

## Canonical failure: #1843

- Request: "Add a CWE-22 path traversal scanner."
- Router match: `security-detection` skill.
- Outcome: 9 hours, 16 commits, 945 LOC of custom scanner code.
- Reality: CodeQL ships a CWE-22 query out of the box. Cost to adopt: ~30 minutes
  of workflow YAML. Net waste: ~8.5 hours and a maintenance burden the team now owns.

The implementation skill was technically correct. The decision to invoke it was
wrong, and no gate caught the error because no gate existed.

## Failure pattern

```
User intent  -->  Action verb extracted  -->  Skill matched  -->  Skill executes
                                              ^
                                              |
                                              [no buy-vs-build gate here]
```

The pattern recurs whenever:

1. The capability is **Context** (per Wardley/Moore: undifferentiating), not Core.
2. A mature industry tool already covers ≥80% of the requirement.
3. The action verb in the request maps cleanly to an existing implementation skill.

Action-matching is high-precision, low-recall on the "is this the right thing to
build?" question. It optimizes the inner loop (how to build) at the expense of the
outer loop (whether to build).

## Remediation (this issue)

1. `/spec` step 4a: **Buy-vs-build gate** invokes `buy-vs-build-framework` (Quick
   tier) for any spec that introduces a new capability, module, scanner, validator,
   or pipeline component. Skipped for pure bug fixes / doc / refactor.
2. `AGENTS.md` Skill-First section and `CLAUDE.md` skill routing matrix add an
   explicit routing rule: "New capability proposed → buy-vs-build-framework (Quick
   tier minimum) BEFORE spec-generator."
3. This retrospective documents the pattern so future routing changes preserve the
   gate even as skills are reshuffled.

## Detection signal for future regressions

If a PR adds a new scanner/validator/pipeline component **without** a corresponding
`Buy-vs-build decision` section in the originating spec, the gate was bypassed.
Reviewers should require the section be added retroactively, or justify the skip
with one of the explicit skip categories (bug fix, doc, refactor, capability
extension).

## Lessons

- Routing efficiency is not the same as routing correctness.
- The cheapest decision to reverse is the one you never made: gate **before**
  artifact generation, not after.
- Action verbs in user requests are a poor proxy for "build this." They tell you
  *what* the user wants done, not *who* should do it.
- Industry tools are the default. In-house implementation is the exception that
  must be justified, not the other way around.

## References

- Issue #1847 (this work)
- Issue #1843 (canonical failure)
- `.claude/skills/buy-vs-build-framework/SKILL.md`
- `.claude/commands/spec.md` (step 4a)
