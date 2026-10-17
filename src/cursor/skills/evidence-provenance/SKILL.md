---
name: evidence-provenance
description: Decide whether evidence is independent or the same loop twice, and whether a named check was run. Classifies lineage (premise, origin, time, mutability, environment), keeps authority a separate axis, and reports VERIFIED, NOT RUN, UNAVAILABLE, or FAILED. Use when you say `is this independent evidence`, `did the reviewer confirm this`, `closed loop`, or `count the confirmations`. Do NOT use to report progress (use the voice rule) or to pick the governing validator (use validation-authority).
metadata:
  capability:
    kind: reusable-primitive
    owns:
      - evidence-provenance
    status: active
  routing:
    role: conditional-adjunct
    invoker: review
    trigger: review or a test gate must decide whether two pieces of evidence confirm a claim independently
    user-facing: true
---

# Evidence Provenance

> A second artifact is not a second proof. Count loops, not files.

Owns one invariant: evidence produced by the same reasoning loop as the
artifact it validates is one evidentiary loop, unless something outside that
loop can falsify it. It does not reject creator-authored tests, require a human
reviewer, require several models, or force an expensive or unavailable gate.

## Triggers

`is this independent evidence`, `did the reviewer confirm this`, `closed loop`,
`count the confirmations`, `which checks actually ran`

## The invariant

```text
agent reads requirement R
   +--> writes implementation I
   +--> writes new test T from the same reading

I + T  = useful evidence about I
I + T != two independent confirmations of R
```

Creator tests stay valid. They answer "does I do what I was written to do". They
cannot answer "was R read correctly", because both artifacts inherit one reading.

## Process

1. **List the claim and the artifact.** Name the artifact, its revision, and the
   premises it was built from (the reading of R, the generator, the fixture
   source).
2. **Record each piece of evidence with its lineage.** The fields and their
   values are in `references/lineage-model.md`. Two rules decide most cases:
   - Shared premise or inheritance joins the subject's loop. A reviewer who is
     handed the implementer's conclusion, or an expected output made by the
     implementation's generator, is in that loop whatever agent produced it.
   - Lineage you cannot state is lineage you cannot count. An item with no
     recorded premises is never independent.
3. **Classify.** Write the record as JSON and run:

   ```bash
   python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/evidence-provenance/scripts/classify_lineage.py" <record.json>
   ```

   An item whose `bound_to` names a different artifact or revision is always
   rejected (`binding-mismatch`), not downgraded. Add `--promotion` when the
   evidence gates a deployment: every item then also needs a `bound_to` with
   artifact, revision, validator, command, and result, or it is rejected as
   `binding-missing`.
4. **Read the verdict.**

   | Verdict | Meaning |
   |---------|---------|
   | `CORROBORATED` | At least one independent loop verified the claim. `independent_loops` is the count to cite. |
   | `SINGLE_LOOP` | Verified, but only inside the subject's loop. Cite it as one loop, however many files. |
   | `FALSIFIED_BY_INDEPENDENT_OBSERVATION` | An independent item with normative or executable-runtime authority failed. It wins over any same-loop pass. |
   | `FAILED` | An item failed without independent authority. Investigate before citing anything else. |
   | `NO_VERIFIED_EVIDENCE` | Nothing verified, or every item was rejected for a binding problem (`binding-mismatch` or `binding-missing`). |

5. **Cite the count the classifier gives.** Set `claimed_independent` to the
   number you intend to write. A claim above `independent_loops` exits 1 as
   `inflated-confidence`.

Independence and authority are separate. An independent heuristic is a weak
loop; a same-loop run of the real runtime is strong evidence about I and still
one loop. The output carries both, so a consumer never has to collapse them.

## Strengthening evidence

| Evidence | Why it counts |
|----------|---------------|
| Pre-existing test that was red and is now green | Written before the change from a different premise, and the change did not edit it. |
| Observation of the real runtime, service, or tool | Its premise is the system itself, not a reading of it. |
| Reviewer who rebuilt the result from primary evidence | Own premises, no inheritance from the implementer. |
| New test that fails when the defect is restored | Marked `discriminating`. It proves the test can fail. It is still one loop for the premise. |

## Walk or do not name

When a relevant check is cheap and available, run it before you cite it. Do not
strengthen a conclusion with a check you chose not to run.

| State | Use it when |
|-------|-------------|
| `VERIFIED` | You ran the check and observed it pass. |
| `NOT RUN` | You did not run it. It may not support a conclusion. |
| `UNAVAILABLE` | The tools or environment could not run it. Say why. |
| `FAILED` | You ran it and it failed. |

Any other wording for a named check ("should run X", "pending", no state) exits
1 as `named-without-state`. A `NOT RUN` or `FAILED` item used as support exits 1
as `unverified-support`. A cheap, available check left `NOT RUN` but not cited
returns the warning `cheap-gate-not-run`. Expensive, destructive, or
credentialed checks are never mandatory; the duty is to report their state.

## Composition

This skill owns the lineage and state semantics and nothing else.

| Concern | Owner |
|---------|-------|
| Strong, falsifiable tests and mutation controls | the testing rule |
| Equivalence without copied contracts | the canonical-source evidence contract (#5399) |
| Wording of progress and completion reports | the voice rule, "Clear The Gate Or Drop The Claim" |
| Which validator governs a change | `validation-authority`, `analysis-provenance` |
| Review verdicts and independent reviewer behavior | `review` (technical-review) |

Consumers name this skill by its id and link here. They do not copy this
skill's tables.

## Scripts

| Script | Purpose | Exit codes |
|--------|---------|------------|
| `classify_lineage.py` | Loops, independence, authority, verdict, violations | `0` classified, `1` violation or failed claim, `2` bad input |

Exit `0` means classified, not passed. `NO_VERIFIED_EVIDENCE` exits `0`, even
under `--promotion` with every item rejected. A promotion gate must also require
a `CORROBORATED` or `SINGLE_LOOP` verdict and an empty `rejected` list.

The script is stdlib-only. It trusts the lineage fields it is given, so a
fabricated premise list defeats it. Check the fields against the diff and the
transcript, not against the agent's own summary.

## Verification

- [ ] Every cited confirmation has a lineage record, including each reviewer.
- [ ] The number of confirmations cited is at most `independent_loops`.
- [ ] Every named check carries `VERIFIED`, `NOT RUN`, `UNAVAILABLE`, or `FAILED`.
- [ ] A promotion record was classified with `--promotion` at the final head.
