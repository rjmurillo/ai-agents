# ADR Debate Log: Consolidated Per-Event Hook Dispatcher

## Summary

- **ADR**:
  `.agents/architecture/ADR-068-consolidated-hook-dispatcher.md`
- **Review date**: 2026-07-19
- **Review cycles**: Initial acceptance, contract hardening, observer output,
  security policy
- **Outcome**: Consensus
- **Final status**: accepted
- **Latest tally**: 6 Accept, 0 Disagree-and-Commit, 0 Block
- **Security assessment**: Accept, active approval policy removed

This review reconciled the shipped implementation with its decision record.
It did not change the dispatcher decision.

## Round 1

### Roles and Vote Record

All six mandatory roles participated: architect, critic,
independent-thinker, security, analyst, and high-level-advisor. The supplied
Round 1 record retained the blocking findings and correction categories, but
not the individual Round 1 vote labels. This log records each missing label as
not retained rather than reconstructing a vote.

| Agent | Round 1 vote |
|-------|--------------|
| architect | Not retained in the supplied review record |
| critic | Not retained in the supplied review record |
| independent-thinker | Not retained in the supplied review record |
| security | Not retained in the supplied review record |
| analyst | Not retained in the supplied review record |
| high-level-advisor | Not retained in the supplied review record |

### Blocking Findings

Round 1 did not converge. Its P0/P1 correction categories were:

1. **Phantom timeout budget and watchdog prior art.** The prior text implied an
   in-process budget and reusable watchdog that do not exist.
2. **Mode and matcher drift.** The decision record did not accurately describe
   the shipped gate, observe, and advise modes or the safe host matcher-union
   fallback.
3. **Evidence provenance.** Current Copilot CLI claims needed version-scoped
   empirical evidence, separate from historical incident evidence.
4. **ADR-074 prior art.** ADR-074 incorrectly treated ADR-068 as a source for
   `SIGALRM`, watchdog, and `budget_exceeded` behavior.

### Corrections Before Round 2

- ADR-068 Decision items 2 through 4 now describe the host matcher union, the
  three execution modes, and the absence of an in-process watchdog.
- `.claude/lib/hook_dispatch.py` and
  `build/scripts/generate_dispatcher.py` are the canonical runtime and
  artifact-generation evidence.
- `tests/build_scripts/test_generate_dispatcher.py`,
  `tests/build_scripts/test_generate_hooks.py`, and
  `tests/build_scripts/test_dispatcher_matcher_union.py` cover the corrected
  mode, cleanup, and matcher contracts.
- ADR-071's 2026-07-19 amendment cites
  `.claude/skills/agent-harness-reference/references/probe-evidence.md`,
  section 4, as a curated probe summary.
- ADR-074 now states that ADR-068 cannot be reused as watchdog prior art.

All Round 1 P0/P1 categories were resolved before the final vote.

## Round 2

### Agent Positions

| Agent | Vote | Recorded disposition |
|-------|------|----------------------|
| high-level-advisor | Accept | No blocking issue remained. |
| security | Accept | PASS_WITH_NOTES. Host-timeout fail-open remains an explicit residual. |
| independent-thinker | Accept | No blocking issue remained. |
| architect | Disagree-and-Commit | Accepted the corrected decision record with nonblocking reservations. |
| analyst | Disagree-and-Commit | Accepted the corrected decision record with nonblocking reservations. |
| critic | Disagree-and-Commit | Required durable acceptance evidence and preservation of the remaining P2 notes. |

### Resolved P0/P1 Findings

- The decision no longer claims a dispatcher-controlled timeout budget,
  `SIGALRM`, watchdog thread, or structured `budget_exceeded` result.
- The mode and matcher descriptions now agree with the canonical runtime,
  generator, and focused tests cited above.
- Historical Copilot CLI 1.0.57 evidence and current 1.0.72-1 probe evidence
  are version-scoped.
- ADR-074 no longer relies on nonexistent ADR-068 watchdog behavior.
- This debate log closes the acceptance-evidence gap and supports the ADR-073
  lifecycle transition to `status: accepted`.

### Accepted Residuals

- Copilot CLI 1.0.72-1 host timeouts fail open. A hung dispatcher can be
  killed before later guards run, allowing the tool. ADR-071 records this
  measured residual.
- The runtime's exactly-one PermissionRequest producer guard lacks a direct
  unit test, although generator-level rejection coverage exists. This remains
  a nonblocking P2 test note.
