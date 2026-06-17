---
id: ADR-074
status: proposed
date: 2026-06-17
decision-makers: []
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-074: Bounded Security-Review Quick-Pass Mode

## Status

Proposed. Requested by issue #2617 (labels `bug`, `enhancement`, `agent-security`, `area-workflows`, `priority:P1`, `automation`). Maintainer-approved DEFER on 2026-06-17 (issue comment 4726185340) that named the next gate as "an ADR + phased impl" plus "security-agent review required before merge".

This ADR proposes a change to a security-sensitive contract (the security-review verdict taxonomy and the orchestrator gate that consumes it). Per `.claude/rules/security.md` MUST-1, it MUST clear architect review, the adr-review skill debate, and security-agent review before its status moves to `Accepted`. The multi-agent adr-review debate and human acceptance are the next gate; this ADR does not run that debate and ships no implementation.

## Date

2026-06-17

## Context

A `security-review` subagent can run for several minutes without a completed turn. During PR #2611 autofix, the security review of a four-file `guards.py` hook diff:

- Timed out after 120 seconds with `total_turns: 0` and `tool_calls_completed: 16`, elapsed 231 seconds.
- Later produced useful findings, but each re-review cost enough that the main flow had to interleave unrelated validation work and repeatedly wait.
- Reviewed a four-file hook utility change whose local targeted gates completed in seconds.

The cost is not a missing review. The review is valuable and stays mandatory. The cost is the absence of any time-bound or progress signal, which makes local PR repair slower, complicates coordination with remote bot reviews, and widens the window for branch divergence while the author waits.

Three forces drive a decision now:

1. **No time budget on the review.** The security agent (`templates/agents/security.shared.md`) and its inline projection (`.claude/skills/security-review/SKILL.md`, v0.1.0) carry only the full threat-model protocol. There is no wall-clock cap and no fast-path. A four-line change and a four-thousand-line change receive the same unbounded analysis depth. A grep for `budget|quick-pass|timeout|progress-report|needs_deeper|classify_diff` across both files returns zero hits (verified on `main` at commit fb9741fa9b, 2026-06-17).

2. **No cheap verdict for the common case.** The full review is gated on a mandatory threat-model reasoning protocol: for every finding the agent must name the attack surface, the threat actor, and the impact before assigning severity (`security.shared.md` lines 109 to 119). That protocol is correct and load-bearing for HIGH and CRITICAL findings, but it makes "this small diff has no exploitable pattern" as expensive to assert as "this large diff has a confirmed RCE". PR automation has no way to ask the cheaper question.

3. **No progress signal during the silent window.** When analysis exceeds two minutes, the caller cannot distinguish a working agent from a wedged one. The orchestrator's PIV verdict gate (`security.shared.md` line 298) blocks PR creation on a `BLOCKED` verdict, so a silent long-running review stalls the whole flow with no observability.

The budget-watchdog and structured-exhaustion pattern already exists in this repository. ADR-068 (consolidated hook dispatcher) enforces a per-event wall-clock cap (`COPILOT_HOOK_DISPATCH_BUDGET_MS`, default 1500 ms), implemented with `signal.SIGALRM` on POSIX and a watchdog thread on Windows, and on exhaustion fails closed with a structured `budget_exceeded` reason (ADR-068 Decision item 4; Implementation Notes item 4, lines 222 to 224). This ADR reuses that pattern at the security-review boundary rather than inventing a parallel one.

## Decision

Add a bounded quick-pass mode to security review, governed by a diff-scope classifier, a budget watchdog, and an extended verdict taxonomy. The full threat-model review is unchanged and remains the default for any diff the classifier does not route to quick-pass and for any quick-pass result that detects a pattern.

Four parts, each independently shippable and reversible:

### 1. Diff-scope classifier

A pure function `classify_diff_scope(file_count, lines_changed) -> tier` maps a diff to one of four tiers. The classifier runs before any review work and its result is logged in structured output.

| Tier | Files | Lines changed | Default mode | Default budget |
|------|-------|---------------|--------------|----------------|
| small | <= 5 | <= 200 | quick | 30 s |
| medium | <= 15 | <= 1000 | full | 120 s |
| large | <= 50 | <= 5000 | full | 300 s |
| extra-large | > 50 | > 5000 | full | no cap |

A diff that exceeds either bound of a tier promotes to the next tier (a 3-file, 900-line diff is `medium`, not `small`). The caller MAY override the tier upward (to a larger tier) with an explicit `--tier` flag to force a deeper review, but MUST NOT override to a smaller tier than the classifier determines. The caller MAY force the full review with `--depth full`. The classifier selects a default; it never overrides an explicit caller request for a deeper review.

