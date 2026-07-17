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

`MAX_MATCHER_TOOL_CALLS = 256` caps the raw `toolCalls` list before
candidate copying, matcher evaluation, or guard execution. The cap counts
invalid and non-dict entries. Exactly 256 entries are accepted; 257 are
rejected with exit 2.

A second, separate limit, `MATCHED_SHIM_PAYLOAD_LIMIT_MIB = 2`, applies only
after matcher selection, to each canonical replay built for a matched
candidate. An oversize matched replay exits 2.

When `toolCalls` exists, each selected batched call is the canonical replay.
Conflicting top-level `tool_name` or `tool_input` fields do not override the
selected call.

Every matching candidate inside a `toolCalls` batch is evaluated in input
order, not only the first. Each candidate's replay excludes unrelated
sibling calls, so a large unmatched sibling cannot deny a small matched
candidate. Evaluation stops at the first non-zero result; if every matching
candidate allows, the shim exits 0.

Candidate and selection traversal use generators, so accepted events do not
allocate a second full candidate list.

Wrapped `SystemExit` values normalize consistently: `None` becomes 0, an
integer code passes through unchanged, and a non-integer code becomes 1.

Diagnostics include matcher, source field, count, and limit where relevant.
They never include payload content.

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

The bounded 256-entry `toolCalls` cap prevents unbounded iteration over
adversarially crafted arrays, mitigating CWE-400 at the candidate-count
level independently of payload size.

Fixing `toolCalls` as the canonical source when the key is present closes a
mixed-schema bypass. An attacker cannot embed a dangerous call in `toolCalls`
while showing a benign `tool_name` at the top level. A guard reading only the
top-level field would miss the dangerous call.

## Limit rationale

The three limits protect different resources and must stay independent:

- 64 MiB bounds the one raw stdin read and JSON parse. The prior 2 MiB raw
  limit rejected valid unmatched Copilot events before matcher selection.
  64 MiB admits observed multi-call payloads while preserving a fixed process
  memory bound.
- 2 MiB bounds each selected replay passed to a wrapped guard. Existing guards
  were designed and tested around this ceiling, so raising it would increase
  guard memory and parsing exposure without helping unmatched calls.
- 256 bounds candidate count before filtering. Payload bytes alone do not bound
  iteration cost because an attacker can submit many tiny or invalid entries.
  The value accepts normal batched events while fixing the maximum matcher and
  guard work per event.

These values are defensive operating limits, not measurements of a Copilot
host guarantee. They can change independently when production evidence supports
a different bound.

## Rejected alternative

A streaming prefilter was rejected. Matchers inspect both snake_case and
camelCase payload shapes, then replay canonical JSON to unmodified guard
scripts. A streaming parser would duplicate schema and matcher semantics before
the established guard boundary. That adds a second policy implementation and
still cannot safely dispatch a matched call without materializing its replay.
The bounded full parse plus lazy candidate traversal keeps one matcher policy,
preserves guard compatibility, and fixes both byte and candidate-count costs.

## Evidence

- Generators: `build/scripts/generate_dispatcher.py`,
  `build/scripts/generate_hooks_shim.py`.
- Tests: `tests/build_scripts/test_generate_dispatcher.py`,
  `tests/build_scripts/test_generate_hooks.py`,
  `tests/build_scripts/test_dispatch_small_apply_patch_regression.py`.
- Focused suite (5 mandated files): 229 passed, 1 skipped.
- Build-script suite: 843 passed, 1 skipped.
- Full suite: 14438 passed, 21 skipped, 45 expected failures, 3 warnings.
- Live generated-shim probe: mixed schema rc=2, 256 entries rc=0,
  257 entries rc=2, no payload disclosure.
- Final QA verdict: PASS, recorded in
  `.agents/qa/pr-3097-dispatcher-stdin-ceiling-test-report.md`.
