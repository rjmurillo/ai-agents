---
id: ADR-066
status: accepted
date: 2026-07-19
decision-makers: [architect]
supersedes: []
superseded-by: null
explainer: null
implemented: true
consulted:
- analyst
- critic
- independent-thinker
- security
- high-level-advisor
informed:
- implementer
- qa
- devops
---

# ADR-066: Hook Fail-Open Reconciliation (Prevention-First, Fail-Closed-and-Loud)

## Status

Accepted (repo-owner @rjmurillo, 2026-07-19). adr-review consensus 6/6 ACCEPT_WITH_CHANGES (architect, critic, independent-thinker, security, analyst, high-level-advisor); the six bounded edits from that review are applied below. Refs #2205, #2230, #2263, #2271.

**Division of authority.** [ADR-071](./ADR-071-plugin-hook-runtime-contract-verification.md) (Accepted 2026-06-02) is the binding rule that hooks MUST fail closed and loud (its Decision item 5). This ADR is the detailed reconciliation of prior guidance (ADR-008, ADR-033, ADR-035, ADR-062) to that rule: the D1 and D2 failure-mode detail, the exit-code table, and the #2205 incident rationale. Where a prior ADR still states fail-open, this ADR governs until the #2271 sweep amends it (precedence clause in D5).

## Context and Problem Statement

PR #2263 scrubbed launcher-level fail-open from the surfaces it owned and replaced it with a prevention-first, fail-closed-and-loud position. It deliberately did not touch the pre-existing, repo-wide "hook runtime errors are fail-open" convention because that policy reversal needed its own ADR. Issue #2271 tracks that audit.

The status quo has the default backwards. ADR-008, ADR-033, and ADR-035 codify "exit 1 = hook error = fail-open" as the standard. ADR-062 calls fail-open "the repo's universal fail-open convention" and treats fail-closed behavior as a deadlock. Stability guidance about graceful degradation has also been cited outside its intended scope to justify hook launchers that silently return success.

The #2205 incident demonstrated the cost. A launcher path bug wedged customer environments for 33 days across v0.3.0 to v0.5.6 because the in-script fail-open shim never ran. The launcher itself failed before the script started. The fail-open default did not protect the customer; it delayed detection.

The repo owner's canonical position is now explicit:

1. Do not add launcher-level fail-open paths for hooks.
2. Do not use silent exit 0 as a recovery path for hook errors.
3. Do not cite graceful degradation as a warrant for hooks whose job is to assert an invariant.
4. Prevent bad hook artifacts before release through generation-time anchoring, `scripts/validation/validate_hook_anchoring.py`, pre-push enforcement, CI enforcement, and runtime-contract tests.
5. If a novel runtime escape reaches a released hook, fail closed and loud with a non-zero exit and actionable stderr.

This ADR reconciles prior ADRs and guidance to that position. The ADR number remains ADR-066.

## Decision Drivers

1. Customer-harm bound. A silent exit 0 disables the hook and looks like success. The #2205 incident showed this is the dominant failure mode.
2. Detectability. A loud failure gets fixed. A silent fail-open accumulates dead hooks no one knows are dead.
3. Prevention at the correct layer. Hook launchers are the wrong layer for recovery. Generated hook artifacts must be anchored, validated, and tested before release.
4. Auditability. Validators and runtime-contract tests make hook anchoring drift visible in pre-push and CI.
5. Operational truth. A hook that cannot prove its invariant did not succeed. Returning success misleads the operator.

## Considered Options

1. **Status quo**: keep "hook runtime errors are fail-open" as the universal default.
2. **Launcher-level recovery**: keep hook launchers permissive, with warnings or degraded behavior on runtime failures.
3. **Prevention-first, fail-closed-and-loud** (chosen): block bad hook artifacts before release and make any novel runtime escape fail non-zero with actionable stderr.

## Decision Outcome

Chosen option: **3 - prevention-first, fail-closed-and-loud**, because the #2205 incident proved that launcher-level fail-open does not protect users. It hides broken hooks until customers pay the cost. The correct layer is prevention before release, backed by validators and runtime-contract tests. Runtime escapes then fail loud so maintainers fix the broken hook instead of shipping a false success.

### Concretely this means

#### D1. Hook failure-mode policy