### 2. Budget watchdog

The review respects a wall-clock budget. The budget comes from, in precedence order: an explicit `--budget-ms` flag, then the `SECURITY_REVIEW_BUDGET_MS` environment variable, then the tier default. The watchdog reuses the ADR-068 mechanism (`signal.SIGALRM` on POSIX, watchdog thread on Windows).

On budget exhaustion the review does not silently truncate and does not emit a forged clearance. It emits a partial report carrying the work completed (files scanned, patterns checked, findings so far) and the structured verdict `budget_exceeded` plus a `needs_deeper_pass: true` flag. The orchestrator decides whether to retry with a larger budget, route to the full subagent, or escalate to a human. `budget_exceeded` is a non-clearing verdict: it never satisfies the PIV gate on its own.

### 3. Quick-pass mode and extended verdict taxonomy

Quick-pass mode scans only for the highest-confidence, highest-severity patterns and skips the per-finding threat-model reasoning protocol. The pattern set is the existing BLOCKED-trigger set already enumerated in the canonical verdict rules (`security.shared.md` lines 127 to 128): CWE-22 (path traversal), CWE-77 and CWE-78 (command injection), hard-coded secrets and credentials (CWE-798), and ASI01 to ASI10 boundary violations.

**Incomplete-diff precondition.** Before pattern scanning, quick-pass verifies that all required inputs are present (changed files, test coverage data if the diff touches security-critical paths, dependency manifest if dependencies changed). If any required artifact is missing, quick-pass returns `[BLOCKED] Cannot evaluate: <specific missing artifact>` per the fail-closed rule (`security.shared.md` line 129). An incomplete diff MUST NOT receive `QUICK_PASS`; the incomplete-diff gate fires before pattern matching.

Quick-pass returns one of two new verdicts:

| Verdict | Meaning | Action |
|---------|---------|--------|
| QUICK_PASS | No quick-pass pattern matched in scope | Clears the gate for small diffs only; logged as quick-pass, not as a full audit |
| NEEDS_DEEP_REVIEW | A quick-pass pattern matched, or the scope is ambiguous | Re-route to the full threat-model review; never clears the gate by itself |

The full review keeps its existing terminal verdicts unchanged: APPROVED, CONDITIONAL, BLOCKED (`security.shared.md` lines 125 to 127). Quick-pass does not replace them; it is a pre-filter that either clears a small, clean diff cheaply or hands a suspicious one to the full review.

The orchestrator PIV gate (`security.shared.md` line 298) is extended to consume the new verdicts: `QUICK_PASS` clears the gate only for diffs the classifier tiered as `small`; `NEEDS_DEEP_REVIEW` and `budget_exceeded` never clear it. APPROVED, CONDITIONAL (with a cited follow-up issue), and BLOCKED keep their current gate semantics.

### 4. Progress reporting

While a review runs longer than 30 seconds, it emits a progress checkpoint to stderr at 30-second intervals. Each checkpoint carries `elapsed_ms`, `remaining_ms`, `files_scanned`, and `findings_count`. This satisfies the issue's acceptance criterion that the agent reports progress before long-running analysis exceeds two minutes, and it gives the orchestrator a liveness signal to distinguish a working review from a wedged one.

### Scope discipline

This ADR records the decision and the contract. It ships no code. The canonical source of behavior is `templates/agents/security.shared.md`; `.claude/skills/security-review/SKILL.md` and the Copilot instruction mirrors are projections that re-sync from it (per the canonical-source-mirror rule). Any implementation lands behind the security-agent review this ADR names as its next gate.

## Prior Art Investigation (Required when changing existing systems)

### What Currently Exists

