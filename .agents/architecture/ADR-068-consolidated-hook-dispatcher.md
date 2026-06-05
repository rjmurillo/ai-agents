# ADR-068: Consolidated Per-Event Hook Dispatcher

## Status

Proposed

## Date

2026-06-02

## Context

Issue #2295 documents intermittent false-positive `preToolUse` denials on
Copilot CLI. Three of 197 `preToolUse` invocations in a single session were
killed with `Hook command timed out after 2-3 seconds`; the host then failed
the tool closed with `Denied by preToolUse hook (hook errored)`. The 194
successful invocations in the same session prove the shim logic and the #2290
payload-casing fix (PR #2293) work. The defect is latency, not correctness.

The root cause is a per-tool-call process-spawn storm:

1. Copilot CLI does not honor a per-hook `matcher` field in `hooks.json`. The
   host runs every registered `PreToolUse` entry on every tool call. The
   matcher-shim pattern from ADR-061's alternative B (deterministic full-tree
   regeneration) self-filters in-process, but only AFTER paying the Python
   interpreter cold-start cost.
2. The current generator (`build/scripts/generate_hooks.py`) writes one shim
   per matcher. The installed `project-toolkit` plugin emits 40 `PreToolUse`
   shim files.
3. Measured cold-start cost on Windows (`py -3 -u <shim>`) is ~246 ms per
   invocation. Sequential aggregate is ~8.7 s. Copilot's observed kill
   threshold is 2-3 s, which `timeoutSec: 5` in `hooks.json` does not raise:
   the budget is host-controlled, not generator-controlled.
4. When the budget is exceeded, Copilot reports `hook errored` and fails
   closed per ADR-071 Decision item 5. The fail-closed policy is correct.
   The defect is that a HEALTHY hook is killed by our own dispatch overhead,
   manufacturing a false `errored` signal.

This is distinct from #2290 (payload casing, fixed) and from #2205 / ADR-071
(launcher cwd, fixed). Both prior fixes corrected correctness defects. This
ADR addresses a performance defect that turns ADR-071's fail-closed policy
into a denial-of-service against benign tool calls.

## Decision

Generate ONE dispatcher entry per `(plugin, event)` pair instead of one
entry per `(plugin, event, matcher)` triple. The single dispatcher reads
stdin once, classifies the payload against every registered matcher in
memory, and invokes matched guards in-process. Source guards remain
authored as standalone scripts under `.claude/hooks/<Event>/`; generated
dispatchers execute each matched guard in `__main__` context using
`runpy.run_path(...)` so existing script semantics are preserved.

1. **Single process per event.** A `PreToolUse` tool call spawns the Python
   interpreter exactly once, regardless of guard count. Cold-start cost is
   paid once per event, not N times.
2. **In-process matcher dispatch.** The dispatcher embeds the matcher
   grammar from `classify_matcher` and walks the registered guards. Guards
   whose matchers do not fire are skipped without I/O. The grammar
   (`regex`, `tool-glob`, `bare`) is preserved verbatim from ADR-061's
   surviving classifier; this ADR does not modify it.
3. **Fail-closed preserved.** A guard that exits non-zero or raises ends
   the dispatcher with the same exit code, surfacing through Copilot's
   existing `hook errored` path. The dispatcher itself fails closed (exit
   2) on malformed stdin, missing `tool_name`, or guard import failure.
   ADR-071 Decision item 5 (prevention plus loud failure) is unchanged.
4. **Bounded shared budget.** The dispatcher enforces a per-event
   wall-clock cap (default 1500 ms, configurable via
   `COPILOT_HOOK_DISPATCH_BUDGET_MS`). On budget exhaustion it fails
   closed with a structured `budget_exceeded` reason so the failure is
   distinguishable from a guard rejection.
5. **No daemon.** The dispatcher is short-lived. ADR-071's host-launcher
   contract (cwd, exit code semantics) is unchanged. No persistent IPC.
6. **Regenerated artifacts are authoritative.** Per
   `.claude/rules/generated-artifacts.md` and ADR-061's CI drift gate, the
   committed `src/copilot-cli/hooks/` tree is regenerated deterministically
   and `git diff --exit-code` runs in CI. The dispatcher file format must
   round-trip identically on repeat generation.

## Prior Art Investigation

### What Currently Exists

- **Pattern**: One shim file per `(event, matcher, source-script)` triple.
  Introduced by REQ-003-007 and re-affirmed in ADR-061's alternative B.
- **When introduced**: ADR-061 debate (2026-05-27) chose alternative B
  (deterministic full-tree regeneration with CI drift gate) over a
  delegate-shim refactor.
