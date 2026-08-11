# ADR-071 Review Debate Log (renumbered from ADR-063)

**ADR**: `.agents/architecture/ADR-071-plugin-hook-runtime-contract-verification.md` (renumbered from ADR-063 per #2228)
**Date**: 2026-06-02
**Protocol**: 6-agent adr-review (architect, critic, independent-thinker, security, analyst, high-level-advisor)
**Outcome**: Consensus reached. 2 Accept, 4 Disagree-and-Commit, 0 Block. P0/P1 dissents resolved in revision.

## Verdicts

| Agent | Verdict | Headline finding |
|-------|---------|------------------|
| architect | Accept | Format coherent with ADR-062; FM #11 placement correct; missing Reversibility/Vendor-lock-in section (P1). |
| critic | Disagree-and-Commit | P0: anchoring gate + e2e run only in pre-push (bypassable); no server-side CI gate. P1: validator hardcodes two artifact paths. P1: deferred launcher fix unowned. |
| independent-thinker | Disagree-and-Commit | P0: anchoring rides undocumented vendor vars; deferring launcher graceful-degradation leaves blast radius open. P1: contract test injects the var it checks (self-referential). |
| security | Accept | CWE-78 not reachable (double-quoted expansion not re-tokenized, proven empirically); CWE-426 needs same-user (no new trust boundary); deferrals OK. All P2. |
| analyst | Disagree-and-Commit | All technical claims verified at file:line. P1: quote the contract verbatim (canonical-source-mirror); distinguish the two test files in Consequences. |
| high-level-advisor | CONCERNS / D&C | P0: convert launcher graceful-degradation from open-ended deferral to a committed, issue-tracked follow-up with the fail-open-at-launcher principle. P1: no-auth cross-platform (Windows pwsh) contract sim in CI. |

## P0/P1 issues and resolutions

| # | Pri | Finding | Resolution |
|---|-----|---------|-----------|
| 1 | P0 | No server-side (CI) enforcement of the anchoring gate; pre-push is bypassable (`--no-verify`, fork PR, release from un-pre-pushed branch). | Added a `Run hook anchoring gate` step to `.github/workflows/validate-plugin-manifests.yml`, which triggers on any `**/hooks/hooks.json` or manifest change. The no-auth runtime-contract test and the validator unit test already run in `pytest.yml`. |
| 2 | P0 | Launcher graceful-degradation (proposed as the control to bound the wedge blast radius) was an open-ended deferral with no owner. | Resolved by rejecting launcher fail-open in favor of prevention plus loud failure: anchoring + the runtime-contract gate catch a broken launcher before release, and an escaped failure fails loud rather than silently exiting 0. ADR Decision item 5 records the fail-closed position; issue #2230 closed addressed-by-prevention. |
| 3 | P1 | Contract test injects the plugin-root var it then checks (self-referential); could pass while production breaks on vendor drift. | Added `test_anchor_is_load_bearing_when_no_plugin_root_var_set`: with no var set, the anchored path must NOT resolve. Documented that the contract sim verifies path resolution, not vendor behavior (the real-CLI e2e does that). |
| 4 | P1 | ADR doc gaps: no Reversibility/Vendor-lock-in section; contract not quoted verbatim; two test files conflated; undocumented-var fragility unstated. | Added Reversibility and Vendor Lock-in section; added a verbatim measurement block and an explicit "not a vendor contract" caveat; distinguished the three verification layers (validator, runtime-contract test, real-CLI e2e) in Consequences. |
| 5 | P1 | Validator hardcodes two artifact paths; a new hook-bearing platform ships ungated. | Tracked in issue #2231 (glob/registry-based discovery). |
| 6 | P1 | Windows PowerShell path-resolution has no always-on CI gate (incident was reported on Windows). | Tracked in issue #2231 (no-auth Windows pwsh contract sim in CI). |
| 7 | P2 | Security: keep the command double-quoted (an unquoted future variant would be CWE-78); restrict the e2e probe env dump; nightly smoke needs secrets governance; run the nightly from a trusted ref only. | Recorded in the rule and issue #2231; the e2e probe dumps only the two named path vars. |

## Anti-pattern self-check (Zimmermann)

No Pass-Through (all agents produced substantive, cited findings). No Groundhog Day (each round distinct). No rubber-stamping: the security and architect Accepts cite specific evidence; the four D&C votes each carry concrete, file-cited dissent that was resolved in revision rather than waved through.

## Disposition

ADR-071 status set to Accepted. All P0 issues resolved in code/ADR; all P1 issues resolved or tracked with an issue (#2230, #2231). Dissent preserved here.

## 2026-07-19 Amendment Review

### Summary

- **Scope**: Copilot CLI 1.0.72-1 contract amendment and its relationship to
  ADR-068 and ADR-074.
- **Rounds**: 2
- **Outcome**: Consensus
- **Final tally**: 3 Accept, 3 Disagree-and-Commit, 0 Block
- **Security assessment**: Accept, PASS_WITH_NOTES

Round 1 identified inaccurate timeout-budget, dispatcher-mode, matcher,
evidence-provenance, and ADR-074 prior-art claims. The corrected amendment
cites the curated probe summary at
`.claude/skills/agent-harness-reference/references/probe-evidence.md`, section
4, distinguishes host timeout metadata from an in-process watchdog, and
records the Copilot CLI 1.0.72-1 host-timeout fail-open residual.

The supplied Round 1 record named all six roles but did not retain individual
Round 1 vote labels. This amendment log does not reconstruct missing votes.
All Round 1 P0/P1 categories were corrected before Round 2.

### Round 2 Votes

| Agent | Vote | Recorded disposition |
|-------|------|----------------------|
| high-level-advisor | Accept | No blocking issue remained. |
| security | Accept | PASS_WITH_NOTES. The host-timeout fail-open residual remains explicit. |
| independent-thinker | Accept | No blocking issue remained. |
| architect | Disagree-and-Commit | Accepted the corrected amendment with nonblocking reservations. |
| analyst | Disagree-and-Commit | Accepted the corrected amendment with nonblocking reservations. |
| critic | Disagree-and-Commit | Acceptance-evidence gaps required durable debate logs; those record corrections are part of this change. |

### Accepted Residuals and Dissent

- Copilot CLI 1.0.72-1 can fail open when the host timeout expires. A hung
  consolidated dispatcher can prevent later guards from running before the
  tool is allowed. ADR-071 lines 135 to 139 record this residual.
- Windows PowerShell contract simulation and authenticated cross-platform
  smoke coverage remain tracked by issue #2231.
- The architect, analyst, and critic votes are durable
  Disagree-and-Commit positions. No separate Round 2 rationale was retained
  for architect or analyst, so this log does not attribute one.

Consensus is achieved under the adr-review protocol because all six roles
voted Accept or Disagree-and-Commit and no role voted Block.

## 2026-07-19 Contract Hardening Review

### Scope

This review checked the final runtime-contract wording against the official
sidecar, the 1.0.72-1 probe record, ADR-068, and the generated dispatcher
shape. Phase 1 required corrections before convergence.

### Corrected claims

- The 1.0.72-1 probe did not independently measure generated `cwd: "."`.
  Launchers do not use cwd to locate plugin scripts.
- Empty PermissionRequest output uses normal host handling. The noninteractive
  probe denied, but empty output is not a universal deny contract.
- The current PreToolUse dispatcher has 18 shims and requests 615 seconds. The
  timeout probe covered only 2 seconds.
- PreCompact is official-contract-backed, with an inconclusive runtime trigger
  probe.
- Copilot parses at most one final JSON document per command hook. Future
  structured observer output needs a merger or direct registrations.

### Convergence votes

| Agent | Vote | Remaining position |
|-------|------|--------------------|
| architect | Accept | No architecture blocker remained. |
| critic | Accept | No P0 or P1 issue remained. |
| independent-thinker | Accept | Cross-reference anchors resolve. |
| security | Accept | Timeout fail-open is explicit and quantified. |
| analyst | Accept | Claims align with labeled official and empirical evidence. |
| high-level-advisor | Accept | No strategic blocker remained. |

Final tally: **6 Accept, 0 Disagree-and-Commit, 0 Block**. Consensus reached.

### Accepted residuals

- The host's treatment of a 615-second requested timeout is not measured.
- Windows PowerShell runtime coverage remains tracked by issue #2231.
- Copilot documentation and the 1.0.72-1 `general-purpose` subagent observation
  still disagree. The reference keeps that row unresolved and version-specific.

## 2026-07-20 Observer Output Wording Review

### Scope

This review checked the correction from stale observer stdout passthrough prose
to the event-specific output policy already implemented by ADR-068 and
`hook_dispatch.py`. It did not reopen the architecture or change ADR status.

### Votes

| Agent | Vote | Position |
|-------|------|----------|
| architect | Accept | The amendment matches ADR-068 and the generated dispatchers. |
| critic | Disagree-and-Commit | Requested delimiter, attribution, and stderr consequences. |
| independent-thinker | Accept | The wording matches implementation and tests. |
| security | Disagree-and-Commit | Requested explicit diagnostic-only stderr wording. |
| analyst | Accept | Each sentence traced to implementation and official sources. |
| high-level-advisor | Accept | The correction is scoped and does not reopen the decision. |

Final tally: **4 Accept, 2 Disagree-and-Commit, 0 Block**. Consensus reached.
The ADR now records blank-output behavior, the blank-line delimiter, loss of
per-shim attribution, failed-output discard, and that stderr is not a documented
model-context path. No P0 or P1 issue remained.

## 2026-07-21 Post-Merge Timeout Rebaseline (Historical Snapshot)

This section records the tree reviewed on 2026-07-21. The 13-shim and
465/470-second values are historical, not current inventory.

PR #3259 removed two PreToolUse shims and one SessionStart shim. PR #3293
removed one more PreToolUse shim. The current PreToolUse manifest now contains
13 shims whose configured values sum to 465 seconds. The generated host entry
requests 470 seconds after five seconds of dispatcher headroom. The 1.0.72-1
timeout probe remains bounded to 2 seconds, so the host-cap uncertainty and
fail-open residual do not change.

## 2026-07-21 Final Reconciliation Convergence (Historical Snapshot)

The six roles reviewed the current worktree, generated manifest, and corrected
timeout wording. The manifest contains 13 PreToolUse shims whose configured
values sum to 465 seconds. The generated host entry requests 470 seconds. The
runtime probe remains limited to 2 seconds.

### Final Votes

| Agent | Vote | Remaining position |
|-------|------|--------------------|
| architect | Accept | No P0 or P1 remained. |
| critic | Accept | The current and historical timeout snapshots are clearly separated. |
| independent-thinker | Accept | The five-second dispatcher headroom is now explicit. |
| security | Accept | The 470-second host-cap uncertainty and fail-open residual remain explicit. |
| analyst | Accept | ADR, debate log, generated artifact, and regression test agree. |
| high-level-advisor | Accept | The 2-second probe gap is retained as an accepted residual. |

Final tally: **6 Accept, 0 Disagree-and-Commit, 0 Block**. No P0 or P1
finding remained.

## 2026-08-09 Issue #4764 Timeout Amendment

The six roles verified the updated runtime-contract residual after the active
PreToolUse manifest grew to two shims.

| Agent | Vote | Remaining position |
|-------|------|--------------------|
| architect | Accept | Two shims, 100 seconds, and 105 seconds match artifacts. |
| critic | Accept | The amendment changes facts, not the accepted contract. |
| independent-thinker | Accept | The host-enforcement uncertainty stays explicit. |
| security | Accept | Fail-open impact now covers every active guard. |
| analyst | Accept | Manifest and generated hook values match exactly. |
| high-level-advisor | Accept | The update is sufficient and proportionate. |

Final tally: **6 Accept, 0 Disagree-and-Commit, 0 Block**. No P0 or P1
finding remained.

## 2026-07-22 PR #3292 Release Convergence

The six roles reviewed the supply-chain amendment, current workflow, Renovate
resolution, exact CLI package pins, shared Copilot launcher helper, and pinned
real-CLI evidence.

### Corrections verified

- The npm install step receives no smoke credentials. Only the two real-CLI
  execution steps receive `ANTHROPIC_API_KEY` and `COPILOT_GITHUB_TOKEN`.
- Claude Code 2.1.217 and Copilot CLI 1.0.73 are exact top-level pins. The ADR
  states that transitive dependencies remain range-resolved.
- Renovate tracks both pins, cannot auto-merge their updates, and excludes them
  from the general minor and patch auto-merge rule.
- Plain startup from `@github/copilot@1.0.73` executed binary 1.0.74-0. The
  shared `copilot_command` helper now inserts `--no-auto-update`, and a unit
  test locks that flag.
- A pinned replay passed three Copilot cases and two Claude cases. The JUnit
  gate parses exactly one `--smoke-substr test_plugin_load_smoke` and one
  `--expected-count 3`, so one skipped plugin-load case cannot read green.
- The nightly remains a lagging, pin-specific signal. Anchoring, static gates,
  simulated runtime tests, and loud launcher failure protect users before a
  reviewed pin change lands.

### Final votes

| Agent | Vote | Remaining position |
|-------|------|--------------------|
| architect | Accept | Pins, Renovate behavior, and runtime evidence align. |
| critic | Accept | The duplicate JUnit gate argument was removed and test-locked. |
| independent-thinker | Accept | The reviewed-pin and lagging-signal trade is explicit. |
| security | Accept | Credential scope and update suppression close both blockers. |
| analyst | Accept | Direct file reads confirmed every Copilot start uses the helper. |
| high-level-advisor | Accept | The helper test reduces the update-bypass risk to normal review. |

Final tally: **6 Accept, 0 Disagree-and-Commit, 0 Block**. No P0 or P1
finding remained.
