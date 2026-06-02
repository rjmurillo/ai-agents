---
status: "proposed"
date: 2026-06-02
decision-makers: [architect]
consulted: [analyst, critic, independent-thinker, security, high-level-advisor]
informed: [implementer, qa, devops]
---

# ADR-066: Hook Fail-Open Reconciliation (Prevention-First, Fail-Closed-and-Loud by Default)

## Status

Proposed. Requires adr-review per `AGENTS.md` ("Any `ADR-*.md` ... create/edit fires adr-review"). Refs #2205, #2230, #2263, #2271.

## Context and Problem Statement

PR #2263 scrubbed launcher-level fail-open from the surfaces it owned and replaced it with a prevention-first, fail-closed-and-loud position. It deliberately did NOT touch the pre-existing, repo-wide "hook runtime errors are fail-open" convention because that wholesale change is itself a governance change and needed its own ADR. Issue #2271 tracks that audit.

The analyst inventory (issue #2271 comment 4604311175, also saved as `/tmp/2271-inventory.md`) classified every fail-open assertion in the repository into three buckets:

- **Class (a)** customer-facing hook that must fail closed and loud (7 surfaces).
- **Class (b)** genuinely-optional advisory hook where degradation is acceptable (9 surfaces).
- **Class (c)** diagnostic prose describing the #2205 incident or historical retro (4 surfaces).

The status quo has the default backwards. ADR-008, ADR-033, ADR-035 codify "exit 1 = hook error = fail-open" as the standard. ADR-062 (LSP-first) calls fail-open "the repo's universal fail-open convention" and treats fail-closed as a "deadlock." `.claude/rules/release-it.md` has a "Graceful Degradation Over Hard Failure" section that hook authors cite as the warrant for launcher fail-open even though the section is scoped to user-facing latency, not governance gates. The reference implementation `.claude/skills/memory/scripts/invoke_memory_cross_reference.py` explicitly says "Always exit 0 (fail-open for hooks)" and is the canonical pattern others copy.

The #2205 incident demonstrated the cost. A launcher path bug wedged customer environments for 33 days across v0.3.0 to v0.5.6 because the in-script fail-open shim never ran (the launcher itself failed before the script started). The fail-open default did not protect the customer; it just delayed detection.

The Serena memory `feedback-generated-artifact-runtime-verification.md` already records this lesson. The other Serena hits (`pr-review/cursor-bot-review-patterns.md`, `implementation/implementation-007-pr1989-recursive-failure-learnings.md`, `architecture/architecture-observations.md`) reference fail-open as a known anti-pattern, not as a recommended default. No live Serena memory advocates launcher fail-open as policy.

This ADR reconciles the governance surfaces so the default flips: **prevention first, fail closed and loud, with a narrow enumerated carve-out for genuinely-optional advisory hooks that must each carry an inline justification.**

## Decision Drivers

1. Customer-harm bound. A silent exit 0 disables the hook and looks like success. The #2205 incident showed this is the dominant failure mode.
2. Detectability. A loud failure gets fixed. A silent fail-open accumulates dead hooks no one knows are dead.
3. Auditability. Today every fail-open is locally defensible ("graceful degradation"). The aggregate is an undetectable degradation surface. An enumerated carve-out list with inline justification makes drift visible to lint.
4. Backward compatibility. Genuinely-optional advisory hooks (lint noise, optional scans) must keep working. The wholesale flip would block legitimate degradation.
5. Lifecycle-hook host semantics. Claude / Copilot CLI hosts use exit codes the host interprets. The new default must not introduce new exit codes for non-blocking hooks where the host already ignores them.

## Considered Options

1. **Status quo**: keep "fail-open is the universal default; specific gates carve themselves out by exiting non-zero."
2. **Wholesale flip**: every hook fails closed and loud; no carve-outs.
3. **Default-flip with enumerated class (b) carve-out and lintable contract** (chosen).

## Decision Outcome

Chosen option: **3 - default-flip with enumerated class (b) carve-out and lintable contract**, because the analyst inventory already enumerates which surfaces are genuinely optional, the #2205 incident proved the wholesale-default-fail-open stance is customer-harming, and a fully wholesale flip would block legitimate lint/advisory degradation without buying additional safety.

### Concretely this means

#### D1. Hook failure-mode policy (replaces ADR-008 "runtime and I/O errors during hook execution are fail-open")

The default for ANY customer-facing hook (class (a)) is:

- **Prevent the bad artifact at generation time.** This is the #2263 stance, restated.
- **If a runtime error escapes**, fail closed and loud: exit non-zero with a useful stderr message naming the hook, the failure, and the recovery path. The host MUST surface the error to the user.
- **No silent exit 0.** A bare `try/except: pass`, `|| true`, or `exit 0` in a class (a) failure path is a violation.

Class (b) hooks (lint noise, optional advisory scans, infrastructure-error backstops where the work is truly enrichment) MAY fail open, but ONLY if:

1. The hook is listed in the **class (b) carve-out registry** (see D5 below).
2. The failure path emits a stderr WARN naming the hook, the failure, and the ADR-066 justification class.
3. The failure path carries an inline comment of the form:

   ```python
   # ADR-066 class (b): <one-line justification>. See ADR-066.
   ```

#### D2. Exit-code reconciliation (ADR-008 / ADR-033 / ADR-035)

The canonical exit-code table is updated as follows:

| Exit Code | Class (a) hooks (default) | Class (b) hooks (carve-out) | Blocking hooks (PreToolUse policy gates) |
|-----------|---------------------------|-----------------------------|------------------------------------------|
| 0 | Success, hook ran and asserted no violation | Success OR known-acceptable degradation (with WARN to stderr) | Allow action |
| 1 | **Hook runtime error, fail closed and loud (was: fail-open)** | Hook runtime error, fail open with WARN to stderr | Logic error, fail closed |
| 2 | Configuration / bootstrap failure (unchanged, ADR-047) | Configuration / bootstrap failure (unchanged) | **Block action immediately** (unchanged) |
| 3 | External dependency unavailable, fail closed (NEW lane) | External dependency unavailable, fail open with WARN (justifies class (b)) | External dependency, fall back per gate policy |

Notes:

- **New exit-code lane**: exit 3 = external/transient unavailability. Today ADR-035 overloads exit 1 for "hook error (fail-open)." Splitting "logic error" (exit 1) from "external unavailable" (exit 3) lets class (b) hooks degrade on exit 3 without masking real logic bugs on exit 1. This answers the analyst's open question.
- Non-blocking host hooks (Claude `SessionStart`, `PostToolUse`, `Stop`, `PreCompact`, etc.) still MUST always exit 0 *to the host* because the host ignores non-zero and suppresses stdout context injection. This is a host constraint, not a policy. The hook MUST still write the structured error to stderr and to `.agents/.hook-state/` so the failure is visible. ADR-035 keeps the "non-blocking hooks exit 0" host rule, but reframes it: the exit-0 is to satisfy the host contract, NOT to silently swallow the failure.
- Blocking hooks (PreToolUse policy gates) MUST use exit 2 to block. Exit 1 in a blocking hook means logic error and the gate fails closed. This is the existing #2263 stance, restated.

#### D3. ADR-062 (LSP-first) reconciliation

ADR-062's "universal fail-open convention" framing is incorrect after this ADR. ADR-062 keeps its fail-open behavior, but it is reclassified as **class (b) with the wedge-on-compaction rationale already documented in its body** (the LSP probe-then-allow design at the tool-call boundary, plus `LSP_GATE_MODE` kill switch). The ADR-062 prose MUST be amended to:

- Replace "the repo's universal fail-open convention" with "the class (b) carve-out for this gate, per ADR-066."
- Remove the "fail-closed is a deadlock" framing as a general statement; that argument is specific to the LSP probe at the tool-call boundary, not general policy.
- Add an explicit `# ADR-066 class (b): LSP probe at tool-call boundary; wedge-on-compaction risk justifies fail-open. See ADR-066.` inline at each fail-open site.

ADR-062's existing kill switch, recovery message, and audit log meet the class (b) bar. No behavior change.

#### D4. `.claude/rules/release-it.md` reconciliation

The "Graceful Degradation Over Hard Failure" section is scoped to **user-facing integration points** (latency, multi-service response composition). It is NOT general warrant for launcher/hook fail-open. The section MUST be amended to:

- Add a leading sentence: "This section applies to user-facing integration points where a degraded response is meaningful to the caller. It does NOT apply to governance hooks, lifecycle hooks, or any code path whose job is to assert an invariant. For hook failure semantics see ADR-066."
- Add a cross-reference at the existing "Memory systems ... must degrade to a documented fallback, not silently swallow context loss" bullet pointing to ADR-066 D5 carve-out rules.

Hook authors who cite release-it.md as the warrant for launcher fail-open are reading it out of scope. The scoped amendment closes that loophole.

#### D5. Class (a) flip plan and class (b) carve-out registry

The analyst inventory's class (a) list is binding. The implementer flip PR (closes #2271) MUST flip each of these to fail-closed-and-loud:

| # | Surface | Lines | Action |
|---|---------|-------|--------|
| a1 | `.agents/architecture/ADR-008-protocol-automation-lifecycle-hooks.md` | 114, 116, 150 | Amend prose per D1/D2. |
| a2 | `.agents/architecture/ADR-033-routing-level-enforcement-gates.md` | 106, 111-115, 222-239, 278, 297, 308-312 | Update exit-code table per D2; remove "downgrade exit 2 -> exit 0 to make a gate advisory" recommendation. |
| a3 | `.agents/architecture/ADR-035-exit-code-standardization.md` | 369-373, 388, 429, 436 | Update table per D2; add the exit-3 lane. |
| a4 | `.agents/architecture/ADR-062-conditional-lsp-first-enforcement.md` | per D3 | Reclass to class (b); amend prose. |
| a5 | `.agents/architecture/ADR-062-memory-first-gate-spec-pipeline.md` | 119 | Reclass Serena-first fallback as class (b) and add inline justification. |
| a6 | `.claude/rules/release-it.md` | 23, 179, 219, 233 | Amend per D4. |
| a7 | `.agents/skills/memory/scripts/invoke_memory_cross_reference.py` and `.claude/skills/memory/scripts/invoke_memory_cross_reference.py` | 10-23, 158 | **Flip to class (a) fail-closed-and-loud.** Rewrite the module docstring and the `# Always exit 0 (fail-open for hooks)` block. Memory cross-reference at commit/PR time is customer-facing governance (it surfaces the memories that govern the change). On runtime error, exit 1 with a stderr message naming the hook, the missing memories, and how to bypass. The host (git hook) WILL surface this and block the commit; that is correct. |

The class (b) carve-out registry (initially):

- b1 PR-iteration-cost lint hooks (markdownlint, em/en dash). Justification: style lint noise, not governance; loud WARN to stderr; regression test exists (`test_markdownlint_guard.py`, `test_push_guard_base.py`).
- b2 commit-msg infrastructure-miss path. Justification: missing message file path is an infrastructure miss, not a violation.
- b3 `command -v python3` bootstrap-style guards. Justification: comparable to ADR-008's existing bootstrap carve-out.
- b4 EARS template "graceful degradation" checkbox. Action: rewrite the checkbox to point at ADR-066's rubric (template-only; no runtime effect).
- b5, b6 educational stability references (`security-defense-in-depth.md`, `slo-design-patterns.md`). Action: add cross-reference to ADR-066 so authors don't read them as launcher guidance.
- b7 CodeQL optional advisory scan. Justification: explicitly optional; loud WARN already present.
- b8 Skill-authoring guidance about graceful degradation in scripts. Action: add cross-reference to ADR-066.
- b9 M5 bot-cascade hook (`REQ-013`). Already aligned; cited as the **reference pattern** for class (a) flips. The `test_phase_5c_no_fail_open_on_reviews` regression test is the model for D6 below.
- ADR-062 LSP gate (re-listed here for completeness; see D3).

Every class (b) entry MUST carry the inline `# ADR-066 class (b): ...` comment. The registry lives in this ADR; the lint contract in D6 enforces co-location.

#### D6. Lintable contract (answers analyst open question)

This ADR mandates a lintable test contract analogous to `test_phase_5c_no_fail_open_on_reviews`:

- A repo-wide test (location: `tests/governance/test_adr_066_no_fail_open_outside_carve_out.py`) asserts that no file in `.claude/skills/`, `.claude/hooks/`, `src/copilot-cli/`, `.agents/skills/`, or `build/scripts/` contains any of:

  - bare `try/except: pass` in a failure path,
  - `|| true` after a hook invocation,
  - `exit 0` in a failure branch,
  - `return 0` annotated `fail-open`,

  ...UNLESS the file path is in the class (b) registry above OR the line carries the inline `ADR-066 class (b): <justification>` marker comment within 5 lines before the suppression.

- Class (b) registry is parsed from this ADR's D5 table at test time so updates to the ADR auto-update the lint.

- The test runs in CI as a BLOCKING gate (exit non-zero on violation). Implementer PR adds the test alongside the class (a) flips.

#### D7. Scope exclusion

`.claude/skills/gstack/**` is third-party vendored code. ADR-066 does NOT govern gstack. The lint contract in D6 explicitly excludes `.claude/skills/gstack/`. If gstack ever moves into first-party scope, this exclusion gets removed in the ADR that absorbs gstack into the repo's governance.

### Consequences

Good:

- Customer-harm bound: the #2205 failure mode (silent launcher exit 0 = wedged customer for 33 days) is structurally prevented for class (a) surfaces.
- Auditability: the class (b) registry plus the inline marker plus the D6 lint contract make every fail-open in the tree visible and justifiable.
- Detectability: real runtime errors in class (a) hooks surface to the user immediately and get fixed instead of accumulating as silent dead-weight.
- No exit-code overload: the new exit-3 lane separates "external unavailable" from "logic error" so class (b) hooks can degrade on transience without masking bugs.

Bad:

- Implementer flip PR is non-trivial (7 class (a) surfaces, plus new exit-3 plumbing in ADR-035, plus the D6 test).
- Some advisory hooks that today silently degrade will start emitting WARN to stderr. This is loud-by-design but will produce visible noise the first release after the flip.
- The `invoke_memory_cross_reference.py` flip means a runtime error in that script (today silent) will block commits. That is the correct behavior per #2263, but it raises the bar on that script's robustness; implementer must add a kill switch (`SKIP_MEMORY_CROSS_REF=1` environment variable) for emergency bypass during the rollout window.

### Confirmation

Implementation compliance is confirmed by:

1. The D6 lint test (`test_adr_066_no_fail_open_outside_carve_out.py`) running green in CI.
2. adr-review consensus on this ADR (D&C or Accept from all 6 agents, max 10 rounds).
3. The implementer flip PR closes #2271 and references this ADR in its body.
4. The class (b) registry in this ADR matches the actual files in the tree (the D6 test asserts this).

## Pros and Cons of the Options

### Option 1: Status quo

- Good, because no code/prose changes; backward compatible.
- Good, because each fail-open is locally defensible at the point of decision.
- Bad, because the aggregate is undetectable degradation surface (the #2205 failure mode).
- Bad, because hook authors cite `release-it.md` "Graceful Degradation" out of scope as warrant for launcher fail-open.
- Bad, because the maintainer's standing position (per #2263) is already the inverse of this option's default.

### Option 2: Wholesale flip (every hook fails closed and loud)

- Good, because there is no ambiguity and no carve-out registry to maintain.
- Good, because every silent dead hook becomes loud immediately.
- Bad, because legitimate advisory paths (lint noise, optional scans) start blocking pushes; the noise floor breaks workflows that aren't customer-facing governance.
- Bad, because ADR-062's wedge-on-compaction risk is real; a wholesale flip would deadlock the LSP gate without the existing recovery design.

### Option 3 (chosen): Default-flip with enumerated class (b) carve-out and lintable contract

- Good, because the default is now correct (class (a) is the dominant surface and the #2205 failure mode).
- Good, because the carve-out is enumerated, inline-justified, and lint-enforced. Drift is detectable.
- Good, because ADR-062's existing class (b) design (probe + kill switch + recovery message) survives unchanged.
- Good, because the new exit-3 lane lets class (b) degrade on transience without overloading exit 1.
- Neutral, because the implementer flip PR is non-trivial.
- Bad, because the class (b) registry needs maintenance discipline (mitigated by the D6 lint asserting registry-to-tree parity).

## More Information

- Refs #2205 (customer wedge incident; the failure-mode evidence)
- Refs #2230 (launcher fail-open remediation; closed addressed-by-prevention)
- Refs #2263 (governance scrub; established prevention-first, fail-closed-and-loud stance)
- Refs #2271 (this audit; closed by the implementer flip PR, NOT by this ADR)
- Analyst inventory: <https://github.com/rjmurillo/ai-agents/issues/2271#issuecomment-4604311175>
- Serena memory `feedback-generated-artifact-runtime-verification.md` is the contemporaneous incident record.
- `.serena/memories/` grep result: no live Serena memory advocates launcher fail-open as policy. Four hits exist; all describe fail-open as a known anti-pattern or incident, not as a recommended default. This addresses the analyst's open question.

Realization plan: this ADR lands. adr-review runs. On consensus, status flips to "accepted." Implementer opens the flip PR per D5, which closes #2271 and adds the D6 test. ADR-008 / ADR-033 / ADR-035 / ADR-062 / `release-it.md` get amended in that same PR (or in tightly-scoped follow-ups, each referencing this ADR). After the flip, review this ADR at the next governance audit (or when a new exit-code lane is proposed).
