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

## Record fields

| Field | Values | Default | Role |
|-------|--------|---------|------|
| `claim` | string | empty | The statement under test. |
| `subject` | object with `artifact`, `revision`, `premises` | required | The candidate whose loop other items are compared against. |
| `claimed_independent` | integer | absent | The confirmation count the author will cite. Any other type exits `2`. |
| `evidence` | list of evidence objects | empty list | Items that support or contradict the claim. |
| `checks` | list of check objects | empty list | Named gates and their state. |

## Evidence fields

Omitted fields take the default. The defaults are the weakest values, so a
minimal item is a same-origin synthetic artifact and fails with
`same-origin-synthetic`.

| Field | Values | Default | Role |
|-------|--------|---------|------|
| `id` | non-empty string, unique, not `subject` | required | Name used by `inherits_from`. |
| `state` | `VERIFIED`, `NOT RUN`, `UNAVAILABLE`, `FAILED` | required | Only `VERIFIED` corroborates. |
| `origin` | `same-loop`, `independent-reviewer`, `human`, `external-system`, `pre-existing` | `same-loop` | Who produced it. Never decides independence alone. |
| `created` | `pre-existing`, `during-task` | `during-task` | Time axis. |
| `authority` | `normative`, `executable-runtime`, `derived`, `heuristic` | `heuristic` | How much the item can settle. Separate from independence. |
| `environment` | `synthetic`, `real` | `synthetic` | A fixture or the system being claimed about. |
| `premises` | list of ids | absent | The assumptions the item was derived from. Absent or empty means lineage unknown. |
| `inherits_from` | evidence ids, or `subject` | empty list | Conclusions the item was handed instead of rebuilding. |
| `changed_by_subject` | boolean | `false` | The evaluated actor edited this item. |
| `discriminating` | boolean | `false` | A restored defect made it fail. Recorded, not counted as independence. |
| `used_as_support` | boolean | `false` | The report leans on this item. |
| `bound_to` | object: artifact, revision, validator, command, result | absent | Ties the item to one candidate. Required under `--promotion`. |

The boolean fields accept only JSON `true` or `false`. Any other value, such as
the string `"false"`, exits `2`.

## Check fields

| Field | Values | Default | Role |
|-------|--------|---------|------|
| `check` | non-empty string | required | Name of the gate. |
| `state` | `VERIFIED`, `NOT RUN`, `UNAVAILABLE`, `FAILED` | absent | Absent or any other wording exits `1` as `named-without-state`. |
| `cheap` | boolean | absent | A cheap check that is available must be run before it is cited. |
| `available` | boolean | absent | The tools and environment can run it. |
| `used_as_support` | boolean | absent | A `NOT RUN` or `FAILED` check used as support exits `1` as `unverified-support`. |

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
grouping. It cannot link loops and cannot count, but its `used_as_support` state is still checked for violations. Rejection does not launder
inheritance: an item that inherits from a rejected item, directly or through a
chain of accepted items, is not independent
(`inherits-rejected-evidence`). The conclusion it was handed came from evidence
that cannot speak for this artifact revision.

Inheritance never launders independence. An item that inherits from any
non-independent item, directly or through a chain, is not independent
(`inherits-non-independent-evidence`), whatever its own origin or premises. A
second agent's label does not change what it was handed. Items that already
carry another reason keep only that reason.

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
| Cheap gate named as "should run" | `s8_should_run_pending`, `s8b_state_missing` | fails Walk or do not name |
| Gate unavailable, reported as such | `s9_unavailable_reported` | passes |
| Doubled confidence claim | `c1_negative_control_doubled_confidence` | blocked; passes if grouping is bypassed |
| Stale revision, other artifact | `x1_stale_revision`, `x2_other_artifact` | rejected |
| Promotion bindings | `x3_promotion_complete`, `x4_promotion_missing_command` | accepted, rejected |
| Lineage lost in a handoff | `x5_lineage_dropped_on_handoff` | not independent |
| Reviewer inherits from a rejected item | `x6_inherits_rejected_missing_binding`, `x7_inherits_stale_revision` | not independent, claim inflated |
| Reviewer inherits from a non-independent item outside the subject loop | `x9_inherits_non_independent_item`, `x10_inherits_through_chain` | not independent, claim inflated |