- ADR-068 retains an informal prior-art section rather than the newer ADR
  template's headed prior-art subsections. The reviewed decision content was
  not rewritten solely for template shape.

### Dissent

Architect, analyst, and critic voted Disagree-and-Commit. The critic's
persisted concern was acceptance-evidence completeness plus the P2 runtime-test
and template-shape notes above. No separate Round 2 rationale was retained for
architect or analyst, so this log does not attribute one.

## Final Consensus

Consensus was achieved under the adr-review protocol: all six roles voted
Accept or Disagree-and-Commit, with 3 Accept, 3 Disagree-and-Commit, and
0 Block. ADR-068 is accepted and `implemented: true`.

## 2026-07-19 Contract Hardening Review

The same six roles reviewed the later Copilot CLI contract corrections after a
Phase 1 evidence pass and one correction round.

### Phase 1 findings corrected

- Configured Stop and future SubagentStop targets remain direct. Native
  `agentStop` and `subagentStop` names are defensive exclusions.
- The current source tree has two Stop registrations and zero SubagentStop
  registrations.
- PreCompact generation rests on the official contract. Its 1.0.72-1 trigger
  probe was inconclusive.
- PermissionRequest `ask` emits no Copilot output and invokes normal host
  handling. The observed noninteractive denial is mode-dependent.
- The current PreToolUse manifest has 18 shims and requests 615 seconds. Only a
  2-second host timeout was probed. A first-shim hang can bypass up to 17 later
  registered shims.
- Observe mode passes stdout through. A future structured-output producer needs
  an event-specific merger or a direct registration.
- Dispatcher rollback remains conditional on replacing or dropping the
  PermissionRequest translation.

### Convergence votes

| Agent | Vote | Remaining position |
|-------|------|--------------------|
| architect | Accept | SessionEnd has no current source registration; its observe mode is only a supported future path. |
| critic | Accept | No P0 or P1 issue remained. |
| independent-thinker | Accept | All evidence links and contract qualifications resolved. |
| security | Accept | Host-timeout fail-open remains an accepted, quantified residual. |
| analyst | Accept | Every Phase 1 claim resolved against code or labeled evidence. |
| high-level-advisor | Accept | Manifest ordering remains an operational P2 awareness item. |

Final tally: **6 Accept, 0 Disagree-and-Commit, 0 Block**. Consensus reached.

### Accepted residuals

- The generator preserves source registration order. It does not prioritize
  security guards. A slow early shim can increase the timeout bypass exposure.
- The host may grant, cap, or ignore the requested 615-second aggregate. Current
  evidence does not distinguish those cases.
- Windows PowerShell runtime coverage remains tracked by issue #2231.
- Shared in-process interpreter state remains part of the accepted dispatcher
  design.

## 2026-07-19 Observer Output Amendment Review

The six roles reviewed the event-specific observer output policy after an audit
found that consolidated SessionStart and PostToolUse plaintext could not remain
as raw stdout. PreCompact and UserPromptSubmit also lacked a documented
config-file output field.

### Round 1 votes

| Agent | Vote | Main position |
|-------|------|---------------|
| architect | Accept | Implementation and official output fields aligned; debate-log update required. |
| critic | Disagree-and-Commit | Failed output, flat merge, and output size needed explicit treatment. |
| independent-thinker | Disagree-and-Commit | `modifiedResult`, stderr silence, and alternatives needed tighter boundaries. |
| security | Accept | No blocker; output size, context injection, and stderr behavior remained P2 residuals. |
| analyst | Accept | Code, tests, and pinned sources supported the decision; impact table omitted two owners. |
| high-level-advisor | Accept | This was the smallest correction that avoided inventing a host field. |

Round 1 tally: **4 Accept, 2 Disagree-and-Commit, 0 Block**.

### Corrections before convergence

- Only successful observers contribute context. Partial stdout from a nonzero
  or crashed observer is discarded.
- SessionStart and PostToolUse merge plaintext in registration order into one
  `additionalContext` string. One blank line separates flat contributions, and
  per-shim attribution is not preserved.
- Current PostToolUse producers are named and classified as plaintext.
  `modifiedResult` and pre-structured JSON require a field-specific merger or
  direct registration.
