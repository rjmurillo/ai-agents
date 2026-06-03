# ADR-067 Review Log

**ADR**: ADR-067 Single In-Process Dispatcher for Copilot CLI Hooks
**Status reviewed**: DRAFT
**Date**: 2026-06-03
**Reviewer note**: Focused single-pass review applying the adr-review structure
(Zimmermann 7-question + strategic lenses). Full 6-agent consensus is NOT yet
recorded; it remains a gate on the cutover per the ADR's own Rollout section.
The mechanism is unit- and runtime-validated (19 tests + real-shim dispatch),
so this review scrutinizes the design and the rollout safety, not whether the
code runs.

## Phase 0: Related work

- #2295 (defect + measurements), #2300 (validation harness), #2290/#2293
  (payload schema casing, prerequisite), #2271 / #2230 (fail-closed contract
  this design must preserve). ADR-063 (hook/skill runtime decomposition).

## Findings by lens

### architect (structure / coherence): ACCEPT

- Decision is one sentence, reversible (gated, default-off), and the runtime
  contract is explicit. The matcher-shim logic and every guard are unchanged;
  only the dispatch layer is added. Coherent with the existing generator seam.

### critic (gaps / risks): ACCEPT WITH P1

- P1: per-shim `timeoutSec` granularity (2-90 s) is lost when collapsing to one
  entry. Mitigation in ADR: use the max; acceptable because Copilot ignores
  `timeoutSec` anyway. Documented. Resolved.
- P2: output concatenation when NOT short-circuiting. The design short-circuits
  on first denial, so only the blocking guard's output surfaces. Acceptable.

### independent-thinker (assumptions): ACCEPT

- Challenges "in-process is safe": runpy reuses cached imports across shims, so
  one slow-importing guard pays its import once for the whole event, not N
  times. The test `test_dispatcher_runs_every_registered_shim` confirms all 29
  real guards run in one process. Assumption holds.

### security (threat model): ACCEPT WITH P0 (resolved)

- P0: a dispatch bug must never fail OPEN. Verified: missing shim -> deny,
  unexpected exception -> deny, non-int exit -> deny, only all-zero -> allow.
  Tests `test_missing_shim_fails_closed`, `test_shim_uncaught_exception_fails_closed`,
  `test_non_int_systemexit_is_denial` cover it. The shim set is manifest-driven
  (the registered list), so the 38-disk-vs-29-registered gap cannot run orphans
  (`test_orphan_file_not_in_manifest_is_not_run`). Fail-closed preserved. P0
  resolved.
- Residual: the consolidation is a single point of execution per event. Bounded
  by the gated rollout + the #2300 real-Copilot validation requirement.

### analyst (evidence / feasibility): ACCEPT

- The 246 ms-per-shim cold-start measurement (#2295) is the load-bearing
  evidence; in-process dispatch removes (N-1) cold starts. Estimated ~400 ms vs
  ~8.7 s. Feasible and proportionate.

### high-level-advisor (priority / ties): ACCEPT

- This unblocks Copilot CLI users hitting false fail-closed denials (a P1
  reliability defect). The gated rollout means landing it now carries no runtime
  risk. Ship the mechanism; gate the cutover. No ties to break.

## Strategic checklist

- **Chesterton's Fence**: the per-shim-entry pattern exists because Copilot has
  no matcher; the dispatcher keeps the self-filtering shims and only changes how
  they are launched. Original purpose preserved. PASS.
- **Path Dependence**: reversible. Default-off; the cutover is one flag and one
  regeneration, revertable by regenerating in the default mode. PASS.
- **Core vs Context**: hook dispatch latency is Context (a packaging concern);
  the fix is minimal, not a platform. PASS.
- **Second-System Effect**: scope is strictly the dispatch layer; no guard
  rewrites, no new capabilities. PASS.

## Verdict

**APPROVED to land the mechanism (DRAFT).** P0 (fail-closed) resolved with test
evidence; P1 (timeout granularity) documented and accepted. The live hooks.json
cutover remains BLOCKED on: (1) full 6-agent adr-review consensus, and (2) a
green `RUN_INSTALLED_PLUGIN_HOOK_E2E=1` run on a real Copilot install. These are
recorded in the ADR Rollout section and are not satisfied by this single-pass
review.
