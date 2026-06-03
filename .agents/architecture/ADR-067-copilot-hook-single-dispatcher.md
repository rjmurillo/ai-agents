# ADR-067: Single In-Process Dispatcher for Copilot CLI Hooks

## Status

DRAFT

status: draft

## Date

2026-06-03

## Context

Copilot CLI has no per-hook `matcher` field. It runs every registered hook
entry on every tool call. The generator (`build/scripts/generate_hooks.py`)
works around this by emitting one self-filtering "matcher shim" file per
(hook, matcher) pair: each shim reads stdin, checks the matcher in-process, and
either exits 0 (not applicable) or runs the wrapped hook.

Each shim is a separate `hooks.json` entry, so Copilot spawns a fresh Python
interpreter per shim, per tool call. Issue #2295 measured the cost on Windows:

- ~246 ms per shim invocation (Python interpreter cold start dominates).
- ~40 installed `preToolUse` shim files.
- ~8.7 s aggregate for all of them, sequentially.

Copilot enforces a `preToolUse` timeout it does not expose (`timeoutSec` in
`hooks.json` is ignored; observed kills at 2-3 s). When the aggregate spawn cost
exceeds that budget, Copilot reports `hook errored` and fails the tool **closed**
("Denied by preToolUse hook (hook errored)"). Fail-closed is correct (the
fail-closed contract from #2271 and #2230); the defect is that a **healthy** hook
is killed by our own per-shim process-spawn overhead, manufacturing a false
denial of benign, read-only commands. Issue #2295 observed 3 of 197 `preToolUse`
calls denied this way in one session.

The matcher-shim self-filtering is correct and must stay (Copilot still has no
native matcher). The problem is purely the N-process dispatch cost.

## Decision

Collapse the N per-shim processes for a Copilot event into **one process per
event**: a dispatcher. The host spawns a single interpreter for the event; the
dispatcher then runs each registered shim **in-process** via `runpy`, so the
interpreter cold start (~200 ms floor) is paid once instead of N times.

### Runtime contract (the security-critical part)

Implemented in `.claude/lib/hook_dispatch.py::run_dispatch` and proven by
`tests/test_hook_dispatch.py`:

1. **Manifest-driven, not directory-driven.** The shim list comes from the
   generator's registered-entry list (the same source as `hooks.json`), written
   to a per-event `_manifest.json`. The dispatcher runs exactly that ordered set.
   Orphaned `invoke_*.py` files on disk (multi-matcher expansion leaves more
   files than registered entries: 38 on disk vs 29 registered for `preToolUse`)
   are **never** executed.
2. **Fail-closed (preserves the #2271/#2230 contract).** The first shim to exit
   non-zero denies the tool; the dispatcher returns that code and stops. A
   registered shim missing on disk, or an unexpected exception while running a
   shim, is a denial (exit 2), never a silent allow. A shim's own internal
   fail-open (its `main` returning 0 on its own error, e.g. the LSP navigation
   guards) is preserved unchanged, because the dispatcher only observes the
   shim's final exit code.
3. **stdin replay.** Each shim reads `sys.stdin.buffer`; the dispatcher rewinds a
   fresh stream of the original payload bytes before every shim, so each shim
   inspects exactly the bytes the host delivered. No payload-schema mutation
   (no #2290 regression).
4. **Output passthrough.** Shim stdout/stderr flows to the dispatcher's streams,
   so block guidance still reaches the host.
5. **Cost.** In-process `runpy` reuses cached imports; per-shim cost drops to a
   few ms. 29 shims plus one interpreter start is well under the observed 2-3 s
   budget (estimated ~400 ms total vs ~8.7 s today).

### Why not the alternatives

- **Raise `timeoutSec`**: rejected. Copilot ignores it (observed kills below the
  configured value); the budget is host-controlled.
- **Speed up each shim**: rejected. Python cold start (~200 ms) is a floor;
  40 x floor still blows the budget.
- **Persistent hook daemon**: heavier and stateful; revisit only if the
  single-dispatcher consolidation proves insufficient.

## Rollout (gated cutover)

This ADR ships with the dispatcher runtime and its tests, but the live
`hooks.json` cutover (one entry per event instead of N) is **gated** and does
NOT change default generator output:

1. `.claude/lib/hook_dispatch.py` + `tests/test_hook_dispatch.py` land first
   (the mechanism, unit-proven).
2. The opt-in installed-plugin harness (`RUN_INSTALLED_PLUGIN_HOOK_E2E=1`,
   issue #2300) validates the real installed shims and the dispatcher against
   the actual runtime, since CI cannot run Copilot.
3. The generator gains a dispatcher emission mode, **default off**. Default
   builds remain byte-identical (N entries) until the mode is enabled.
4. The cutover (enabling the mode, regenerating `hooks.json` to one
   dispatcher entry per event) requires: this ADR accepted via `adr-review`
   consensus, and a green `RUN_INSTALLED_PLUGIN_HOOK_E2E=1` run on a real
   Copilot install proving fail-closed is preserved.

This sequencing means merging the dispatcher mechanism cannot, by itself, change
hook behavior or open a fail-open hole; the behavior change is a separate,
reviewed, validated step.

## Consequences

- Positive: removes the false fail-closed denials (#2295); one interpreter start
  per event; the matcher-shim logic and every guard stay unchanged.
- Negative: a per-event single point of execution. A dispatcher bug affects all
  guards for that event. Mitigated by: fail-closed default, manifest-driven
  exactness, the unit suite, the installed-plugin harness, and the gated rollout.
- The Claude side is unaffected (Claude honors native matchers; it keeps direct
  per-hook entries).

## References

- Issue #2295 (the spawn-storm false-timeout defect, evidence + measurements).
- Issue #2300 (installed-plugin hook condition harness, the runtime validation).
- `.claude/lib/hook_dispatch.py`, `tests/test_hook_dispatch.py`.
- Fail-closed hook contract: issues #2271 (rejected soft-blocking), #2230
  (rejected launcher fail-open).
- ADR-063 (hook/skill runtime decomposition context).