- Notification and SubagentStart output policies now have explicit unit tests.
- Direct registration and silent discard for PreCompact and UserPromptSubmit
  are recorded as rejected alternatives.
- Missing output ceiling, prompt-injection reach, and stderr model-context
  silence are recorded as accepted residuals.
- The impact table now names the in-process unit tests and official-source
  sidecar.

### Convergence votes

| Agent | Vote | Remaining position |
|-------|------|--------------------|
| architect | Accept | No P0 or P1 remained; flat merge and stderr silence are explicit residuals. |
| critic | Accept | All first-round P1 findings were resolved or accepted in the ADR. |
| independent-thinker | Accept | Every disputed assumption gained evidence, a boundary, or a revisit trigger. |
| security | Accept | Failed-output injection was removed; three low-risk residuals remain accepted. |
| analyst | Accept | All load-bearing claims trace through code, tests, and pinned sources. |
| high-level-advisor | Accept | The correction is bounded, reversible, and ready to ship. |

Final tally: **6 Accept, 0 Disagree-and-Commit, 0 Block**. Consensus
reached.

### Accepted residuals

- Observer stdout has no repository-enforced size ceiling. Registered shims are
  generated artifacts, but a defective shim can create an oversized response.
- `additionalContext` is intentionally a model-context channel. A compromised
  registered observer can inject instructions after repository compromise.
- Whether exit-0 stderr reaches model context remains docs silent.
- The blank-line merge is flat and loses per-shim attribution.

## 2026-07-20 Security Policy Amendment Review

The six roles reviewed removal of test-runner auto-approval from Claude Code
and Copilot CLI. The amendment retains the generic PermissionRequest adapter
without an active producer. It does not replace the removed policy with
`permissions.allow`.

### Round 1 votes

| Agent | Vote | Main position |
|-------|------|---------------|
| architect | Disagree-and-Commit | Removal and adapter retention were sound; evidence, alternatives, and issue disposition were missing. |
| critic | Block | The ADR understated issue #3217 divergence, implied an unenforced future gate, and omitted user friction. |
| independent-thinker | Block | Requested a separate security record, adapter deletion, host-native replacement analysis, and a mechanical gate. |
| security | Disagree-and-Commit | Removal reduced attack surface; issue divergence, protected assets, residuals, and audit evidence were missing. |
| analyst | Provisional Block | Implementation was correct; traceability, stale Claude wording, and two absence regressions were incomplete. |
| high-level-advisor | Block by disposition | No literal vote token was supplied, but the reviewer required P0 corrections before Phase 1 could close. |

Round 1 tally: **0 Accept, 2 Disagree-and-Commit, 4 Block**.

### Phase 2 ruling and corrections

- The amendment remains inside ADR-068 because this record already owns advise
  mode and PermissionRequest translation.
- The dormant adapter remains. It is tested, has no registration, and adds no
  runtime attack surface while inactive.
- Human ADR and PR review is named as the current compensating control. The ADR
  states that no mechanical CI gate proves that review occurred.
- Safety-audit findings 19 and 48 and the CRITICAL_FAIL review record now anchor
  the removal rationale.
- Tighter command matching and test-runner `permissions.allow` rules are
  rejected because both keep the same command-name trust flaw.
- ADR-085 initially ratified D-B as keep-as-hook. The owner later superseded
  that ruling after Finding 3 and selected deletion. ADR-068 and ADR-085 now
  align; issue #3217 remains the implementation owner for D-A.
- Normal host permission prompts are accepted friction.
- The committed-artifact regression proves the producer, both PermissionRequest
  directories, generated registration, and test-runner allow rules remain
  absent.
- The exact focused command and result are recorded in ADR-068: 370 passed,
  1 skipped.

### Convergence votes

| Agent | Vote | Remaining position |
|-------|------|--------------------|
| architect | Accept | All Phase 2 settlements are present and test-backed. |
| critic | Accept | No P0 or P1 issue remains. |
| independent-thinker | Accept | Scope, adapter retention, issue divergence, and prompts are explicit. |
| security | Accept | The active trust-boundary defect is removed with no replacement policy. |
| analyst | Accept | Evidence, arithmetic, registrations, and absence regressions align. |
| high-level-advisor | Accept | The decision is bounded, honest about controls, and ready to ship. |

Final tally: **6 Accept, 0 Disagree-and-Commit, 0 Block**. Consensus
reached.

### Accepted residuals

