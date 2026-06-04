---
status: "proposed"
date: 2026-06-02
decision-makers: [architect]
consulted: [analyst, critic, independent-thinker, security, high-level-advisor]
informed: [implementer, qa, devops]
---

# ADR-066: Hook Fail-Open Reconciliation (Prevention-First, Fail-Closed-and-Loud)

## Status

Proposed. Requires adr-review per `AGENTS.md` ("Any `ADR-*.md` ... create/edit fires adr-review"). Refs #2205, #2230, #2263, #2271.

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
| 1 | Hook logic or runtime error | Fail closed and emit actionable stderr |
| 2 | Configuration, bootstrap, or policy-gate block | Fail closed and emit actionable stderr |
| 3 | External dependency unavailable | Fail closed and emit actionable stderr |
| 4 | Authentication or authorization failure | Fail closed and emit actionable stderr |

Notes:

- Exit 3 separates external dependency failures from logic errors. It does not create a fail-open lane.
- Blocking hooks, including PreToolUse policy gates, continue to use non-zero exits to block unsafe actions.
- Non-blocking lifecycle hook hosts that ignore non-zero exits do not change the policy. The repository still treats the hook as failed. Pre-push and CI MUST catch bad artifacts before release, and runtime-contract tests MUST prove the generated hook path is valid.

#### D3. ADR-062 reconciliation

ADR-062's "universal fail-open convention" framing is wrong after this ADR. ADR-062 MUST be amended to:

- Replace "the repo's universal fail-open convention" with "ADR-066's prevention-first hook policy."
- Remove the claim that fail-closed behavior is generally a deadlock.
- Keep any LSP recovery mechanism framed as a bounded, tested operational escape, not as launcher-level fail-open.
- Add tests that prove the LSP hook path either enforces the invariant or fails loud.

#### D4. Graceful-degradation guidance reconciliation

Graceful-degradation guidance applies to user-facing integration points where a reduced response is meaningful to the caller. It does not apply to governance hooks, lifecycle hooks, or code whose job is to assert an invariant.

Hook authors MUST NOT cite graceful degradation as a reason to return success after a hook launcher, bootstrap path, runtime import, or invariant check failed.

#### D5. Implementation plan for issue #2271

The implementer follow-up PR for #2271 MUST update prior governance surfaces to match this ADR:

| Surface | Required action |
|---------|-----------------|
| ADR-008 | Replace fail-open runtime hook prose with D1 and D2 policy. |
| ADR-033 | Remove recommendations that downgrade blocking hook failures to advisory success. |
| ADR-035 | Update hook exit-code guidance to D2 and remove fail-open semantics. |
| ADR-062 LSP-first ADR | Reframe LSP handling per D3. |
| ADR-070 memory-first gate ADR | Reframe fallback language as prevention and loud failure, not success-shaped degradation. |
| Release It guidance | Scope graceful degradation away from hook invariants per D4. |
| Memory cross-reference hooks | Remove launcher-level fail-open behavior and add fail-closed runtime-contract coverage. |

The follow-up PR closes #2271. This ADR does not close #2271 by itself.

#### D6. Lintable and testable prevention contract

This ADR mandates a prevention contract:

1. `scripts/validation/validate_hook_anchoring.py` is the canonical validator for generated hook anchoring.
2. The validator runs in pre-push and CI.
3. Runtime-contract tests assert that generated hooks resolve their anchored target paths and fail non-zero with actionable stderr when the invariant cannot be proven.
4. A repo-wide governance test rejects hook failure paths that contain success-shaped suppression, including:
   - bare `try/except: pass` in a failure path,
   - `|| true` after a hook invocation,
   - `exit 0` in a failure branch,
   - `return 0` or `sys.exit(0)` annotated as fail-open,
   - comments that endorse hook fail-open or graceful degradation for invariant enforcement.
5. Any exception to this policy requires a later ADR. Inline comments alone are not enough.

#### D7. Scope exclusion

Third-party vendored code is outside this ADR unless it is wrapped by a first-party hook launcher. First-party wrappers remain governed by ADR-066.

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