The default for hooks is:

- **Prevent the bad artifact at generation time.** Generated hook launchers MUST anchor to the repository root through the canonical generation path.
- **Validate anchoring before release.** `scripts/validation/validate_hook_anchoring.py` MUST run in pre-push and CI for hook artifacts.
- **Test the runtime contract.** A runtime-contract test MUST prove that generated hooks resolve their anchored targets correctly and do not depend on caller working directory accidents.
- **Fail closed and loud on novel escapes.** If a runtime error still escapes, the hook exits non-zero and emits stderr that names the hook, the failed invariant, and the recovery path.
- **No silent success on hook failure.** `try/except: pass`, `|| true`, unconditional `exit 0`, or success-shaped fallback behavior in hook failure paths violates this ADR.

This replaces the prior ADR-008 statement that runtime and I/O errors during hook execution are fail-open.

#### D2. Exit-code reconciliation

The canonical exit-code table for hooks is:

| Exit Code | Meaning for hooks | Required behavior |
|-----------|-------------------|-------------------|
| 0 | Hook ran and asserted no violation | Allow action |
| 1 | Hook logic or runtime error | Emit actionable stderr. NOTE: on a Claude blocking event exit 1 does NOT block (the tool proceeds); a gate that must fail closed uses exit 2 (see notes) |
| 2 | Configuration, bootstrap, or policy-gate block | Fail closed and emit actionable stderr |
| 3 | External dependency unavailable | Fail closed and emit actionable stderr |
| 4 | Authentication or authorization failure | Fail closed and emit actionable stderr |

Notes:

- Exit 3 separates external dependency failures from logic errors. It does not create a fail-open lane.
- Blocking hooks, including PreToolUse policy gates, continue to use non-zero exits to block unsafe actions.
- Non-blocking lifecycle hook hosts that ignore non-zero exits do not change the policy. The repository still treats the hook as failed. Pre-push and CI MUST catch bad artifacts before release, and runtime-contract tests MUST prove the generated hook path is valid.
- Which exit code BLOCKS is host-specific, so "fail closed" is not a single number. On a Claude blocking event (PreToolUse and the other blocking events) only exit 2, or a nested `hookSpecificOutput.permissionDecision:"deny"` at exit 0, blocks; exit 1 lets the tool proceed (see the ADR-035 Claude hook section). On Copilot preToolUse any non-zero exit denies. A gate that must fail closed on a blocking event therefore MUST use exit 2, never exit 1: an exit-1 "fail closed" on a Claude PreToolUse gate is the #2205 silent-disable in a new place.

#### D3. ADR-062 reconciliation (completed)

