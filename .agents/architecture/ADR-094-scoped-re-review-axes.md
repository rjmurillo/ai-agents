---
id: ADR-094
status: proposed
date: 2026-08-15
decision-makers: []
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-094: Scoped re-review re-runs only the axes that flagged

## Status

Proposed

Draft for human maintainer review. Not accepted, not enacted. `AGENTS.md:44`
triggers the `adr-review` skill on any `ADR-*.md` edit, and `ADR-073:156`
places that debate before human approval, not after. `.claude/rules/governance.md`
MUST-1 (human approval) states the general principle but is scoped to
`.agents/governance/**`, so it does not itself define this ADR's acceptance path.

## Date

2026-08-15

## Context

`/review` runs 15 subagent axes sequentially on every invocation and caches
nothing across runs, so a one-line fix to one WARN costs the same as the first
review of the whole diff. `/ship` requires a SHA-bound review marker on HEAD, and
every new code commit invalidates that marker, so each fix round forces another
full 15-axis run. Across the recorded convergence incidents that multiplier is
the dominant cost in PR review cycles.

### What the cost is, measured

| Source | Measurement |
|---|---|
| `.claude/skills/review/SKILL.md:71,85,92` | 15 axes per run: Stage-1 `spec-compliance`, 11 Stage-2 canonical axes, 3 chained skills |
| `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` | PR #1887: 46 hours, 69 commits, 254 conversations, 11+ review rounds |
| `.agents/governance/CI-FEEDBACK-SUBLOOP.md:11` | PR #1965: 58 commits, 18 rounds. PR #1979: 30 commits, 18 rounds |
| `.agents/analysis/009-phase1-agent-comment-baseline.md` | 20 PRs, 6 scoped CI review agents, 120 runs: 182 comments, 24% signal ratio |

At 18 rounds, a PR that re-reviews before each ship attempt spends 18 x 15 = 270
axis invocations. The `/review` axes and the 6 CI agents in the 009 baseline are
different populations; the 24% figure bounds the value of review fan-out
generally, and it is not a measurement of `/review` itself.

### The amplifier is the marker, not `pr-autofix`

`pr-autofix` does not invoke `/review`. Grepping `.claude/commands/pr-autofix.md`
for `/review` returns only prose about review threads. Its T3 and T4 tiers walk
the review-thread lifecycle; they do not run the axes. The real amplifier is the
`/ship` gate:

- `.claude/skills/review/SKILL.md:164-166`: "the marker is valid only while its
  parent (the reviewed tip) is HEAD's parent. Land any new code commit and the
  marker no longer sits on HEAD's parent, so the review is correctly treated as
  stale."
- `.claude/commands/ship.md:109`: "Exit `1` means no marker, a stale marker, or
  new code landed after review."

That coupling is correct and should stay. It is also what makes every fix round
pay for a full re-review, because the only way to refresh the marker today is to
run all 15 axes.

### What the marker already records

The marker trailer is `Reviewed-By: /review@<comma-separated-axis-list> on
<reviewed-tip-sha>` (`.claude/skills/review/SKILL.md:152`). It already names the
axis set that ran. Nothing reads that list as a scope claim today;
`validate_review_marker.py` checks the SHA binding. The list is the hook this
decision hangs the safety property on.

## Decision

Add an explicit scope flag to `/review`: `/review --axes=<comma-separated-list>`.
A scoped run executes the Stage-1 gate plus only the named Stage-2 and chained
axes, marks every other axis `SKIPPED`, and **MUST NOT write a review marker**.

The full run stays the default and stays unchanged. `/review` with no `--axes`
runs all 15 axes and remains the only thing that can satisfy `/ship`.

The intended workflow: an initial full run finds the flagged axes, since nothing
is known to scope against yet. Each subsequent fix round re-runs Stage-1 (which
always runs on a scoped invocation, per contract change 7 below) plus the k
flagged axes, paying k+1 axes per round instead of 15. Run the full `/review`
once at the end to earn the marker. At 6 total rounds (1 initial full run, 4
scoped fix rounds, 1 final full run) and 2 flagged axes, that is
15 + 4x(1+2) + 15 = 42 axis invocations against 6x15 = 90 today, a 53%
reduction, with the merge gate exactly as strong as it is now.

This ADR does **not** promote `.agents/governance/CI-FEEDBACK-SUBLOOP.md` to
normative. See Alternatives.

### Why a scoped run cannot write a marker

