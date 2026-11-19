# ADR Debate Log: ADR-123 Skills Declare the Artifacts They Read and Write

## Summary

- **Rounds**: 3 of 10
- **Prior debate log**: none
- **Outcome**: Consensus
- **Final Status**: accepted

Panel: architect, critic, independent-thinker, security, analyst, high-level-advisor.
Constraint from the maintainer: type the existing `metadata.inputs` and `metadata.outputs`.
No seat disputed that choice.

## Round 1 Summary

### Votes

| Agent | Vote |
|-------|------|
| architect | Disagree-and-Commit |
| critic | Block |
| independent-thinker | Disagree-and-Commit |
| security | Disagree-and-Commit |
| analyst | Disagree-and-Commit |
| high-level-advisor | Disagree-and-Commit (strategic assessment: CONCERNS) |

No seat raised a P0. Every factual claim checked by two or more seats was VERIFIED.
All six seats marked the debate-log citation REFUTED, because this log did not exist yet.

### Key Issues Addressed (P1 unless noted)

| # | Issue | Raised by | Resolution in revision |
|---|-------|-----------|------------------------|
| 1 | Items 4 and 5 force declarations on lifecycle skills, contradicting "five skills migrate" and "optional". | architect, critic, independent-thinker, high-level-advisor | New item 6 lists the eight required skills. "Optional" now applies only outside the lifecycle. |
| 2 | Item 6 let `intents` certify reachability, reversing DESIGN-036's no-self-certification rule. | architect, critic, independent-thinker | Moved to a DESIGN-036 amendment. Reachability now needs a resolver result that routes an intent to exactly that skill. |
| 3 | Item 7 blocked on prose, a DESIGN-036 rejected alternative, and failed six phrases on day one. | all six | Moved to DESIGN-036 as a report-only phrase report. Its grammar is defined: lead-in, clause end, quote characters, and `ambiguous` counts as a miss. All six misses gain intents in the same change. The "drop the quote marks" remedy is removed. |
| 4 | Item 4's helper walk left cycles, two-hop chains, repo-local helpers, and shared helpers undefined. | critic, architect | Item 4 now defines the walk: first lifecycle skill wins, terminal invokers give no credit, repo-local never credits shipped, and a cycle with declared outputs is a defect. |
| 5 | `path` grammar was too loose (CWE-22). | security | Paths are relative to the artifact root, match a fixed lowercase grammar, and are never opened by the gate. |
| 6 | Paths ignored `AI_AGENTS_ARTIFACT_ROOT`. | security, critic | Paths resolve under `artifact_dir`; the example became `plans/active/`. |
| 7 | No YAML loader was named. | security | The gate uses `_UniqueKeySafeLoader`. `yq` is named a read-only aid. |
| 8 | Untrusted inputs were not addressed. | security | Item 1 states a declared input is data and grants no authority. |
| 9 | Handoff matcher undefined (P2). | critic | Item 5 fixes a one-line shape and requires set equality with credited outputs. |
| 10 | Three decisions in one record (P2). | architect, high-level-advisor | Routing evidence items moved to DESIGN-036. The record now holds one decision. |
| 11 | Shipped versus repo-local undefined (P2). | high-level-advisor | Item 3 names `metadata.distribution: repo-local`. |
| 12 | Byte cap and fixture headroom not budgeted (P2). | analyst | Consequences records the 24576-byte cap, the F6 headroom, flow-style YAML, and offsetting trims. |
| 13 | Confirmation had no threshold (P2). | architect | The resolver corpus must stay at 100 percent, from 38 of 38. |
| 14 | `pr-review` and `pr-autofix` cycle left undecided (P2). | high-level-advisor | The record states `pr-review` becomes a routed front door in the same change. |
| 15 | Handoff duplicates metadata; defer it (P2). | independent-thinker, high-level-advisor | Kept, per the maintainer's approved plan. The Rationale table records why it is not dropped. Dissent carried below. |
| 16 | One producer per artifact hides edges for commit-writing skills (P2). | independent-thinker | Consequences states the graph is a lower bound. Item 2 says other writers stay undeclared. |

