# Dispatcher payload ceiling

## Contract

Generated dispatchers and matcher shims share one ceiling constant:
`HOOK_STDIN_CEILING_MIB = 64`, defined once in
`build/scripts/generate_hooks_shim.py` and imported by
`build/scripts/generate_dispatcher.py`.

### Dispatcher

The generated dispatcher entrypoint reads at most 64 MiB plus one byte from
stdin. Gate events (PreToolUse) that exceed the ceiling exit 2 before any
shim runs. Observe events (PostToolUse, SessionStart, SessionEnd,
UserPromptSubmit) that exceed the ceiling return 0 and skip the shims.
Diagnostics name the event and the static registered shim list. They never
log payload bytes.

### Matcher shims

Each generated matcher shim reads and parses up to 64 MiB of stdin only to
classify candidates against its matcher. Unmatched payloads above 2 MiB and
at or below 64 MiB exit 0; the shim does not gate a call it never matched.

A second, separate limit, `MATCHED_SHIM_PAYLOAD_LIMIT_MIB = 2`, applies only
after matcher selection, to each canonical replay built for a matched
candidate. An oversize matched replay exits 2 and names the matcher and the
source field, again without payload bytes.

Every matching candidate inside a `toolCalls` batch is evaluated in input
order, not only the first. Each candidate's replay excludes unrelated
sibling calls, so a large unmatched sibling cannot deny a small matched
candidate. Evaluation stops at the first non-zero result; if every matching
candidate allows, the shim exits 0.

Wrapped `SystemExit` values normalize consistently: `None` becomes 0, an
integer code passes through unchanged, and a non-integer code becomes 1.

## Security reasoning

The bounded 64 MiB read on both the dispatcher and the shim mitigates
CWE-400 resource exhaustion; neither component buffers or parses an
unbounded payload.

The post-selection 2 MiB replay limit prevents an oversized matched call
from reaching a wrapped guard, while still allowing a large unrelated call
to pass through unmatched.

Evaluating every matching candidate, instead of stopping after the first
match, closes a safe-first, dangerous-second bypass: an attacker can no
longer hide a dangerous second call behind a benign first call that matches
the same shim.

## Evidence

- Generators: `build/scripts/generate_dispatcher.py`,
  `build/scripts/generate_hooks_shim.py`.
- Tests: `tests/build_scripts/test_generate_dispatcher.py`,
  `tests/build_scripts/test_generate_hooks.py`,
  `tests/build_scripts/test_dispatch_small_apply_patch_regression.py`.
- Focused suite (5 mandated files): 225 passed, 1 skipped.
- Build-script suite: 839 passed, 1 skipped.
- Full suite: 14434 passed.
- Final QA verdict: PASS, recorded in
  `.agents/qa/pr-3097-dispatcher-stdin-ceiling-test-report.md`.
