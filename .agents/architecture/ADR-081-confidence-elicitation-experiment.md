---
id: ADR-081
status: proposed
date: 2026-07-11
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-081: Confidence Elicitation Is a Shadow Study, Not a Shipped Gate

## Status

Proposed

## Date

2026-07-11

## Context

Issue #3016 (P3, owner-anchored, single requester, no production retro proving
the gap) proposes a metacognitive confidence-elicitation signal: before a
completion claim clears, the agent surfaces "what am I least confident about
right now?" and each item is resolved or logged as accepted-risk. The elicited
list is meant to be a routing signal into existing verification, never a
verdict, wired first into the false-completion gate
(`.claude/hooks/PreToolUse/invoke_false_completion_gate.py`), with a mandatory
calibration gate: an A/B that measures whether surfaced items actually predict
defects the critic or tests caught, and removal of the feature if they do not.

The intent is sound: measure whether a folk technique earns its place rather
than shipping it on faith. But an adversarial review of the proposal (architect plus a GPT-5.5 pass, recorded in
`.agents/analysis/ADR-081-confidence-elicitation-debate.md`) found that the
feature as specified is mechanically unbuildable, its calibration is not
runnable with current tooling, and its ground truth is circular. This ADR
records that finding and reframes the work into a buildable shape for the owner
to choose.

## Decision

**Do not ship confidence elicitation as a blocking PreToolUse hook.** A hook
cannot elicit; it can only check. Eliciting a confidence list at completion
time would require an LLM call inside a local 5-second blocking path, and the
proposal's own justification (the calibration gate) is not runnable with the
existing eval harness. Instead, if the technique is pursued at all, pursue it as
an offline shadow study, and present the owner with a simpler alternative that
delivers value now.

Concretely, the ADR offers three tracks and asks the owner to choose; it does
not close #3016 unilaterally (User Sovereignty: the owner filed it):