### Dissent Carried

- independent-thinker and high-level-advisor prefer deferring the Handoff line until it can be generated.
- security recommends that skills with `user` or `repo` inputs declare `depends-on: [untrusted-content-handling]`. The revision states the data rule but does not require the dependency.

## Round 2 Summary

### Votes

| Agent | Vote |
|-------|------|
| architect | Disagree-and-Commit |
| critic | Accept (changed from Block) |
| independent-thinker | Disagree-and-Commit |
| security | Accept |
| analyst | Accept |
| high-level-advisor | Disagree-and-Commit |

Consensus: six of six Accept or Disagree-and-Commit. No P0.

### Key Issues Addressed

| # | Issue | Raised by | Resolution |
|---|-------|-----------|------------|
| 17 | Handoff set equality forced an edit to `review` whenever a helper declared an output (P1). | independent-thinker, high-level-advisor | `Writes:` must name the skill's own outputs and may name only credited outputs. |
| 18 | The walk from `adr-review` reaches a repo-local invoker cycle (P1). | architect | A shipped skill's walk stops at its first repo-local invoker. A cycle is the revisited segment only. |
| 19 | The resolver root for the evidence layer was the resolver's own location, not the gate's repo root (P1). | architect | DESIGN-036 names `<repo_root>/src/claude/skills` and bare-name comparison. |
| 20 | `$` accepts a trailing newline; YAML types unchecked (P2). | security, architect, independent-thinker | `re.fullmatch` and type checks stated in item 1. |
| 21 | "Lifecycle skill" collides with the `lifecycle` routing role (P2). | critic, high-level-advisor | Defined as a member of `LIFECYCLE_ORDER`. |
| 22 | Whether an optional input satisfies the consume rule (P2). | critic | Any declared input counts; only required inputs count for the no-later rule. |
| 23 | PR #6273 did not set the invokers (P2, claim REFUTED). | architect, independent-thinker, high-level-advisor | Corrected: PR #5922 set them on 2026-09-24; PR #6273 marked them repo-local on 2026-10-11. |
| 24 | Fixtures F1 and F2 also load `review`; the 100-byte headroom floor (P2). | analyst | Consequences names F1, F2, F6 and the floor. |
| 25 | Reachability via intents is a collision check, not user reachability (P2). | independent-thinker | DESIGN-036 says what it proves and what it does not. |
| 26 | Phrase report scope (P2). | high-level-advisor | The report prints the count of front doors without `intents`. |
| 27 | `LIFECYCLE_ORDER` stated as present (P2, claim REFUTED as current state). | security | Reworded as "this change adds". |

### Dissent Carried

- independent-thinker and high-level-advisor still prefer generating the Handoff line over writing it by hand.
- security's recommendation on `depends-on: [untrusted-content-handling]` stands as advisory.

## Round 3 Summary

Confirmation of the round 2 fixes, rows 17 to 27, run as one pass through all six seat lenses.

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Accept |
| independent-thinker | Disagree-and-Commit (Handoff generation preference stands) |
| security | Accept |
| analyst | Accept |
| high-level-advisor | Disagree-and-Commit |

No P0 or P1. Every claim added in round 2 was VERIFIED.

### Key Issues Addressed (all P2)

| # | Issue | Resolution |
|---|-------|------------|
| 28 | Type checks omitted `source` and the list-of-mappings shape. | Item 1 names both. The gate checks `source` is a string. |
| 29 | Status said "round 2 of two" while round 3 ran. | Status reads "round 2, confirmed in round 3". |
| 30 | Item 6 said items 4 and 5 require all eight skills; item 5 binds six. | Item 6 says this change declares data on those eight. |

### Noticed Outside Scope

- `scripts/validation/skill_size.py:71` comments "max body is 24,210 B", but rendered `ship` is 24456 bytes. The comment is stale.