An axis that did not run has no verdict. If a scoped run could refresh the
marker, `/ship` would accept a marker naming axes that never evaluated the
shipped SHA, and a fix for a docs cluster could ship a security regression under
a green marker. Making the scoped run marker-free keeps the gate's meaning
intact and needs no invalidation logic, no per-axis file-scope mapping, and no
new storage.

## Prior Art Investigation

### What currently exists

- **Structure being changed**: `.claude/skills/review/SKILL.md`, the Convergence
  contract (REQ-008-04) and Process steps 1 to 8. Mirrored wholesale into
  `src/copilot-cli/skills/review/` by the build pipeline.
- **When introduced**: the axis-convergence work under
  `.agents/archive/plans/review-axes-convergence.md`; the marker under issue
  #1938; the superset contract under issue #1934.
- **Constraints that drove it**: `/review` must be a strict superset of CI so a
  local run never surfaces fewer findings than CI, and it must work in a vendored
  plugin install with no `.agents/` access.

### Historical rationale

The full-fan-out design is deliberate. REQ-008-04 states `/review` "is a strict
superset of CI: any finding CI surfaces, `/review` will surface first locally."
Running every discovered axis every time is the cheapest way to guarantee that
property. No caching was omitted by oversight; there was no cache to omit,
because a full run was the only defined mode.

### Why change now

The original problem has not changed: a pre-merge review still must be a
superset of CI. What changed is the observed cost of the retry path, which the
original design did not price. The superset guarantee is needed once per shipped
SHA, not once per intermediate commit. This ADR keeps the guarantee at the ship
boundary and drops it only where nothing consumes it.

Risk of change: the flag becomes the habitual invocation and reviewers stop
running the full pass. The marker prohibition is the structural answer, because
`/ship` still refuses to move without a full run.

## Rationale

### Alternatives considered

| Alternative | Pros | Cons | Why not chosen |
|---|---|---|---|
| Promote CI-FEEDBACK-SUBLOOP.md whole (5 phases, `fix(subloop):` convention, session schema, CI scoping) | Names the whole procedure; already written | Four of five parts are not the cost driver; `fix(subloop):` already fits the existing `fix` type (`CI-FEEDBACK-SUBLOOP.md:58`), so no commit-format allowlist change is needed, but promoting the doctrine to normative governance still needs the `CONSENSUS.md` cross-role vote per governance MUST-3, plus the deferred session-schema and CI-scoping follow-ups | Largest approval surface for the same latency win |
| `/review --axes=<list>`, marker-free (chosen) | One skill contract, testable, no governance surface, keeps `/ship` gate strength | Author must pick the axis list; no automatic invalidation | Smallest change that removes the measured cost |
| Cache per-axis verdicts keyed on diff hash | Fully automatic; no caller decision | Needs a per-axis file-scope map that does not exist (axes are prompts, not filters); cache invalidation is the hard half | Inventing an axis-to-path mapping is speculative and unfalsifiable today |
| Run the 15 axes in parallel instead of sequentially | No contract change; large wall-clock win | Does not reduce token spend, which is the reported driver; 15 concurrent subagents may exceed harness limits | Orthogonal. Worth doing separately; does not fix cost |
| Do nothing | Zero risk | The measured incidents recur; the plugin keeps losing installs | The cost is documented across three PRs and one baseline study |

### Disagreement with the existing sub-loop proposal