- No mechanical CI gate proves that a future PermissionRequest producer
  received security review. Human ADR and PR review remains the stated control.
- At this review point, issue #3217 still owned the D-A terminal state. PR #3293
  later selected Retirement. It no longer authorizes test-runner auto-approval
  after the ADR-085 D-B amendment.
- The allow-rule marker list is finite. It catches the removed policy and common
  runner names, while human review enforces the broader rule that runner names
  are not a safety boundary.
- The dormant adapter may require a fresh host-contract probe before future use.

## 2026-07-20 Mainline Reconciliation Review

The six roles reviewed ADR-068 after integration with main as of 2026-07-20 and
the superseding ADR-085 security amendment.

### Corrections

- Metrics at that review point stated 30 source registrations, 16 PreToolUse shims, a
  555-second summed timeout request, 76.7 percent host-entry reduction, and up to
  15 later shims bypassed by a first-shim hang.
- The ADR names the accountable human decision-maker.
- Canonical source order and the rejection of unsupported risk-based reordering
  are explicit.
- #3218 now has a measurable hybrid decision rule and explicit re-evaluation
  triggers.
- Future PermissionRequest producer accountability is explicit.

### Final Votes

| Agent | Position |
|-------|----------|
| architect | Accept |
| critic | Accept |
| independent-thinker | Accept |
| security | Accept |
| analyst | Accept |
| high-level-advisor | Accept |

Final tally: **6 Accept, 0 Disagree-and-Commit, 0 Block**. Consensus reached.

## 2026-07-21 Post-Merge Registration Rebaseline

PR #3259 removed `branch_context_guard` and `git_hooks_activation`. PR #3293
removed `skill_first_guard`. Regeneration reduced the current source set from 30
to 26 registrations without changing the dispatcher decision.

The rebaseline records 26 source registrations across six events, 13 PreToolUse
shims, a 465-second manifest timeout sum, a 470-second generated host request,
73.1 percent host-entry reduction, and up to 12 later PreToolUse shims bypassed
by a first-shim hang.

## 2026-07-21 Final Reconciliation Convergence

The six roles reviewed the reconciled worktree after PR #3259 and PR #3293.
A stale Serena/LSP index initially returned deleted files from another worktree.
Absolute-path file reads, generated manifests, and the D-A and D-B absence
regressions were treated as authoritative.

The final correction distinguishes the 465-second PreToolUse manifest sum from
the generated 470-second host request, which includes five seconds of dispatcher
headroom.

### Final Votes

| Agent | Vote | Remaining position |
|-------|------|--------------------|
| architect | Accept | No P0 or P1 remained. |
| critic | Accept | The rejected hybrid wording no longer embeds a stale process count. |
| independent-thinker | Accept | The manifest sum and host timeout now match the generated artifact. |
| security | Accept | The dormant PermissionRequest adapter remains unregistered; any producer requires fresh review. |
| analyst | Accept | Current counts, timeout arithmetic, and absence tests align with disk bytes. |
| high-level-advisor | Accept | Historical counts remain inside dated sections; the current rebaseline is explicit. |

Final tally: **6 Accept, 0 Disagree-and-Commit, 0 Block**. No P0 or P1
finding remained.

## References

- `.agents/architecture/ADR-068-consolidated-hook-dispatcher.md`
- `.agents/architecture/ADR-071-plugin-hook-runtime-contract-verification.md`
- `.agents/architecture/ADR-074-security-review-quick-pass-mode.md`
- `.agents/architecture/ADR-084-vendored-hook-roi-bar.md`
- `.agents/architecture/ADR-085-cross-harness-permission-surface-asymmetry.md`
- `.agents/audits/2026-07-02-safety-audit.md`
- `.claude/lib/hook_dispatch.py`
- `build/scripts/generate_dispatcher.py`
- `build/scripts/generate_hooks_events.py`
- `tests/build_scripts/test_generate_dispatcher.py`
- `tests/build_scripts/test_generate_hooks.py`
- `tests/build_scripts/test_dispatcher_matcher_union.py`
- `tests/test_hook_dispatch.py`
- `tests/build_scripts/test_copilot_dispatcher_artifact.py`
- `.serena/memories/reviews/fix-copilot-hook-contract-213f3af.md`
- `.claude/skills/agent-harness-reference/references/official-hook-contracts.md`
- `.claude/skills/agent-harness-reference/references/probe-evidence.md`
