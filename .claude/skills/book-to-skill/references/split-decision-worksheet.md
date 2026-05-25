# Diagnose / Apply Split Decision Worksheet

Use during Phase 2 of `book-to-skill`. Decides whether the book becomes one skill or two.

## Inputs (from Phase 1)

- Q2 step count:
- Q2 steps produce a concrete output artifact (yes/no):
- Q5 question count:
- Q5 questions interrogate the operator's situation (yes/no):

## Decision matrix

| Q5 non-trivial? | Q2 multi-step with output? | Decision |
|-----------------|----------------------------|----------|
| Yes | Yes | **Split** into `<book>-diagnose` and `<book>-apply` |
| Yes | No | **Single** skill, diagnose-only (questionnaire) |
| No | Yes | **Single** skill, apply-only (recipe) |
| No | No | **Halt**. Re-run Phase 1; one of the lists must be non-trivial. |

## Tie-breakers when unsure

- Different invocation contexts? If diagnose runs during review and apply runs during drafting, that argues for split.
- Different audiences? If diagnose is for the operator's own work and apply produces output for someone else, split.
- Combined skill would exceed 500 lines? Split.
- Otherwise, default **single**. Refactor later if usage shows two distinct modes.

## Worked example: *The Mom Test* (Rob Fitzpatrick)

- Q2: rewrite a customer interview question in Mom Test format (multi-step, produces output) → yes
- Q5: detect leading questions in a draft interview (non-trivial diagnostic) → yes
- Different contexts: diagnose runs on existing interviews; apply runs while drafting → yes

Decision: **split**. Produces `momtest-diagnose` and `momtest-apply`.

## Worked example: *Atomic Habits* (James Clear)

- Q2: four-law habit design loop (multi-step, produces a designed habit) → yes
- Q5: implicit; the book asks the reader to audit current habits but doesn't formalize the audit → trivial

Decision: **single**. One skill, `atomic-habits-apply`. Revisit if operators start asking it to evaluate existing habits separately from designing new ones.

## Output

Append the decision and rationale to `method.json` from Phase 1. This becomes the `Diagnose/apply split decision` line in the Phase 3 SkillForge handoff.
