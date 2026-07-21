# Critique: ADR-068 + ADR-071 Amendment (2026-07-19, Copilot 1.0.72-1)

## Verdict

**APPROVED_WITH_CONCERNS** : Confidence: HIGH

## Summary

Both ADRs are well-structured, internally consistent on numeric claims, and
properly grounded in official sources and versioned probes. The amendments
correct stale 1.0.57-era assumptions without overreaching. Three findings
require resolution before merge: an event-name overclaim that conflates
native/target events, undocumented `cwd` field semantics for plugin hooks,
and an INCONCLUSIVE probe that is shipped without explicit risk acceptance.

## Scores by Axis

| Axis | Score | Notes |
|------|-------|-------|
| Completeness | 4/5 | All major decisions have acceptance criteria; cwd semantics and blast-radius quantification are absent |
| Alignment | 5/5 | Amendments serve the stated objectives with no scope creep |
| Feasibility | 5/5 | Implementation already shipped and independently verifiable via committed tests |
| Risk Coverage | 3/5 | Host-timeout bypass documented qualitatively but not quantified; PreCompact inconclusive probe shipped without explicit risk acceptance |
| Testability | 4/5 | Runtime subprocess tests cover all dispatched modes; SessionEnd and PostToolUseFailure remap entries have zero test coverage |
| Traceability | 5/5 | Every claim links to code file, probe evidence, or official docs with pinned commits |

## Reasoning

### Q1: What breaks if this plan is wrong?

If the PermissionRequest `ask` suppression is wrong and Copilot actually accepts
a `behavior: "ask"` value, the plugin will silently suppress a user-facing
"ask the user" prompt that the original Claude guard intended. The probe
evidence section 5 confirms no valid `ask` behavior exists, so this risk is
low. If the PreCompact event never fires on the measured host, a dead
registration wastes one hooks.json entry and its artifacts (low impact). If the
`cwd: "."` field means something different for plugins than for repository hooks
and a future hook uses relative paths, that hook breaks at runtime.

### Q2: What assumptions contradict project constraints?

ADR-068 Decision item 1 lists "agentStop" as a direct event, but the generator's
`copilot-cli.yaml` eventRemap does not include `agentStop` as a target. The
generator can never produce an `agentStop` entry, making the ADR claim
technically vacuous rather than wrong. This contradicts the ADR's own standard
of describing "the current generated tree."

### Q3: Strongest counterargument to the chosen approach?

A per-shim host registration with host-native matchers would avoid the 18-shim
serial execution risk entirely. Copilot 1.0.72-1 demonstrably suppresses
nonmatching spawns for PascalCase matchers. The ADR considered this (Alternative
"Keep one host entry per shim") but rejected it on cold-start cost. The
counterargument: with working host matchers, most spawns are already suppressed,
so the aggregate cold-start cost would be paid only for matching tools (Bash,
Write, Edit). A `git push` would spawn only the 9 push-specific guards, not 18.
The ADR's "repeated interpreter startup" rejection does not account for host
matcher filtering reducing the effective spawn count.

## Critical Findings

### 1. P0 : Event-name overclaim conflates native and generator target names

**What:** ADR-068 Decision item 1 states "Stop, agentStop, SubagentStop, and
subagentStop bypass consolidation." The `copilot-cli.yaml` eventRemap includes
only `Stop: Stop` and `SubagentStop: SubagentStop`. Native `agentStop` is not a
configured target event. The ADR presents four events as bypassing
consolidation, but only two can appear in the generated output.

**Where:** ADR-068:72 (Decision item 1), `copilot-cli.yaml`:60-68

**Impact:** A future reader implementing a new hook targeting `agentStop`
directly would be misled into thinking the generator handles it.

**Recommendation:** Rephrase to: "Stop and SubagentStop bypass consolidation.
The defensive code also excludes `agentStop` and `subagentStop` if they ever
appear as target events."

### 2. P1 : `cwd: "."` semantics undocumented for plugin hooks