- **Original author and context**: The per-matcher-shim layout was chosen
  because Copilot CLI does not parse `matcher`, so the host needs N
  separate entries to surface per-matcher dispatch. The original cost model
  assumed shim count would stay small (ADR-061 cited three multi-matcher
  hooks; #2112 tracked the revisit threshold at eight).

### Historical Rationale

- **Why was it built this way?** Simplicity. One shim per matcher means
  each entry is self-contained, debuggable in isolation, and the matcher
  grammar can evolve without touching a shared dispatcher. ADR-061's
  withdrawal rationale explicitly rejected shared-body delegation as
  speculative abstraction.
- **What alternatives were considered?** ADR-061 weighed a delegate-shim
  refactor and rejected it on cost and drift grounds. No alternative
  considered shim COUNT as a performance variable.
- **What constraints drove the design?** Copilot CLI's lack of `matcher`
  support, the desire to keep shims trivially auditable, and ADR-008's
  preference for declarative over imperative configuration.

### Why Change Now

- **Has the original problem changed?** Yes. Shim count grew from three
  multi-matcher hooks (ADR-061's measurement) to forty `PreToolUse` entries
  in the shipped `project-toolkit` plugin. ADR-061's threshold (eight
  multi-matcher hooks) is exceeded by 5x. The ADR-061 follow-up issue
  #2112 anticipated this revisit.
- **Is there a better solution now?** Yes. A single dispatcher per event
  collapses N cold starts to one. The matcher grammar is small enough
  (~120 lines in `classify_matcher` plus the runtime mirror) to embed
  in-process without re-introducing the drift class ADR-061 worried about,
  because there is now ONE dispatcher per event (not N delegates).
- **What are the risks of change?** A dispatcher bug affects every guard
  for that event. Mitigation: the runtime-contract test from ADR-071
  already exists; extend it to cover the dispatcher's classify-and-route
  path with the full installed guard set.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Raise `timeoutSec` in `hooks.json` | Zero generator change | Copilot ignores it (killed at 2-3s when set to 5s); host-controlled budget | Rejected: ineffective |
| Speed up each shim body | Minimal architectural change | Python cold start (~200 ms) is a floor; 40 x floor still blows budget | Rejected: insufficient |
| Persistent hook daemon | Lowest steady-state latency | Process lifecycle, IPC, stale-state, security surface; violates ADR-071 launcher contract | Rejected: disproportionate; revisit only if single-dispatcher is insufficient |
| Consolidated per-event dispatcher | Collapses N spawns to 1; preserves ADR-071 fail-closed; preserves ADR-061 grammar; no new IPC | One dispatcher bug affects all guards for that event | **Chosen**: smallest change that fits within the host-imposed budget |

### Trade-offs

The per-shim-file isolation that ADR-061 valued is exchanged for a single
dispatcher per event. Debuggability is preserved because guards remain
authored as standalone scripts under `.claude/hooks/<Event>/`; they run
unchanged in Claude Code (which DOES honor `matcher` and dispatches one
guard per entry natively). The dispatcher is a Copilot-side adapter, not
a replacement for the canonical guard layout.

A dispatcher failure cascades to every guard for that event. ADR-071's
runtime-contract gate caught the launcher cwd defect that motivated it;
the same gate must be extended to cover dispatcher classification and
route correctness against the full installed guard set, not a sample.

## Consequences

### Positive

- Per-call hook wall-clock collapses from N x cold-start to 1 x cold-start
  plus in-memory matcher dispatch. With N=40 and cold start ~246 ms, the
  expected reduction is ~8.5 s -> ~300 ms, well inside Copilot's observed
  2-3 s budget with margin.
- Fail-closed semantics are preserved; the false-positive denials in
  issue #2295 disappear because healthy guards are no longer killed by
  dispatch overhead.
- ADR-061's drift gate (deterministic full-tree regeneration + CI diff)
  applies unchanged: the dispatcher file is regenerated from canonical
  on every run.
- Fewer files in `src/copilot-cli/hooks/<event>/`: one dispatcher per
  event instead of N shims. PR review surface shrinks.

### Negative

- A dispatcher defect (classifier mismatch, import failure) takes down
  every guard for that event. Mitigation: extend ADR-071's runtime-contract
  test to assert that, for every installed `(event, matcher, payload)`
  triple, the dispatcher routes to the same guard the per-shim layout would
  have invoked.
- The dispatcher executes matched guard scripts in-process via
  `runpy.run_path(..., run_name='__main__')` and must replay buffered stdin
  for each guard so canonical guard contracts remain unchanged. A bug in
  stdin replay or guard ordering can reject valid tool calls; mitigate with
  runtime-contract tests that cover multi-guard matches and payload replay.

### Neutral

- Claude Code behavior is unchanged. Claude Code parses `matcher` natively
  and continues to dispatch guards one-per-entry from the canonical
  `.claude/hooks/<Event>/` layout. The dispatcher is Copilot-only.
- ADR-035 exit-code standardization (0=ok, 1=logic, 2=config) carries
  through: the dispatcher's own errors are 2 (config / malformed input);
  guard exits propagate.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `build/scripts/generate_hooks.py` | Direct | Replace per-matcher shim emission with per-event dispatcher emission; execute matched guards via `runpy.run_path` in `__main__` context | High (load-bearing) |
| `src/copilot-cli/hooks/**` | Direct | Regenerated tree shape changes: one file per event instead of N | Medium (gated by ADR-061 CI drift check) |
| `tests/build_scripts/test_generate_hooks.py` | Direct | New parametrized tests covering dispatcher routing, fail-closed on malformed input, budget enforcement, and guard isolation | High (must cover full installed guard set, not samples) |
| `.agents/governance/GENERATOR-FILES.md` | Indirect | Document dispatcher pattern alongside per-matcher-shim history | Low |
| Claude Code `.claude/hooks/**` | None | Unchanged | None |
| ADR-071 runtime-contract test | Direct | Extend to assert dispatcher classification matches per-matcher reference for every installed payload | High |
| `.claude/rules/generated-artifacts.md` | Indirect | Add dispatcher runtime-test requirement to the runtime-contract test family | Low |

## Implementation Notes

The implementer agent should treat this as a generator-only change with a
test-first reproduction:

1. **Failing test first.** Add regression tests that construct a synthetic
   `hooks.json` with 40 `PreToolUse` entries and assert structural behavior:
   one generated Copilot dispatcher entry per event, matcher-equivalent
   routing, and deterministic guard order. Keep timing checks non-blocking
   (diagnostic benchmark only) to avoid CI flake from host variability.
2. **Generator change.** In `generate_hooks.py`, replace the per-matcher
   shim loop with a per-event dispatcher emission. The dispatcher template
   embeds `_shim_classify` (the runtime mirror of `classify_matcher`) once
   and dispatches a list of `(matcher, guard_module_path)` tuples.
3. **Guard execution model.** The dispatcher resolves guard paths under
   `${COPILOT_PLUGIN_ROOT}` with `${CLAUDE_PLUGIN_ROOT}` fallback (matching
   the existing per-shim resolution). Buffer stdin once at dispatcher entry,
   then replay the same payload before each matched guard. Execute each guard
   via `runpy.run_path(path, run_name='__main__')` so existing
   `if __name__ == '__main__'` paths run without requiring guard rewrites.
4. **Budget enforcement.** Use `signal.SIGALRM` on POSIX and a watchdog
   thread on Windows. On budget exhaustion the dispatcher exits 2 with a
   stderr line containing `budget_exceeded` for log parseability.
5. **Drift gate.** ADR-061's `git diff --exit-code src/copilot-cli/hooks/`
   step in CI catches non-deterministic dispatcher emission. The generator
   must sort guards by `(matcher_kind, matcher_pattern, source_path)`
   before emission.
6. **Runtime-contract extension.** Extend the ADR-071 runtime-contract test
   to enumerate every installed guard and assert that the dispatcher routes
   each registered matcher to the same guard the per-shim layout would
   have invoked. Use the matcher classification table as the oracle.

The implementer should NOT add a launcher-level fail-open; ADR-071 closed
that path explicitly. The dispatcher fails closed on all internal errors.

## Related Decisions

- ADR-061 (withdrawn): Hook matcher shims delegate pattern. Establishes the
  matcher grammar this ADR preserves and the drift-gate discipline this
  ADR inherits.
- ADR-071: Plugin hook runtime-contract verification. Establishes
  fail-closed semantics and the runtime-contract test family this ADR
  extends.
- ADR-035: Exit-code standardization. Governs the dispatcher's exit codes.
- ADR-008: Protocol automation lifecycle hooks. Governs hook event taxonomy.

## References

- Issue #2295: source defect (this ADR).
- Issue #2290 / PR #2293: payload casing fix. Distinct defect, verified
  working in the same session that surfaced #2295.
- Issue #2205: launcher cwd fix (ADR-071).
- Issue #2230: launcher-level fail-open proposal, closed
  addressed-by-prevention. Reaffirmed by this ADR's Decision item 3.
- Issue #2112: ADR-061 follow-up tracking when to revisit shared-body
  patterns. Threshold (eight multi-matcher hooks) exceeded.
- `.claude/rules/generated-artifacts.md`: runtime-contract test
  requirement.
- `build/scripts/generate_hooks.py`: current per-matcher generator.

---

*Template Version: 1.1*
*Created: 2026-06-02*
*GitHub Issue: #2295*
