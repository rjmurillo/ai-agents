---
id: ADR-074
status: accepted
date: 2026-06-17
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-074: Bounded Security-Review Quick-Pass Mode

## Status

Accepted by maintainer 2026-06-17.

Requested by issue #2617 (labels `bug`, `enhancement`, `agent-security`,
`area-workflows`, `priority:P1`, `automation`). Maintainer-approved DEFER on
2026-06-17 (issue comment 4726185340) named the next gate as "an ADR + phased
impl" plus "security-agent review required before merge". Issue #2617 was
closed as completed on 2026-06-17.

The repository retained no durable six-agent debate log for the original
acceptance. A mandatory review completed on 2026-07-19 and closed that
historical evidence gap without backdating the review: 3 Accept,
3 Disagree-and-Commit, and 0 Block. See
`.agents/critique/ADR-074-debate-log.md`.
The supplied Round 1 record did not retain individual vote labels; the debate
log preserves that evidence limit rather than reconstructing missing votes.

This ADR changes a security-sensitive contract (the security-review verdict taxonomy and the orchestrator gate that consumes it). DECISION acceptance is the maintainer's call, now given. The security-agent IMPLEMENTATION review still applies before the quick-pass CODE lands; this status flip ships no implementation.

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

ADR-068 does not provide a budget watchdog or structured-exhaustion
implementation. Its shipped dispatcher validates timeout metadata and delegates
aggregate timeout ownership to the host. ADR-068 rejected an in-process
`SIGALRM` or watchdog-thread kill because Python cannot safely terminate one
running guard while preserving the shared interpreter. This ADR therefore
cannot cite ADR-068 as reusable prior art. Its review deadline must be enforced
by a caller or isolated worker process that can be terminated safely.

## Decision

Add a bounded quick-pass mode to security review, governed by a diff-scope
classifier, a caller-enforced deadline, and an extended verdict taxonomy. The
full threat-model review is unchanged and remains the default for any diff the
classifier does not route to quick-pass and for any quick-pass result that
detects a pattern.

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

### 2. Caller-enforced deadline

The review respects a wall-clock budget. The budget comes from, in precedence
order: an explicit `--budget-ms` flag, then the
`SECURITY_REVIEW_BUDGET_MS` environment variable, then the tier default. The
orchestrator or an isolated worker process owns enforcement. An in-process
signal or watchdog thread is explicitly rejected because it cannot safely kill
the running review across supported platforms.

On budget exhaustion the caller does not emit a forged clearance. If the worker
has published a progress checkpoint, the caller may attach that checkpoint and
must label it partial. The caller emits the structured verdict
`budget_exceeded` plus `needs_deeper_pass: true`. The orchestrator decides
whether to retry with a larger budget, route to the full subagent, or escalate
to a human. `budget_exceeded` is a non-clearing verdict: it never satisfies the
PIV gate on its own.

### 3. Quick-pass mode and extended verdict taxonomy

Quick-pass mode scans only for the highest-confidence, highest-severity patterns and skips the per-finding threat-model reasoning protocol. The pattern set is the existing BLOCKED-trigger set already enumerated in the canonical verdict rules (`security.shared.md` lines 127 to 128): CWE-22 (path traversal), CWE-77 and CWE-78 (command injection), hard-coded secrets and credentials (CWE-798), and ASI01 to ASI10 boundary violations.

**Incomplete-diff precondition.** Before pattern scanning, quick-pass verifies that all required inputs are present (changed files, test coverage data when the diff matches a Security-Relevant Change Trigger in `security.shared.md` lines 300 to 313, dependency manifest if dependencies changed). If any required artifact is missing, quick-pass returns `[BLOCKED] Cannot evaluate: <specific missing artifact>` per the fail-closed rule (`security.shared.md` line 129). An incomplete diff MUST NOT receive `QUICK_PASS`; the incomplete-diff gate fires before pattern matching. The escalated full-review path retains the same existing fail-closed rule for incomplete inputs.

Quick-pass returns one of two new verdicts:

| Verdict | Meaning | Action |
|---------|---------|--------|
| QUICK_PASS | No quick-pass pattern matched in the full diff under review | Clears the gate for small diffs only; logged as quick-pass, not as a full audit |
| NEEDS_DEEP_REVIEW | A quick-pass pattern matched, or the scope is ambiguous | Re-route to the full threat-model review; never clears the gate by itself |

The full review keeps its existing terminal verdicts unchanged: APPROVED, CONDITIONAL, BLOCKED (`security.shared.md` lines 125 to 127). Quick-pass does not replace them; it is a pre-filter that either clears a small, clean diff cheaply or hands a suspicious one to the full review.

The orchestrator PIV gate (`security.shared.md` line 298) is extended to consume the new verdicts: `QUICK_PASS` clears the gate only for diffs the classifier tiered as `small`; `NEEDS_DEEP_REVIEW` and `budget_exceeded` never clear it. APPROVED, CONDITIONAL (with a cited follow-up issue), and BLOCKED keep their current gate semantics.

### 4. Progress reporting

While a review runs longer than 30 seconds, it emits a progress checkpoint to stderr at 30-second intervals. Each checkpoint carries `elapsed_ms`, `remaining_ms`, `files_scanned`, and `findings_count`. This satisfies the issue's acceptance criterion that the agent reports progress before long-running analysis exceeds two minutes, and it gives the orchestrator a liveness signal to distinguish a working review from a wedged one.

### Scope discipline

This ADR records the decision and the contract. It ships no code. The canonical source of behavior is `templates/agents/security.shared.md`; `.claude/skills/security-review/SKILL.md` and the Copilot instruction mirrors are projections that re-sync from it (per the canonical-source-mirror rule). Any implementation lands behind the security-agent review this ADR names as its next gate.

## Prior Art Investigation (Required when changing existing systems)

### What Currently Exists