**What:** Every generated hooks.json entry ships `"cwd": "."`. The
official-hook-contracts.md says the `cwd` field is "relative to the repository
root or absolute." But the original 1.0.57 probe measured `cwd = user's working
directory`. Neither ADR explicitly states: (a) which interpretation applies to
plugin hooks vs repository hooks, (b) whether the generated `cwd: "."` is
load-bearing or vestigial, or (c) whether the current host version changed the
runtime cwd behavior.

**Where:** ADR-071:46-47 (amendment text referencing "cwd is
repository-relative or absolute"), `src/copilot-cli/hooks/hooks.json` every
entry, `official-hook-contracts.md`:59-61

**Impact:** If a future hook script adds relative-path file operations expecting
cwd=repo-root per docs, but the host still delivers cwd=user-dir (as the 1.0.57
probe showed), the script breaks at runtime. The runtime-contract test
(`test_copilot_dispatcher_artifact.py`) explicitly sets env vars but never
exercises cwd-relative resolution.

**Recommendation:** Add a clarifying note in ADR-071's Verified Runtime Contract
section: "The `cwd: '.'` field in generated hooks.json is NOT relied upon for
script execution (all scripts use absolute plugin-root anchoring). Its runtime
effect for plugin hooks has not been probed on 1.0.72-1 and remains
DOCS-SAY-only."

### 3. P1 : PreCompact shipped as generated observe event despite INCONCLUSIVE probe

**What:** ADR-068 Implementation Note 8 says "PreCompact is a supported
generated observe event." probe-evidence.md section 5 says "the probe did not
reach its trigger. The probe result is INCONCLUSIVE." The event was shipped
based solely on DOCS-SAY evidence.

**Where:** ADR-068:279 (Implementation Note 8),
`probe-evidence.md`:136-139, `src/copilot-cli/hooks/hooks.json`:27-34

**Impact:** Low. A non-firing event is dead code, not a runtime failure. But the
ADR does not acknowledge the probe gap for this specific event. A future reader
auditing the ADR may assume PreCompact was probe-verified.

**Recommendation:** Amend ADR-068 Implementation Note 8 to: "PreCompact is
generated based on DOCS-SAY evidence. Its runtime dispatch is EMPIRICALLY
INCONCLUSIVE (probe-evidence.md section 5). Risk: dead registration if the event
never fires for this plugin's trigger conditions."

### 4. P1 : Host-timeout blast radius is qualitative, not quantified

**What:** ADR-068 says "One hung consolidated `PreToolUse` dispatcher can be
killed before later guards run, allowing the tool and bypassing all guards that
did not complete." The current tree has 18 PreToolUse shims. "All guards" = up
to 17 bypassed by one hung shim. The ADR does not state this number or its
growth trend.

**Where:** ADR-068:161-165 (Why the In-Process Kill Was Rejected),
`PreToolUse/_manifest.json`:4-23

**Impact:** A reviewer approving a 19th guard would not realize they are
increasing the worst-case bypass count. The blast radius grows silently with
every added PreToolUse guard.

**Recommendation:** Add to Consequences/Negative: "The current PreToolUse tree
registers 18 shims. In the worst case, 17 guards can be bypassed if shim 1
hangs until the host kills the process. Each added PreToolUse guard increases
this count by 1."

### 5. P2 : Matcher probe version (1.0.71) differs from contract base (1.0.72-1)

**What:** `generate_dispatcher.py`:275 says matcher filtering was "Verified
empirically on Copilot CLI 1.0.71 (issue #3075 probe)." ADR-071's amendment is
scoped to "Copilot CLI 1.0.72-1." The matcher optimization relies on a probe
done one minor version earlier.

**Where:** `build/scripts/generate_dispatcher.py`:275,
ADR-071:92 (amendment header)

**Impact:** Low. Official docs confirm matchers work. But if a regression
existed in 1.0.72-1 specifically for matcher filtering, the #3075 probe would
not have caught it.

**Recommendation:** Note in ADR-071 amendment: "Host matcher suppression was
probed on 1.0.71 (#3075). The 1.0.72-1 probes did not re-verify host-side
matcher suppression. Official docs confirm matcher support across versions."

## Zimmermann Q1-Q7

| Q | Answer |
|---|--------|
| Q1: What is the decision? | Consolidate per-event dispatchers, keep Stop/SubagentStop direct, add PermissionRequest translation, document 1.0.72-1 contract corrections |
| Q2: Why was it made? | Historical spawn incident (#2295), measured cold-start cost, and missing PermissionRequest output adapter |
| Q3: What alternatives were considered? | Per-shim entries, host-only matchers, in-process watchdog, child processes, persistent daemon : all explicitly rejected with rationale |
| Q4: What is the scope? | Generated Copilot CLI plugin artifacts only; Claude Code unchanged |
| Q5: Who decided? | Six-agent adr-review panel (3 Accept, 3 Disagree-and-Commit, 0 Block) |
| Q6: When? | 2026-06-02 (original), 2026-07-19 (amendment) |
| Q7: Revisit trigger? | Host CLI version change, new event semantics, or plugin-root variable removal |

## Strengths

1. **Exceptional source discipline.** Every empirical claim links to a specific
   probe session, versioned CLI, and curated evidence file. DOCS-SAY vs
   EMPIRICAL tagging is consistently applied.

2. **Arithmetic independently verified.** 33 source registrations
   (1+2+1+18+5+2+4), 8 host entries (6 dispatchers + 2 Stop), 75.8% reduction,
   and every per-event `timeoutSec` sum matches the manifest exactly.

3. **Fail-closed defaults throughout.** Missing shim = exit 2 in gate mode.
   Malformed manifest = exit 2. Unknown mode = exit 2. Boolean timeout = exit 2.
   The code enforces ADR-066 at every decision point.

4. **PermissionRequest `ask` suppression is fully grounded.** Official docs say
   `behavior` accepts only `allow` or `deny`. Probe confirms Claude decision
   shape is ignored. Code emits `None` for `ask`. Tests verify empty stdout.

5. **Honest about what was NOT tested.** ADR-071 explicitly states the committed
   E2E harness was not run for 1.0.72-1 observations and that PreCompact is
   INCONCLUSIVE.

## Weaknesses / Gaps

1. The "agentStop" naming conflation (Finding 1) will mislead future
   contributors about what the generator actually produces.

2. The `cwd: "."` field ships in every entry without any ADR explaining its
   purpose or verifying its runtime effect for plugins on the current host.

3. No test exercises the boundary between "last registered event today" and
   "first new event tomorrow" : adding PostToolUseFailure or SessionEnd hooks
   would break `test_safe_events_use_one_dispatcher_entry` without any test
   guidance on what to update.

4. The blast-radius growth of serial PreToolUse execution is not surfaced as a
   metric or warning.

## Scope Concerns

- The amendment stays within its declared scope (contract corrections for
  1.0.72-1). No scope creep detected.
- The coupling between ADR-068 and ADR-071 is well-managed: ADR-068 owns
  the dispatcher policy, ADR-071 owns the empirical contract and gates.

## Open Questions for Authors

1. Was the `cwd` field's runtime behavior re-probed on 1.0.72-1 for plugin
   hooks specifically? If not, should the amendment explicitly record this gap?

2. Should the blast-radius count (currently 17) be surfaced as a CI metric that
   warns when it exceeds a threshold?

3. The PostToolUse dispatcher has no host matcher (because
   `mcp__serena__write_memory` is not in `_KNOWN_CLAUDE_TOOLS`). This means the
   PostToolUse dispatcher fires on EVERY post-tool-use event, even when neither
   shim's matcher matches. Is the in-process self-filtering cost acceptable for
   the plugin's current usage pattern?

## Priority Table

| ID | Severity | Finding | Blocking? |
|----|----------|---------|-----------|
| 1 | P0 | agentStop overclaim in Decision item 1 | No (misleading, not incorrect policy) |
| 2 | P1 | cwd: "." semantics undocumented for plugins | No (anchoring makes it benign) |
| 3 | P1 | PreCompact INCONCLUSIVE shipped without explicit acceptance | No (low-impact dead registration) |
| 4 | P1 | Blast radius not quantified | No (qualitative description present) |
| 5 | P2 | Matcher probe version mismatch | No (docs confirm behavior) |

## Approval Conditions

Upgrade to unconditional APPROVED when:

1. Finding 1 is corrected: Decision item 1 text distinguishes configured target
   events (Stop, SubagentStop) from defensive code coverage (agentStop,
   subagentStop).
2. Finding 3 is acknowledged: Implementation Note 8 adds "DOCS-SAY only,
   empirically INCONCLUSIVE" qualifier.

Findings 2, 4, 5 are concerns that should be addressed but are not blocking.

## Recommendation

Amend ADR-068 Decision item 1 to distinguish "these events are configured and
direct" from "these native names are defensively excluded" : this is a
three-sentence edit that clears the P0 finding and unblocks merge.

---

*Reviewer: critic (adversarial, fresh-context)*
*Date: 2026-07-19*
*Confidence: HIGH*
*Repository: rjmurillo/ai-agents (branch fix/copilot-hook-contract)*