1. **Shadow study (the faithful reframe of the requester's intent).** Instrument
   confidence elicitation at the Stop or PR boundary only, never in the blocking
   gate. Log each session's confidence list to a study corpus. Measure whether
   surfaced items predict defects, using EXTERNAL labels only (failing tests, CI
   failures, human adjudication); critic findings may nominate candidate labels
   but never serve as labels, because the critic is another generator and
   critic-versus-self-report measures LLM agreement, not defect prediction. Size
   the corpus by a power target (about 85 labeled sessions for a moderate r=.30
   correlation, more for precision/recall), fix the effect threshold before
   running, and set a 30-day hard stop. The metric that matters is INCREMENTAL:
   defects the confidence list catches that the existing gate, tests, and PR
   checks missed. Ship a mechanism only if that study passes; otherwise close
   #3016 WONTFIX with the evidence.

2. **Gate hardening (the recommended alternative, buildable now).** Harden the
   existing false-completion gate to require test or build evidence AFTER the
   last code-changing edit, block when a failure appears after the last passing
   evidence, and surface recent failed commands in the block message. This uses
   external evidence already present in session logs, with no LLM self-report,
   no critic-as-truth, and no hand-labeled corpus. It addresses the real
   failure mode the confidence feature gestures at (claiming done on stale
   evidence) without any of its risks.

3. **WONTFIX.** If neither the study nor the hardening is worth the effort at P3,
   close #3016 with this ADR as the justification.

Whichever track the owner picks, three rules bind any future implementation:

- No LLM call inside a PreToolUse blocking path (the 5-second budget forbids it).
- No generator output used as calibration ground truth.
- "Routing, never a verdict" is only honest if the mechanism warns and routes to
  the silent-failure-hunter rather than blocking; a blocking check IS a verdict.

## Prior Art Investigation (Required when changing existing systems)

### What Currently Exists

- **The false-completion gate**: `.claude/hooks/PreToolUse/invoke_false_completion_gate.py`
  (771 lines, blocking, 5-second timeout in `.claude/settings.json`). Clears
  completion claims in commit/PR operations on external test/build evidence in
  the session log. Addresses 44 false-completion mentions across 80-plus retros
  (issues #1673, #1703, ADR-008).
- **The silent-failure-hunter agent**: `.claude/agents/silent-failure-hunter.md`,
  catches unhandled error paths in review.
- **The eval harness**: `scripts/eval/_scoring_engine.py` with `AssertionKind`
  limited to `REGEX` and `VERDICT` (`scripts/eval/_eval_agent_types.py`); scores
  fixture assertions against a response.

### Historical Rationale

The false-completion gate exists because keyword-plus-external-evidence checks
were the tractable, non-circular way to catch false "done" claims. It
deliberately avoids trusting the generator's own account of its work.

### Why Change Now

The requester wants to add the agent's own known-unknowns as a signal. The
review found the specified mechanism (a blocking hook that elicits) impossible,
the calibration (correlate self-report against critic judgment) circular, and
the harness claim (the repo can measure it) false. So "change now" is not
warranted for a shipped hook; the honest change is to reframe the measurement or
harden the existing external-evidence gate.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Ship the blocking confidence hook as specified (#3016) | Matches the request literally | A hook cannot elicit; LLM-in-gate breaks the 5s budget; calibration unbuildable; ground truth circular; likely ceremony | Mechanically impossible and unjustified as specified |
| Shadow study with external-only labels (track 1) | Faithfully measures the requester's intent; non-circular; bounded by a power target and a hard stop | Needs 85 to 320 hand-labeled sessions; real effort | Offered as the pursue-it-properly track |
| Harden the existing gate (track 2, recommended) | Buildable now; external evidence only; kills the real stale-evidence failure mode | Does not add a metacognitive signal | Recommended, but the owner may still want the study |
| WONTFIX (track 3) | Zero cost; honest at P3 with no production evidence | Leaves the requester's hypothesis untested | Offered if neither track earns the effort |

### Trade-offs

The ADR trades literal fidelity to the issue for buildability and honesty. It
preserves the requester's actual goal (do not adopt a folk technique without
measuring it) while refusing the parts that cannot be built or that reintroduce
the closed-loop trap the issue itself warns against.

## Consequences

### Positive

- No unbuildable hook is shipped; no LLM call is added to a 5-second blocking
  path; no circular calibration is institutionalized.
- The owner gets a clear, evidence-backed choice with a buildable path on each
  branch.
- Track 2 (gate hardening) is a concrete, low-risk improvement available
  immediately if chosen.

### Negative

- The requester's original design is not implemented as written.
- The shadow study, if chosen, is real labeling effort.

### Neutral

- #3016 stays open until the owner selects a track.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `invoke_false_completion_gate.py` | Direct (track 2 only) | Add evidence-after-last-edit and post-evidence-failure checks | Medium |
| Session-log schema | Direct (track 1 only) | Add a structured confidence-items field if the study is run | Low |
| Eval harness | Direct (track 1 only) | New offline correlation script; not a change to the fixture scorer | Medium |
| silent-failure-hunter | Indirect | Would be the non-blocking routing target if any warn-mode signal is added | Low |

## Implementation Notes

If track 1 (shadow study): elicit at Stop or PR boundary; persist a structured
confidence list to a study corpus; write a standalone
`scripts/eval/eval-confidence-calibration.py` that joins confidence lists to
external defect labels and reports incremental precision/recall; do not touch
`_scoring_engine.py` (its fixture-assertion model does not fit session
correlation).

If track 2 (gate hardening): extend the gate to record the last code-changing
operation's position in the log and require a passing test/build event after it;
add a block path when a failing event follows the last passing one; keep it local
Python within the existing timeout.

## Related Decisions

- Issue #3016 (this ADR's subject), #1673 and #1703 (false-completion history),
  ADR-008 (verification-based enforcement).
- ADR-080 (a sibling gated-experiment ADR proposed concurrently in PR #3028, not yet on main; both apply the
  measure-before-adopt discipline).

## References

- `.claude/hooks/PreToolUse/invoke_false_completion_gate.py`
- `scripts/eval/_scoring_engine.py`, `scripts/eval/_eval_agent_types.py`
- `.claude/agents/silent-failure-hunter.md`
- `.agents/analysis/ADR-081-confidence-elicitation-debate.md` (the review this
  ADR incorporates)