This is done, and went further than the original draft directed. The ADR-062 amendment (issue #3214, Accepted 2026-07-18) RETIRED the LSP-first runtime enforcement hooks entirely (the five guards), and #3232 deleted them from the vendored surface, keeping only the static steering in `.claude/rules/lsp-first.md`. So the "LSP recovery mechanism" the June draft directed to reframe as a bounded escape no longer exists; there is nothing left to fail-open or fail-closed at that layer. The surviving static steering is a class-3 advisory (see D4) and enforces nothing at runtime. ADR-084 (the vendored-hook ROI bar) records why: the family added one true positive in 6.5 weeks against a running tally of false blocks. No further ADR-062 action is required by #2271.

#### D4. Graceful-degradation guidance reconciliation

Graceful-degradation guidance applies to user-facing integration points where a reduced response is meaningful to the caller. It does not apply to governance hooks, lifecycle hooks, or code whose job is to assert an invariant.

Hook authors MUST NOT cite graceful degradation as a reason to return success after a hook launcher, bootstrap path, runtime import, or invariant check failed.

**Three hook classes, three failure modes.** Fail-closed-and-loud is the default for hooks that ASSERT AN INVARIANT. It is not universal. Classify a hook before choosing its failure mode:

1. **Invariant / policy gate** (blocks a specific unsafe action: a secret commit, a protected-branch push, a completion claim with no test evidence). Fail closed and loud. On a blocking event use exit 2. A silent success disables the gate (#2205).
2. **Integration point** (a user-facing call where a reduced response is meaningful to the caller). Graceful degradation is allowed, scoped to the caller per the guidance above.
3. **Advisory / steering / precondition hook** (injects context, nudges a preference, or checks a soft precondition, and does NOT block a specific unsafe action). Fail OPEN. A false block from an advisory hook wedges the agent loop with no safety benefit. This is the #3247 and #3232 class: the LSP runtime-enforcement family was retired (ADR-062 amendment #3214) because a false block on a core tool cost more than its one true positive in 6.5 weeks (ADR-084 ROI bar). An advisory hook that hits its own error MUST surface a loud stderr note and MUST NOT deny. Where a class-3 concern genuinely needs enforcement, move it to generation-time, pre-push, and CI, where a block cannot wedge a live loop.

The failure mode follows the hook's job, not a blanket runtime default: fail closed for class 1, degrade for class 2, fail open for class 3. This resolves the apparent conflict between D1 (no silent success) and the do-not-wedge-the-loop lesson: both hold, on different hook classes.

#### D5. Implementation plan for issue #2271

The implementer follow-up PR for #2271 MUST update prior governance surfaces to match this ADR:

| Surface | Required action | Status |
|---------|-----------------|--------|
| ADR-008 | Replace fail-open runtime hook prose with D1 and D2 policy. | DONE (amended 2026-06-11) |
| ADR-033 | Remove recommendations that downgrade blocking hook failures to advisory success. | Pending #2271 |
| ADR-035 | Align the hook exit-code section to D2 and the D4 three-class model (fail-closed for invariant gates, fail-open for class-3 advisory), not a blanket "remove fail-open." | In progress (this change) |
| ADR-062 LSP-first ADR | Reframe LSP handling per D3. | DONE (amendment #3214; runtime layer retired, deleted in #3232) |
| ADR-070 memory-first gate ADR | Reframe fallback language as prevention and loud failure, not success-shaped degradation. | Pending #2271 |
| Release It guidance | Scope graceful degradation away from hook invariants per D4. | Pending #2271 |
| Memory cross-reference hooks | Remove launcher-level fail-open behavior and add fail-closed runtime-contract coverage. Classify the `push_guard_base.py` telemetry fail-open and the `guards.py` consumer-repo skip as legitimate class-3 exit-0 per D4 and D6, not banned fail-open. | Pending #2271 |

The follow-up PR closes #2271. This ADR does not close #2271 by itself.

#### D6. Lintable and testable prevention contract

This ADR mandates a prevention contract:

1. `scripts/validation/validate_hook_anchoring.py` is the canonical validator for generated hook anchoring.
2. The validator runs in pre-push and CI.
3. Runtime-contract tests assert that generated hooks resolve their anchored target paths and fail non-zero with actionable stderr when the invariant cannot be proven.
4. A repo-wide governance test rejects success-shaped suppression in hook failure paths. It scans by AST, scoped to failure branches (except handlers and post-invariant-check branches), for:
   - bare `try/except: pass` in a failure path,
   - `|| true` after a hook invocation,
   - `exit 0` or `return 0` in a failure branch of a class-1 invariant gate (D4),
   - a `permissionDecision: "allow"` or top-level `decision: "allow"` printed to stdout from an except handler. The exit code alone does not catch this: a hook can exit non-zero yet have already emitted an allow decision, which the host honors. The scan MUST inspect stdout decisions emitted from error paths, not exit codes alone,
   - comments that endorse hook fail-open or graceful degradation for invariant enforcement.
5. Legitimate class-3 exit-0 (D4) is distinguished from banned fail-open by a REQUIRED structured marker, not by inference. A class-3 advisory hook, a consumer-repo skip (`guards.py` `skip_if_consumer_repo`), or a bounded telemetry fail-open (`push_guard_base.py` and the roughly ten guards behind it) that legitimately exits 0 on its own path MUST carry a machine-readable marker (for example `# fail-open: class-3 advisory, ADR-066 D4`) and appear on the governance-test allowlist. The scan treats an unmarked, unlisted exit-0-in-failure-path as banned. This keeps the legitimate guards from tripping the lint while still catching a new silent fail-open.
6. Any exception beyond the item-5 marked-and-allowlisted class-3 case requires a later ADR. Inline comments alone are not enough.

#### D7. Scope exclusion

Third-party vendored code is outside this ADR unless it is wrapped by a first-party hook launcher. First-party wrappers remain governed by ADR-066.

#### D8. Precedence and break-glass

**Precedence.** Until the #2271 sweep lands, this ADR governs the failure-mode question wherever a prior ADR still states fail-open. A reader who finds "fail-open" prose in ADR-033, ADR-070, or the Release It guidance follows D1, D2, and D4 here instead; the stale prose is known #2271 debt, not a live contradiction. This closes the contradiction window at zero ADR-edit cost, and the sweep then removes the stale prose. ADR-071 (Accepted) remains the binding rule above this reconciliation.

**Break-glass.** Fail-closed-and-loud must never leave an operator with only the banned escape (`git commit --no-verify`, which this repo forbids). Every fail-closed gate that can block a developer MUST honor an explicit, named, logged environment valve of the form `SKIP_<GATE>_GATE` (the existing pattern, for example `SKIP_LSP_GATE`). The valve is a documented, auditable escape for a false positive or a novel wedge, visible in the environment, unlike `--no-verify`. It is not a silent fail-open path. A fail-closed gate that can wedge a live loop and offers no such valve is non-conformant and MUST gain one.

### Consequences

Good:

- Customer-harm bound: the #2205 failure mode (silent launcher success while the hook is broken) is prevented before release.
- Detectability: novel runtime escapes are visible immediately through non-zero exit and stderr.
- Auditability: hook anchoring and failure semantics are tested in pre-push and CI.
- Policy coherence: ADR-008, ADR-033, ADR-035, ADR-062, and stability guidance converge on one hook policy.

Bad:

- Follow-up work is required across prior ADRs, guidance, and hook tests.
- Hooks that were silently degraded will start failing loud. This is intentional, but it changes operator experience.
- Emergency bypasses, if needed, must be explicit, named, logged, and documented in a later ADR or rollout plan. They are not silent fail-open paths.

### Confirmation

Implementation compliance is confirmed by:

1. `scripts/validation/validate_hook_anchoring.py` running green in pre-push and CI.
2. Runtime-contract tests proving generated hooks anchor correctly and fail non-zero on broken invariants.
3. A repo-wide governance test rejecting hook fail-open endorsements and success-shaped suppression.
4. adr-review consensus on this ADR (D&C or Accept from all 6 agents, max 10 rounds).
5. The implementer flip PR closing #2271 and referencing this ADR in its body.

## Pros and Cons of the Options

### Option 1: Status quo

- Good, because no code or prose changes are required.
- Bad, because the #2205 failure mode remains possible.
- Bad, because hook authors can keep treating success-shaped suppression as normal.
- Bad, because the maintainer's standing position from #2263 is already the inverse of this option.

### Option 2: Launcher-level recovery

- Good, because it tries to reduce immediate operator interruption.
- Bad, because it preserves the wrong layer for recovery.
- Bad, because launcher failures can occur before in-script recovery runs.
- Bad, because warnings and degraded paths still let broken hooks reach users.

### Option 3 (chosen): Prevention-first, fail-closed-and-loud

- Good, because bad hook artifacts are blocked before release.
- Good, because runtime escapes are visible and actionable.
- Good, because validators and runtime-contract tests become the enforcement point.
- Good, because no fail-open path is endorsed for hooks.
- Bad, because follow-up governance and test updates are required.

## More Information

- Refs #2205 (customer wedge incident; failure-mode evidence)
- Refs #2230 (launcher fail-open remediation; closed addressed-by-prevention)
- Refs #2263 (governance scrub; established prevention-first, fail-closed-and-loud stance)
- Refs #2271 (audit; closed by the implementer flip PR, not by this ADR)
- Analyst inventory: <https://github.com/rjmurillo/ai-agents/issues/2271#issuecomment-4604311175>
- Serena memory `feedback-generated-artifact-runtime-verification.md` is the contemporaneous incident record.

Realization plan: this ADR lands. adr-review runs. On consensus, status flips to "accepted." The implementer opens the flip PR per D5, closes #2271, and adds the D6 tests. ADR-008, ADR-033, ADR-035, ADR-062, release guidance, and memory cross-reference hooks get amended in that same PR or in tightly scoped follow-ups, each referencing this ADR. After the flip, review this ADR at the next governance audit or when a new hook exit-code lane is proposed.
