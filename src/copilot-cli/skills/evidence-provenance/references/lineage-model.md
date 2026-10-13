# Lineage Model

Field reference for `classify_lineage.py`. The fixtures in
`tests/skills/evidence-provenance/fixtures/` are the executable examples.

## Record

```json
{
  "claim": "R holds",
  "subject": {"artifact": "pkg", "revision": "r2", "premises": ["interp:R"]},
  "claimed_independent": 1,
  "evidence": [
    {
      "id": "legacy-test",
      "state": "VERIFIED",
      "origin": "pre-existing",
      "created": "pre-existing",
      "authority": "executable-runtime",
      "environment": "synthetic",
      "premises": ["contract:ext-v1"],
      "inherits_from": [],
      "changed_by_subject": false,
      "discriminating": false,
      "used_as_support": true,
      "bound_to": {"artifact": "pkg", "revision": "r2", "validator": "pytest",
                   "command": "pytest tests/x", "result": "pass"}
    }
  ],
  "checks": [{"check": "ruff check", "state": "VERIFIED", "cheap": true, "available": true,
              "used_as_support": true}]
}
```

## Evidence fields

| Field | Values | Role |
|-------|--------|------|
| `state` | `VERIFIED`, `NOT RUN`, `UNAVAILABLE`, `FAILED` | Required. Only `VERIFIED` corroborates. |
| `origin` | `same-loop`, `independent-reviewer`, `human`, `external-system`, `pre-existing` | Who produced it. Never decides independence alone. |
| `created` | `pre-existing`, `during-task` | Time axis. |
| `authority` | `normative`, `executable-runtime`, `derived`, `heuristic` | How much the item can settle. Separate from independence. |
| `environment` | `synthetic`, `real` | A fixture or the system being claimed about. |
| `premises` | list of ids, or absent | The assumptions the item was derived from. Absent or empty means lineage unknown. |
| `inherits_from` | evidence ids, or `subject` | Conclusions the item was handed instead of rebuilding. |
| `changed_by_subject` | boolean | The evaluated actor edited this item. |
| `discriminating` | boolean | A restored defect made it fail. Recorded, not counted as independence. |
| `used_as_support` | boolean | The report leans on this item. |
| `bound_to` | artifact, revision, validator, command, result | Ties the item to one candidate. |

## Rules

An item is independent when all of these hold:

1. Its lineage is known (`premises` present and not empty).
2. It shares no premise with the subject and inherits nothing from a member of
   the subject's loop. Loops form by shared premise or inheritance, across items
   as well as against the subject.
3. The subject did not change it.
4. It is not a same-origin synthetic artifact made during the task. A
   same-origin observation of a real runtime, or a pre-existing artifact,
   passes this test.

`independent_loops` counts distinct loops among independent, verified items. Two
independent items that share a premise are one loop.

A rejected item (`binding-mismatch`, `binding-missing`) is removed before
grouping. It cannot link loops and cannot count. Rejection does not launder
inheritance: an item that inherits from a rejected item, directly or through a
chain of accepted items, is not independent
(`inherits-rejected-evidence`). The conclusion it was handed came from evidence
that cannot speak for this artifact revision.

## Verdict order

1. Independent item with `normative` or `executable-runtime` authority in state
   `FAILED`: `FALSIFIED_BY_INDEPENDENT_OBSERVATION`.
2. Any accepted `FAILED` item: `FAILED`.
3. Independent `VERIFIED` item: `CORROBORATED`.
4. Any `VERIFIED` item: `SINGLE_LOOP`.
5. Otherwise `NO_VERIFIED_EVIDENCE`.

## Delegation and resume

Independence is derived from recorded lineage, not stored as a flag. A handoff
that carries the record reproduces the same classification. A handoff that
carries only a conclusion drops `premises`, and the item falls to
`lineage-missing`. Carry the record, not the verdict.

## Scenarios

| Scenario | Fixture | Classification |
|----------|---------|----------------|
| Implementation and new test from one reading | `s1_same_interpretation` | one loop |
| Pre-existing red test turns green | `s2_preexisting_red_to_green` | independent, authoritative |
| New test fails when the defect returns | `s3_mutation_restoration` | `discriminating`, one loop |
| Generated expectation, shared generator | `s4_shared_generator` | one loop |
| Real runtime contradicts the expectation | `s5_runtime_contradicts_generated` | independent observation wins |
| Reviewer inherits the conclusion | `s6_reviewer_inherits_conclusion` | one loop, claim inflated |
| Reviewer rebuilds from primary evidence | `s7_reviewer_reconstructs` | independent |
| Cheap gate named as "should run" | `s8_should_run_pending`, `s8b_state_missing` | fails Walk-or-Don't-Name |
| Gate unavailable, reported as such | `s9_unavailable_reported` | passes |
| Doubled confidence claim | `c1_negative_control_doubled_confidence` | blocked; passes if grouping is bypassed |
| Stale revision, other artifact | `x1_stale_revision`, `x2_other_artifact` | rejected |
| Promotion bindings | `x3_promotion_complete`, `x4_promotion_missing_command` | accepted, rejected |
| Lineage lost in a handoff | `x5_lineage_dropped_on_handoff` | not independent |
| Reviewer inherits from a rejected item | `x6_inherits_rejected_missing_binding`, `x7_inherits_stale_revision` | not independent, claim inflated |