- **Structure/pattern being changed**: the security-review verdict taxonomy (APPROVED / CONDITIONAL / BLOCKED) and the unbounded full threat-model protocol in `templates/agents/security.shared.md`, projected into `.claude/skills/security-review/SKILL.md` (v0.1.0 at decision time).
- **When introduced**: always-on security review scope (PR #1681); prompt-discipline hardening to A tier (PR #2086, issue #2003); skill projection (issue #1875, ADR-058).
- **Original author and context**: the verdict gate and threat-model protocol are the product of the security-agent prompt-optimization line of work; the PIV verdict gate predates this issue.

### Historical Rationale

- **Why was it built this way?** Security review is mandatory and defense-first. The threat-model protocol exists to stop the agent from guessing a severity without a named actor and named impact (`security.shared.md` line 115). Unbounded depth was acceptable when review was a discrete step, not an inner loop of PR autofix.
- **What alternatives were considered?** ADR-068 records that hook timeout
  behavior is host-owned and version-sensitive. Raising a timeout alone is
  equally insufficient here because it does not bound the agent's analysis
  depth.
- **What constraints drove the design?** 100% test coverage for security-critical implementation (`AGENTS.md`); fail-closed on incomplete diffs (`security.shared.md` line 129); no lowering of severity thresholds without a governance ADR (`.claude/rules/security.md` MUST-NOT-1).

### Why Change Now

- **Has the original problem changed?** Yes. Security review now runs inside PR autofix as an inner loop (PR #2611 evidence), where a 231-second silent review stalls automation it never used to gate.
- **Is there a better solution now?** Yes. A caller-enforced deadline around an
  isolated review worker can stop work safely and return a non-clearing
  exhaustion verdict. No such implementation has shipped yet.
- **What are the risks of change?** A quick-pass can clear a small diff carrying a vulnerability its pattern set does not cover. This is accepted reduced analysis depth, scoped to the `small` tier, with detection limited to the existing BLOCKED-trigger pattern set. A diff that matches no pattern in that set can clear without full threat-model analysis. Full review remains unchanged and callable through `--depth full`; pattern matches and ambiguity require it.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Raise the subagent/host timeout | Zero contract change | Does not bound analysis depth; the agent still runs unbounded inside the budget; just delays the stall | Rejected: treats the symptom, not the cost (same defect ADR-068 names for hooks) |
| Quick-pass for every diff with no scope gate or escalation | Fastest path | Large, ambiguous, or pattern-matching diffs could clear without threat-model review | Rejected: removes the fail-closed boundary around the reduced-depth mode |
| Caller deadline only, no quick-pass | Bounds wall-clock; smaller contract change | A budget-exhausted review on a small clean diff still returns no verdict; the common case stays slow | Rejected: does not satisfy the "cheaper quick-pass for high-confidence findings" acceptance criterion |
| Diff-scope classifier + caller deadline + quick-pass + progress, full review unchanged for escalations | Bounds time and gives small clean diffs a cheap verdict while escalating matched or ambiguous cases | Small QUICK_PASS diffs do not receive full threat-model analysis; adds two verdicts, a gate branch, and isolated-worker lifecycle | **Chosen**: smallest bounded reduction in analysis depth that meets all three acceptance criteria |

### Trade-offs

The quick-pass pattern set is deliberately the existing BLOCKED-trigger set, not a new, broader set. This keeps the quick scan honest: it asserts only "none of the things that already force a BLOCK are present". Pattern matches and ambiguity go to full review. A small clean diff can clear without full threat-model analysis, which is the accepted trade-off. The classifier thresholds (5 files / 200 lines for small) are a tuning surface; callers can override them upward, and the defaults match the issue's four-file evidence.

## Consequences

### Positive

- A small four-file hook diff gets a bounded verdict (QUICK_PASS or NEEDS_DEEP_REVIEW) within 30 seconds, or an explicit `needs_deeper_pass` signal. PR autofix stops stalling on the common case.
- PR automation can request a high-confidence quick review without waiting for a full deep audit (acceptance criterion 2).
- The orchestrator gets a progress signal before the two-minute mark and can tell a working review from a wedged one (acceptance criterion 3).
- The proposed budget-exhaustion path is structured (`budget_exceeded` +
  `needs_deeper_pass`) and never clears the gate.

### Negative

- Two new verdicts and a new gate branch widen the verdict taxonomy the orchestrator must understand. Mitigated by keeping the full-review terminal verdicts unchanged and making the new verdicts strictly non-clearing except QUICK_PASS-on-small.
- The classifier thresholds are a new tuning surface that can be mis-set. Mitigated by caller override and by failing toward the full review (any doubt routes to NEEDS_DEEP_REVIEW).
- An operator can set `SECURITY_REVIEW_BUDGET_MS` below a tier default and force repeated `budget_exceeded` results. The implementation must surface the configured budget and outcome; this ADR defines no hidden minimum.
- The canonical-source change to `security.shared.md` requires re-syncing the skill projection and the Copilot mirrors in the same change set (canonical-source-mirror rule).

### Neutral

- The full threat-model protocol is unchanged for medium, large, and extra-large diffs and for any quick-pass that detects a pattern. A small diff with a clean QUICK_PASS does not run that protocol; this is the accepted reduction stated above.
- `SECURITY_REVIEW_BUDGET_MS` is local to the proposed security-review
  implementation. ADR-068 defines no corresponding dispatcher environment
  variable.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `templates/agents/security.shared.md` | Direct (canonical source) | Add quick-pass mode, classifier reference, two verdicts, budget and progress contract; extend PIV gate to consume new verdicts | High (security-sensitive contract; security-agent review required) |
| `.claude/skills/security-review/SKILL.md` | Direct (projection) | Re-sync from canonical: project quick-pass content and the QUICK_PASS / NEEDS_DEEP_REVIEW verdicts; keep the existing IDENTIFY/OK/ESCALATE divergence note accurate | Medium |
| Copilot instruction mirrors (`.github/instructions/`, `src/copilot-cli/instructions/`) | Indirect | Regenerate from templates after the canonical change | Medium |
| Orchestrator PIV verdict gate | Direct | Branch on QUICK_PASS (clears only for `small`), NEEDS_DEEP_REVIEW and `budget_exceeded` (never clear) | High (gate is the security boundary) |
| `.agents/governance/SECURITY-REVIEW-PROTOCOL.md` | Direct | Document the quick-pass mode and the budget-exhaustion handling in the review workflow | Medium |
| Implementation scripts (classifier, isolated worker, deadline owner) | New | New Python modules with pytest coverage; 100% coverage per `AGENTS.md` security floor; no in-process kill | Medium |

## Implementation Notes

Phased, each phase independently shippable and reversible, ordered so the cheapest and least risky lands first:

1. **Diff-scope classifier.** `classify_diff_scope(file_count, lines_changed) -> tier` as a pure function with parametrized pytest cases on every tier boundary (4/200, 5/200, 6/201, etc.). No behavior change to review depth yet; classifier output is logged only.
2. **Caller-enforced deadline.** `SECURITY_REVIEW_BUDGET_MS` plus
   `--budget-ms`, enforced by the orchestrator or an isolated worker process.
   On exhaustion, terminate the worker and emit `budget_exceeded` plus
   `needs_deeper_pass`. Do not add `SIGALRM` or a watchdog thread that pretends
   to kill in-process work.
3. **Quick-pass mode and verdicts.** Scan the BLOCKED-trigger pattern set only; skip the threat-model protocol; return QUICK_PASS or NEEDS_DEEP_REVIEW. Extend the PIV gate. Coverage: positive (clean small diff -> QUICK_PASS), negative (planted CWE-78 -> NEEDS_DEEP_REVIEW), edge (ambiguous scope -> NEEDS_DEEP_REVIEW, incomplete diff missing changed files -> BLOCKED Cannot evaluate). Rolling this phase back requires removing the QUICK_PASS gate branch and treating existing QUICK_PASS verdicts as requiring full review before the next PR cycle.
4. **Progress reporting.** 30-second-interval stderr checkpoints with `elapsed_ms`, `remaining_ms`, `files_scanned`, `findings_count`. The small tier's first checkpoint coincides with its 30-second deadline, so it is not a reliable liveness signal there. Progress checkpoints provide useful liveness evidence for medium and larger tiers.

Each phase carries pos/neg/edge tests per `.agents/governance/TESTING-RIGOR.md`. The canonical change to `security.shared.md` and its projections land together in one change set per the canonical-source-mirror rule.

## Related Decisions

- ADR-068 (Consolidated Hook Dispatcher): records why unsafe in-process kill
  was rejected and why host-owned timeout metadata is not a reusable watchdog.
- ADR-066 (Hook Fail-Open Reconciliation) and ADR-071 (Plugin Hook Runtime Contract Verification): fail-closed precedent that `budget_exceeded` follows (never clears the gate).
- ADR-058 (Agent Eval Discipline): the `security` agent / `security-review` skill form-factor pairing this ADR extends.
- ADR-059 (PR-Review Completion Gate Dispatcher): structured-output dispatcher pattern the verdict consumer follows.
- ADR-002 (Agent Model Selection): the security agent runs `opus`; quick-pass mode does not change model selection.
- ADR-073 (Machine-Readable ADR Lifecycle Frontmatter): frontmatter schema this ADR adopts.

## References

- Issue #2617: bounded quick-pass mode request, with PR #2611 timing evidence and maintainer DEFER (comment 4726185340).
- `templates/agents/security.shared.md` lines 109 to 129, 298: threat-model protocol, verdict taxonomy, PIV gate.
- `.claude/skills/security-review/SKILL.md` (v0.1.1; v0.1.0 at decision time): inline projection and verdict divergence note.
- `.agents/architecture/ADR-068-consolidated-hook-dispatcher.md` Decision item
  4: no in-process watchdog; host owns dispatcher timeout.
- `.agents/governance/SECURITY-REVIEW-PROTOCOL.md`: review workflow.
- `.agents/governance/SECURITY-SEVERITY-CRITERIA.md`: severity thresholds (unchanged by this ADR).
- `.claude/rules/security.md`: security-agent review requirement and severity-threshold MUST-NOTs.
- `.claude/rules/canonical-source-mirror.md`: canonical-to-projection re-sync contract.
- `.agents/critique/ADR-074-debate-log.md`: 2026-07-19 six-agent review that
  closes the historical missing-review trail without asserting an earlier
  debate.
- CWE-22, CWE-77, CWE-78, CWE-798; ASI01 to ASI10: the quick-pass pattern set.