The sub-loop document is right about the mechanism and wrong about the packaging.
Its phase 4 (`CI-FEEDBACK-SUBLOOP.md:28`, "Re-run only the axes that flagged the
original cluster, not all axes") is the fix. The surrounding four phases restate
the existing lifecycle with a "sub-" prefix, which adds vocabulary without adding
enforcement.

Two specific objections:

1. **`fix(subloop):` has no consumer.** The document itself says the convention
   exists so "the CI side (follow-up below) reduce reviewer scope only for
   structured turns". That CI follow-up is deferred. A commit convention whose
   only reader is a deferred change is dead weight, and it puts a new token into
   the commit-format contract that every contributor must learn.
2. **Prose cannot be gated.** A doctrine telling authors to cluster and ladder is
   unenforceable; nothing fails when it is ignored. A flag with a validator and
   tests either works or does not. Prefer the mechanism.

Leave `CI-FEEDBACK-SUBLOOP.md` as a non-normative description. It is useful
reading. It does not need promotion for the cost fix to land.

### Trade-offs

Buys token cost and wall-clock latency on the retry path. Sacrifices per-run
completeness: a scoped run's output is a subset and is not review evidence for
anything. The sacrifice is confined to intermediate commits, which nothing
downstream consumes.

## Contract changes to `.claude/skills/review/SKILL.md`

`src/copilot-cli/skills/review/` is generated from this file by the build
pipeline and MUST NOT be hand-edited; regenerate it in the same change per
`.claude/rules/generated-artifacts.md`.

| # | Location | Change |
|---|---|---|
| 1 | Frontmatter `argument-hint` (line 5) | `branch-or-pr-number [--axes=<comma-list>]` |
| 2 | Triggers table (lines 19-23) | Add row: `/review --axes=a,b` runs the Stage-1 gate plus only the named axes, writes no marker |
| 3 | Convergence contract, REQ-008-04 (lines 27-31) | State that the strict-superset-of-CI guarantee holds for a full run only. A scoped run is a declared subset, is not a superset of CI, and cannot satisfy `/ship`. |
| 4 | Process, new step 0 | Parse `--axes`. Validate each name against the union of the stems discovered from `references/*.md` (the 11 Stage-2 canonical axes) and the three chained skill names (`code-qualities-assessment`, `golden-principles`, `taste-lints`), since the latter are sibling skills, not `references/` files (`review/SKILL.md:47-49`). An unknown name is a config error: exit 2 before any axis runs. Empty or absent means full run. |
| 5 | Process step 4 (line 71) | "Run every Stage-2 canonical axis" becomes "Run every Stage-2 canonical axis in the active set", where the active set is the discovered set filtered by `--axes` when present |
| 6 | Process step 5 (lines 85-89) | The 3 chained skill axes run only when named in `--axes`, or always on a full run |
| 7 | Process step 7 (line 92) | Axes outside the active set are recorded `SKIPPED (not in --axes scope)` and excluded from the `merge_verdicts` input. They are not `UNKNOWN` (which means "ran, unparseable") and never `PASS`. |
| 8 | Output table (lines 108-128) | Keep all 15 rows on a scoped run so the reader always sees what did not run. Append `(scoped: a,b,c)` to the FINAL VERDICT line. |
| 9 | Marker section (lines 139-170) | Add: a scoped run MUST NOT write a marker, on any verdict. Stage-1 always runs, so the existing short-circuit is unaffected. |
| 10 | Verification checklist (lines 181-187) | Add three boxes: unknown axis name exits 2; scoped run writes no marker; out-of-scope axes render `SKIPPED`, not `PASS`. |

`spec-compliance` always runs regardless of `--axes`. It is the Stage-1 gate and
its `CRITICAL_FAIL` short-circuit is the cheapest correctness check in the run.

`validate_review_marker.py` gains one rule: a trailer whose axis list is not an
exact match (set equality) of the discovered axis set exits 1. This catches a
missing axis, an unknown axis, and a duplicate axis alike; a strict-subset check
alone would miss a list that mixes one real axis with one unknown name, because
that list is not a subset of the discovered set at all. This is defense in
depth. A scoped run should never write a marker in the first place, and a
hand-written or partially-updated marker must not pass.

## Required tests

`.claude/rules/claude-agents.md` MUST-7 binds documented exit codes to assertions,
and `.claude/rules/generated-artifacts.md` binds customer-facing artifacts to a
runtime-contract test. The axis-set resolution therefore MUST live in a script,
not in prose, so it is executable and testable: add
`.claude/skills/review/scripts/resolve_axis_set.py`.

New tests under `tests/skills/review/`:

| Test | Class | Assertion |
|---|---|---|
| `--axes=architect,security` | positive | Active set is those two plus `spec-compliance`; the other 12 are absent |
| No `--axes` | positive | Active set is all 15 discovered axes |
| `--axes=nonexistent` | negative | Exit 2, no axis runs, error names the unknown stem |
| `--axes=` empty, duplicates, surrounding whitespace, mixed case | edge | Whitespace around each name is trimmed. Matching is exact-case against the lowercase-hyphenated axis stems; mixed case is an unknown name, exit 2. A duplicate name in the list is a config error, exit 2. `--axes=` present but empty is a config error, exit 2, distinct from `--axes` absent (full run) |
| Marker on a scoped run | negative control | No `Reviewed-By` trailer is written on any verdict, including PASS |
| `validate_review_marker.py` with a subset axis list | negative | Exit 1 |
| `validate_review_marker.py` with the full axis list on a valid SHA binding | positive control | Exit 0, proving the subset test fails for the right reason |
| Merge input on a scoped run | positive | `SKIPPED` axes are not passed to `merge_verdicts`; an all-PASS scoped run yields PASS and still writes no marker |

The marker tests are the load-bearing ones. They are the negative controls that
prove a scoped run cannot become ship evidence.

## Consequences

### Positive

- Fix rounds cost k+1 axes instead of 15 (Stage-1 always runs). At 6 total
  rounds (1 initial full run, 4 scoped fix rounds, 1 final full run) and 2
  flagged axes, 42 axis invocations against 90.
- `/ship` gate strength is unchanged: a full run is still the only marker source.
- No new governance surface. No commit-format change, no session-schema change,
  no CI change.
- The axis list is already in the marker trailer, so the safety check needs no
  new artifact.

### Negative

- The caller picks the axis list, and a wrong pick means a real finding is not
  re-checked until the final full run. The final run catches it; the cost is one
  late round.
- Two invocation modes to document and to keep correct in both plugin trees.
- A scoped output is easy to screenshot and misread as a review. The `(scoped:)`
  suffix and the 15-row table with `SKIPPED` are the mitigation.

### Neutral

- `CI-FEEDBACK-SUBLOOP.md` stays non-normative and unchanged.
- Parallel axis execution stays available as a separate, orthogonal improvement.

## Impact on dependent components

| Component | Dependency | Required update | Risk |
|---|---|---|---|
| `.claude/skills/review/SKILL.md` | Direct | The 10 contract changes above | Medium |
| `src/copilot-cli/skills/review/` | Generated mirror | Regenerate in the same change; never hand-edit | Medium |
| `.claude/skills/review/scripts/validate_review_marker.py` | Direct | Reject a strict-subset axis list | Low |
| `.claude/skills/review/scripts/resolve_axis_set.py` | New | Axis-set resolution and validation | Low |
| `.claude/commands/ship.md` | Indirect | No change. The marker check already rejects anything that is not a valid full-run marker | Low |
| `.claude/commands/pr-autofix.md` | None | No change. It does not invoke `/review` | None |
| `tests/skills/review/` | Direct | The 8 tests above | Low |

## Follow-ups named by CI-FEEDBACK-SUBLOOP.md

| Follow-up | This ADR | Reason |
|---|---|---|
| Governance promotion of the sub-loop doctrine | **Not covered. Recommend against.** | The mechanism carries the cost fix; the doctrine adds unenforceable prose and a cross-role consensus requirement |
| Session-log `sub_loop_turns` array | **Deferred** (#2014) | Observability, not cost. Additive to the schema; can land any time without blocking this |
| CI workflow scope-reduction on `fix(subloop):` heads | **Deferred** (#2014) | Different surface, different blast radius, needs its own ADR. `.github/workflows/ai-pr-quality-gate.yml` already runs 10 separate per-axis review jobs aggregated at `aggregate` (`:295-598`, `aggregate:` job at `:607`), so a host exists; what is missing is the conditional logic to skip a job based on the `fix(subloop):` commit prefix, which this ADR does not design |
| `fix(subloop):` commit convention | **Recommend dropping** | Its only stated consumer is the deferred CI change |
| Worked retrospective example | **Deferred** | Write it after the first PR runs the scoped mode end to end |

## Open items for the reviewing maintainer

1. `AGENTS.md` cites `.agents/governance/CI-FEEDBACK-SUBLOOP.md` in its Skill-First
   boundaries block, which is always-loaded context, while the document's own
   status line says it "does not change governance expectations". A non-normative
   proposal is being routed to as guidance. Worth resolving whichever way this
   ADR goes.
2. `decision-makers` is empty. The template requires it and this draft cannot
   populate it.
3. No measurement of `/review`'s own signal ratio exists. The 24% figure is from
   6 CI agents, a different population. A per-axis signal measurement would show
   whether some of the 15 axes should be dropped outright rather than scoped,
   which would beat this ADR on the same cost axis.

## Related decisions

- ADR-064: commands-to-skills migration. `/review` is a skill, not a command.
- ADR-093: a local run clears a red remote check only when it is the same
  checker. The same reasoning underlies the marker prohibition here: a subset run
  is a different check.

## References

- `.agents/governance/CI-FEEDBACK-SUBLOOP.md`. The proposal this narrows.
- `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`. The 46-hour incident.
- `.agents/analysis/009-phase1-agent-comment-baseline.md`. The 24% signal baseline.
- `.claude/rules/governance.md`. Approval path this draft does not bypass.
- `.claude/rules/generated-artifacts.md`. Mirror regeneration and runtime-contract tests.
- Issue #1938. SHA-bound marker design.
- Issue #2014, epic #1933. Sub-loop origin and the lifecycle-convergence epic.
