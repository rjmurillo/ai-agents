---
id: ADR-105
status: accepted
date: 2026-08-31
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-105: Terminal-State Completion Contract

## Context

`.agents/governance/FAILURE-MODES.md` catalogs twelve recurring failure
patterns observed across 50+ retrospectives. Pattern 12, "Post-Completion
Continuation / Response Reopening," documents two manifestations traced to
issue #5404:

1. **Execution continuation.** The execution loop had no single authoritative
   completion contract, so after the frozen criteria were met, an agent
   promoted later-discovered optional refinements, adjacent cleanup, or newly
   imagined criteria into active work. Retry limits, review rounds, and
   delegation budgets remained available, and leftover budget alone kept the
   agent working because none of those backstops proved the task was done.
2. **Response reopening.** After a correct terminal result, the final
   response appended an unsolicited continuation prompt ("Want me to ...?",
   "I can also ...", "Would you like me to ...?"). No blocker and no
   requested decision remained, yet the tail created a new implicit
   continuation edge. `.claude/rules/voice.md` before this change required
   "Offer to fix proactively" and shipped flag examples ending in exactly
   this shape ("Want me to fix ...?", "Cleanup or leave?", "Want me to add
   them?").

FAILURE-MODES.md frames the cross-cutting defect as a missing artifact, not
mere verbosity: "task execution fails to make verified satisfaction
terminal, and response generation reports completion then reopens the
interaction." Its own remediation principle for every one of the twelve
patterns is the same: replace a trust-based instruction with "a blocking
gate that produces an artifact a tool can inspect." Pattern 12 had no such
artifact before this PR: completion was inferred from budget or TODO state,
not from a named, checkable predicate.

This PR ships that artifact across three canonical files plus the catalog
entry documenting it:

- `.claude/rules/builder-ethos.md` gains section 4, "Completion Is a Terminal
  State," the canonical terminal predicate.
- `.claude/rules/voice.md` gains a Completion-Tail Audit section, removing
  unsolicited continuation tails from completed responses, and a
  corresponding Quick Self-Review line.
- `.claude/skills/avoiding-manufactured-work/SKILL.md` gains a full Task
  Completion Contract: contract formation and precedence, finding
  disposition, the terminal predicate restated for the skill's own
  vocabulary, and reactivation rules.
- `.agents/governance/FAILURE-MODES.md` gains catalog entry 12 documenting
  all three as one failure mode with its own Enforcement Pattern table.

## Decision

Adopt a four-file canonical-ownership split, each file owning one part of
the contract and none duplicating another:

1. **`.claude/rules/builder-ethos.md` section 4 owns the terminal
   predicate.** When every requested deliverable satisfies the frozen task
   contract and no blocker remains, the task is terminal: stop autonomous
   work. Budgets, retry limits, review rounds, and TODO exhaustion are
   backstops, not proof of completion, and cannot keep a verified-terminal
   task active.
2. **`.claude/rules/voice.md` owns the completion-tail audit.** After
   reporting a completed requested result, remove any unsolicited offer,
   question, or invitation whose only function is to continue the
   interaction. A blocking decision, a user-requested question, a bounded
   deliverable choice, or a policy-required interaction remains allowed;
   an opt-in continuation prompt does not.
3. **`.claude/skills/avoiding-manufactured-work/SKILL.md` owns contract
   formation, precedence, disposition, and reactivation.** The skill defines
   how the frozen contract is derived before non-trivial execution, the
   five-level precedence order that resolves conflicts inside it, the
   four-way finding disposition (blocker / requested improvement / optional
   enhancement / side quest) that maps onto the skill's existing
   keep/shrink/defer/delete vocabulary, and the three conditions that can
   reopen a terminal task.
4. **`.agents/governance/FAILURE-MODES.md` documents the whole doctrine as
   failure mode 12**, cross-referencing all three files in one Enforcement
   Pattern table so a future retrospective can map an incident to a named
   pattern the same way the other eleven patterns already work.

Authorized directly by the repository owner in-session (2026-08-31): "User
authorizes both [merge or close]... Fix all valid findings and CI failures...
run the trusted completion gate, and merge." This is the same
in-session-authorization pattern ADR-099's Decision section records
("Authorized directly by the repository owner in-session"), cited here for
that precedent only.

## Prior Art Investigation

### What Currently Exists

- **Structure being changed**: `.claude/rules/builder-ethos.md` (sections 1
  to 3: Boil the Lake, Search Before Building, User Sovereignty) had no
  completion section before this PR. `.claude/rules/voice.md` had a Quick
  Self-Review checklist and an Ownership section but no completion-tail
  rule; its prior text instructed the opposite behavior ("Offer to fix
  proactively"). `.claude/skills/avoiding-manufactured-work/SKILL.md`
  already classified post-hoc findings into keep/shrink/defer/delete but had
  no pre-execution contract-formation step, no precedence order, and no
  reactivation rule.
- **When introduced**: the pre-existing keep/shrink/defer/delete workflow
  predates this PR; the terminal predicate, completion-tail audit, and full
  contract (formation, precedence, reactivation) are new in this PR, per
  issue #5404.
- **Original author and context**: FAILURE-MODES.md attributes the gap to a
  documented catalog-wide theme, not a single author decision: "Instructions
  asking agents to 'remember', 'verify', or 'check' without an observable
  artifact succeed briefly and degrade as context grows."

### Historical Rationale

Completion was inferred from budget and TODO state because those backstops
were already load-bearing for other purposes (retry limits, delegation
budgets, review-round caps) and appeared sufficient without a dedicated
predicate. Voice.md's prior "offer to fix proactively" instruction reflected
a reasonable-sounding helpfulness heuristic: surface the next possible
action rather than let the user wonder what else could be done.

### Why Change Now

The problem has not gone away on its own: FAILURE-MODES.md lists issue #5404
as live evidence of both manifestations, and the catalog's own cross-cutting
theme states plainly that a soft requirement with no feedback loop "succeeds
briefly and degrades as context grows." The risk of not changing is
continued, unmeasured recurrence of a now-named pattern. The risk of
changing is that the doctrine ships as prose only, with the runtime-parity
behavioral proof deferred (see Related Decisions); this ADR accepts that gap
explicitly rather than silently.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| Do nothing; leave completion implicit | Zero change cost | FAILURE-MODES.md #12 already documents live evidence of both manifestations (issue #5404); the catalog's own theory says an unaddressed soft requirement degrades further, not less, as context grows | Rejected: the FM catalog exists to close exactly this shape of gap |
| New standalone "completion-state" skill | Isolates the doctrine in one file a reader opens once | Duplicates concerns builder-ethos.md (belief/predicate) and voice.md (output-level enforcement) already own; risks becoming a fourth, competing source of truth against builder-ethos.md's existing Precedence Stack rather than slotting into it | Rejected: adds a file to reconcile instead of extending files with an existing seam for this exact concern |
| Extend builder-ethos.md + voice.md + avoiding-manufactured-work skill (chosen) | Matches the existing separation of concerns: ethos file states beliefs and the predicate, voice file states the output-level consequence, skill file states the operational mechanics; each already had a natural slot (builder-ethos's Precedence Stack names a section-4 owner; voice's Quick Self-Review already lists completion-adjacent checks; the skill already had the keep/shrink/defer/delete vocabulary to extend) | Couples the doctrine across three files; a reader needs all three to see the complete contract | Chosen: FAILURE-MODES.md #12's own Enforcement Pattern table lists "Terminal predicate," "Finding disposition," and "Completion-tail audit" as three separate rows across three separate files by design, not by accident |

### Trade-offs

The chosen split trades single-file readability for boundary consistency: no
existing file's scope is stretched to cover a concern it did not already
own. The cost is a reader who wants the full contract must open three files;
FAILURE-MODES.md #12 mitigates that cost by summarizing all three in one
Enforcement Pattern table with direct citations to each owning file.

## Consequences

### Positive

- One canonical terminal predicate (builder-ethos.md section 4) gives every
  agent role a single place to check "is this task done" instead of
  inferring from budget or TODO state.
- The Completion-Tail Audit in voice.md removes the exact continuation-prompt
  shapes FAILURE-MODES.md #12 names as previously shipped ("Want me to fix
  ...?", "Cleanup or leave?", "Want me to add them?").
- `avoiding-manufactured-work/SKILL.md` now states one documented contract
  for formation, precedence, disposition, and reactivation, replacing
  per-agent implicit judgment calls with a named rule a reviewer can cite.
- FAILURE-MODES.md #12 gives future retrospectives a twelfth named pattern
  and enforcement table, matching the shape of the other eleven and closing
  the gap the catalog's own cross-cutting theme describes.

### Negative

- **Precedence deviation from issue #5404's literal text.** The shipped
  skill's precedence order (`system/host requirements > mandatory safety and
  repository policy > explicit current user request > frozen task contract
  > optional improvements and preferences`) places mandatory policy above an
  explicit user request. Issue #5404's own literal precedence text ordered
  these the other way. Two independent review bots on PR #5433 flagged the
  issue's literal order as a security-bypass risk: Devin (security-severity
  finding) and CodeRabbit both identified that ranking an explicit user
  request above mandatory policy would let an adversarial or mistaken
  request outrank a safety or repository-policy blocker. The shipped skill
  deviates from the issue's literal order to close that gap; the deviation
  is marked inline in the skill file itself (`<!-- Deviates from issue
  #5404's literal precedence text: mandatory policy must outrank a raw user
  request per security review (PR #5433 threads). -->`). This ADR is the
  governance record of that deviation: a reader who compares the shipped
  precedence order against issue #5404 verbatim will find a mismatch, and
  this paragraph, together with the inline comment, is the citation for why.
- **No behavioral proof yet.** No live evaluation confirms the doctrine
  changes agent output. FAILURE-MODES.md #12's own Enforcement Pattern table
  lists the runtime-parity behavioral proof as "Planned (not yet
  implemented; blocked on live model access, tracked in the PR's
  Incremental Scope Declaration)." This ADR covers doctrine only.
- **A fourth normative surface to keep in sync.** FAILURE-MODES.md #12 must
  track any future edit to builder-ethos.md section 4, voice.md's
  Completion-Tail Audit, or the skill's Task Completion Contract. A future
  edit to any of the three that is not mirrored into the catalog entry's
  Enforcement Pattern table silently desynchronizes the documented pattern
  from the rule it describes.

### Neutral

- Generated instruction mirrors (`.github/instructions/builder-ethos.instructions.md`,
  `.github/instructions/voice.instructions.md`,
  `src/copilot-cli/skills/avoiding-manufactured-work/SKILL.md`) were
  regenerated in this PR to keep shipped projections aligned with the
  canonical rule and skill files. They remain mirrors, not owners.
- This PR also updates the 12 critic/qa reviewer surfaces and the clean-
  review eval registration so a zero-finding APPROVED or PASS verdict can be
  terminal when inspected evidence is clean. Those surfaces consume the
  doctrine; canonical ownership stays with the four files above.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|---|---|---|---|
| `.claude/rules/builder-ethos.md` | Direct | Adds section 4 (Completion Is a Terminal State); already shipped in this PR | Low |
| `.claude/rules/voice.md` | Direct | Adds Completion-Tail Audit section and a Quick Self-Review line; already shipped in this PR | Low |
| `.claude/skills/avoiding-manufactured-work/SKILL.md` | Direct | Adds Task Completion Contract (formation, precedence, disposition, terminal predicate, reactivation, handoff boundary); already shipped in this PR | Low |
| `.agents/governance/FAILURE-MODES.md` | Direct | Adds catalog entry 12 and updates the Index to twelve patterns; already shipped in this PR | Low |
| 12 critic/qa reviewer surfaces (for example, `.claude/agents/critic.md`, `.claude/agents/qa.md`, and their mirrors) | Indirect | Updated in this PR so a zero-finding APPROVED or PASS verdict is valid when the review cites inspected evidence; no ownership change | Low |
| `tests/evals/critic-scenarios.json`, `tests/evals/test_critic_finding_quota.py` | Indirect | Register and guard the zero-finding clean-review case that issue #5404 requires | Low |
| Generated instruction mirrors (`.github/instructions/builder-ethos.instructions.md`, `.github/instructions/voice.instructions.md`, `src/copilot-cli/skills/avoiding-manufactured-work/SKILL.md`) | Indirect | Regenerated in this PR to keep shipped projections aligned with the canonical rule and skill files | Low |
| Issue #5417 (persisted completion across compaction and handoff) | Indirect | Consumes this ADR's terminal predicate and reactivation rules as its starting contract; implementation is out of scope here | Medium |
| Runtime-parity behavioral-proof suite (14 scenarios) | Indirect | Will need to grade agent output against this ADR's terminal predicate and Completion-Tail Audit once live model access exists | Medium |

## Related Decisions

- Issue #5404 is the origin of the terminal-state invariant and the
  completion-tail audit; this ADR is its governance record.
- Issue #5417 (persisted completion across compaction and handoff/restart)
  is explicitly out of scope here. `avoiding-manufactured-work/SKILL.md`'s
  Handoff Boundary paragraph names the split directly: "Durable transport
  and restoration across compaction, process restart, and handoff are owned
  by issue #5417, not this skill."
- PR #5433 carries an Incremental Scope Declaration formally deferring the
  runtime-parity behavioral-proof half of issue #5404 (the 14-scenario
  suite), because it requires live model access this session does not have.
  A separate, future ADR or PR should cover that suite once live model
  access is available. This ADR covers doctrine only, not behavioral proof.
- ADR-099 (`ADR-099-remove-commit-limit-bypass-gate.md`) is cited only for
  the in-session repository-owner-authorization pattern used in the Decision
  section above; it is not otherwise a related architectural decision.

## Consensus

Six-role `adr-review` panel run completed 2026-08-31 against this ADR,
issue #5404, PR #5433 review comments, and the live doctrine text in
`.claude/rules/builder-ethos.md`, `.claude/rules/voice.md`,
`.claude/skills/avoiding-manufactured-work/SKILL.md`, and
`.agents/governance/FAILURE-MODES.md` #12. Round 1 found two P1 record
defects, both resolved in this change: (1) this section still claimed the
panel had not run and treated a scoped specialist-only substitute as
sufficient, which `.claude/rules/governance.md` and the `adr-review`
contract do not allow; (2) the Neutral and Impact sections still
described the critic/qa consumer updates and mirror sync as future work,
while PR #5433 already ships them. Round 2 converged 6 Accept, 0
Disagree-and-Commit, 0 Block. Debate log: `.agents/critique/ADR-105-debate-log.md`.

## References

- Issue #5404 (terminal-state invariant and completion-tail audit origin)
- PR #5433 (this ADR ships with this PR; Incremental Scope Declaration
  referenced above)
- `.agents/governance/FAILURE-MODES.md` #12, "Post-Completion Continuation /
  Response Reopening"
- `.agents/architecture/ADR-099-remove-commit-limit-bypass-gate.md`, cited
  for the owner-authorization-in-session pattern only