- **Structure/pattern being changed**: the security-review verdict taxonomy (APPROVED / CONDITIONAL / BLOCKED) and the unbounded full threat-model protocol in `templates/agents/security.shared.md`, projected into `.claude/skills/security-review/SKILL.md` (v0.1.0).
- **When introduced**: always-on security review scope (PR #1681); prompt-discipline hardening to A tier (PR #2086, issue #2003); skill projection (issue #1875, ADR-058).
- **Original author and context**: the verdict gate and threat-model protocol are the product of the security-agent prompt-optimization line of work; the PIV verdict gate predates this issue.

### Historical Rationale

- **Why was it built this way?** Security review is mandatory and defense-first. The threat-model protocol exists to stop the agent from guessing a severity without a named actor and named impact (`security.shared.md` line 115). Unbounded depth was acceptable when review was a discrete step, not an inner loop of PR autofix.
- **What alternatives were considered?** Raising the host timeout was rejected upstream in ADR-068 for hooks ("Copilot ignores it") and is equally ineffective here, since the cost is the agent's own analysis depth, not a host kill.
- **What constraints drove the design?** 100% security coverage (`AGENTS.md`); fail-closed on incomplete diffs (`security.shared.md` line 129); no lowering of severity thresholds without a governance ADR (`.claude/rules/security.md` MUST-NOT-1).

### Why Change Now

- **Has the original problem changed?** Yes. Security review now runs inside PR autofix as an inner loop (PR #2611 evidence), where a 231-second silent review stalls automation it never used to gate.
- **Is there a better solution now?** Yes. The ADR-068 budget-watchdog pattern (shipped, tested) gives a reusable structured-exhaustion mechanism that did not exist when the security agent was first written.
- **What are the risks of change?** A quick-pass that clears a diff carrying a vulnerability its pattern set does not cover. Mitigated by restricting QUICK_PASS to clear only `small` diffs, restricting the quick-pass pattern set to the existing BLOCKED-trigger set, and routing every pattern match and every ambiguity to the full review. The change adds verdicts and a pre-filter; it removes no check and lowers no threshold.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Raise the subagent/host timeout | Zero contract change | Does not bound analysis depth; the agent still runs unbounded inside the budget; just delays the stall | Rejected: treats the symptom, not the cost (same defect ADR-068 names for hooks) |
| Quick-pass with no full-review fallback | Fastest path | A pattern the quick set misses ships uncaught; lowers effective coverage | Rejected: violates 100% security coverage and `.claude/rules/security.md` MUST-NOT-1 |
| Budget watchdog only, no quick-pass | Bounds wall-clock; smallest change | A budget-exhausted review on a small clean diff still returns no verdict; the common case stays slow | Rejected: does not satisfy the "cheaper quick-pass for high-confidence findings" acceptance criterion |
| Diff-scope classifier + budget watchdog + quick-pass + progress, full review unchanged as fallback | Bounds time, gives a cheap common-case verdict, preserves full coverage via fallback, reuses ADR-068 | Adds two verdicts and a gate branch; the classifier is a new tuning surface | **Chosen**: smallest change that meets all three acceptance criteria without lowering coverage |

### Trade-offs

The quick-pass pattern set is deliberately the existing BLOCKED-trigger set, not a new, broader set. This keeps the quick scan honest: it asserts only "none of the things that already force a BLOCK are present", and it hands everything else to the full review. The classifier thresholds (5 files / 200 lines for small) are a tuning surface; they are defaults a caller can override, and they are chosen to match the issue's four-file evidence. The full review's correctness is untouched: it remains the authority, and quick-pass can only short-circuit it for a small, clean diff or defer to it.

## Consequences

### Positive

- A small four-file hook diff gets a bounded verdict (QUICK_PASS or NEEDS_DEEP_REVIEW) within 30 seconds, or an explicit `needs_deeper_pass` signal. PR autofix stops stalling on the common case.
- PR automation can request a high-confidence quick review without waiting for a full deep audit (acceptance criterion 2).
- The orchestrator gets a progress signal before the two-minute mark and can tell a working review from a wedged one (acceptance criterion 3).
- The budget-exhaustion path is structured (`budget_exceeded` + `needs_deeper_pass`), reusing the ADR-068 contract rather than a parallel one.

### Negative

- Two new verdicts and a new gate branch widen the verdict taxonomy the orchestrator must understand. Mitigated by keeping the full-review terminal verdicts unchanged and making the new verdicts strictly non-clearing except QUICK_PASS-on-small.
- The classifier thresholds are a new tuning surface that can be mis-set. Mitigated by caller override and by failing toward the full review (any doubt routes to NEEDS_DEEP_REVIEW).
- The canonical-source change to `security.shared.md` requires re-syncing the skill projection and the Copilot mirrors in the same change set (canonical-source-mirror rule).

### Neutral

- The full threat-model protocol is unchanged for medium, large, and extra-large diffs and for any quick-pass that detects a pattern.
- `SECURITY_REVIEW_BUDGET_MS` mirrors the `COPILOT_HOOK_DISPATCH_BUDGET_MS` naming from ADR-068.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `templates/agents/security.shared.md` | Direct (canonical source) | Add quick-pass mode, classifier reference, two verdicts, budget and progress contract; extend PIV gate to consume new verdicts | High (security-sensitive contract; security-agent review required) |
| `.claude/skills/security-review/SKILL.md` | Direct (projection) | Re-sync from canonical: project quick-pass content and the QUICK_PASS / NEEDS_DEEP_REVIEW verdicts; keep the existing IDENTIFY/OK/ESCALATE divergence note accurate | Medium |
| Copilot instruction mirrors (`.github/instructions/`, `src/copilot-cli/instructions/`) | Indirect | Regenerate from templates after the canonical change | Medium |
| Orchestrator PIV verdict gate | Direct | Branch on QUICK_PASS (clears only for `small`), NEEDS_DEEP_REVIEW and `budget_exceeded` (never clear) | High (gate is the security boundary) |
| `.agents/governance/SECURITY-REVIEW-PROTOCOL.md` | Direct | Document the quick-pass mode and the budget-exhaustion handling in the review workflow | Medium |
| Implementation scripts (classifier, watchdog) | New | New Python modules with pytest coverage; 100% coverage per `AGENTS.md` security floor; SIGALRM/watchdog parity with ADR-068 | Medium |

## Implementation Notes

Phased, each phase independently shippable and reversible, ordered so the cheapest and least risky lands first:

1. **Diff-scope classifier.** `classify_diff_scope(file_count, lines_changed) -> tier` as a pure function with parametrized pytest cases on every tier boundary (4/200, 5/200, 6/201, etc.). No behavior change to review depth yet; classifier output is logged only.
2. **Budget watchdog.** `SECURITY_REVIEW_BUDGET_MS` plus `--budget-ms`, watchdog via `signal.SIGALRM` (POSIX) and a watchdog thread (Windows), emitting `budget_exceeded` + `needs_deeper_pass` on exhaustion. Reuse the ADR-068 implementation shape; do not fork a second watchdog.
3. **Quick-pass mode and verdicts.** Scan the BLOCKED-trigger pattern set only; skip the threat-model protocol; return QUICK_PASS or NEEDS_DEEP_REVIEW. Extend the PIV gate. Coverage: positive (clean small diff -> QUICK_PASS), negative (planted CWE-78 -> NEEDS_DEEP_REVIEW), edge (ambiguous scope -> NEEDS_DEEP_REVIEW, incomplete diff missing changed files -> BLOCKED Cannot evaluate).
4. **Progress reporting.** 30-second-interval stderr checkpoints with `elapsed_ms`, `remaining_ms`, `files_scanned`, `findings_count`.

Each phase carries pos/neg/edge tests per `.agents/governance/TESTING-RIGOR.md`. The canonical change to `security.shared.md` and its projections land together in one change set per the canonical-source-mirror rule.

## Related Decisions

- ADR-068 (Consolidated Hook Dispatcher): source of the budget-watchdog and structured `budget_exceeded` pattern this ADR reuses.
- ADR-066 (Hook Fail-Open Reconciliation) and ADR-071 (Plugin Hook Runtime Contract Verification): fail-closed precedent that `budget_exceeded` follows (never clears the gate).
- ADR-058 (Agent Eval Discipline): the `security` agent / `security-review` skill form-factor pairing this ADR extends.
- ADR-059 (PR-Review Completion Gate Dispatcher): structured-output dispatcher pattern the verdict consumer follows.
- ADR-002 (Agent Model Selection): the security agent runs `opus`; quick-pass mode does not change model selection.
- ADR-073 (Machine-Readable ADR Lifecycle Frontmatter): frontmatter schema this ADR adopts.

## References

- Issue #2617: bounded quick-pass mode request, with PR #2611 timing evidence and maintainer DEFER (comment 4726185340).
- `templates/agents/security.shared.md` lines 109 to 129, 298: threat-model protocol, verdict taxonomy, PIV gate.
- `.claude/skills/security-review/SKILL.md` (v0.1.0): inline projection and verdict divergence note.
- `.agents/architecture/ADR-068-consolidated-hook-dispatcher.md` Decision item 4, Implementation Notes item 4: budget watchdog.
- `.agents/governance/SECURITY-REVIEW-PROTOCOL.md`: review workflow.
- `.agents/governance/SECURITY-SEVERITY-CRITERIA.md`: severity thresholds (unchanged by this ADR).
- `.claude/rules/security.md`: security-agent review requirement and severity-threshold MUST-NOTs.
- `.claude/rules/canonical-source-mirror.md`: canonical-to-projection re-sync contract.
- CWE-22, CWE-77, CWE-78, CWE-798; ASI01 to ASI10: the quick-pass pattern set.
