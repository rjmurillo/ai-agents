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

When the `toolCalls` key is present, its value must be a list. Object,
string, number, boolean, and null values exit 2 before top-level fallback.

`MAX_MATCHER_TOOL_CALLS = 256` caps the raw `toolCalls` list before
candidate copying, matcher evaluation, or guard execution. The cap counts
every raw entry. Exactly 256 structurally valid entries are accepted; 257 are
rejected with exit 2.

Every list entry is validated before any guard runs. Non-object entries and
entries without a non-empty, unpadded string `name` exit 2. An empty `toolCalls` list
combined with a top-level `tool_name` or `toolName` key also exits 2,
regardless of whether its value is a string, null, or another type. The payload
presents conflicting schemas with no canonical batched candidate.

A second, separate limit, `MATCHED_SHIM_PAYLOAD_LIMIT_MIB = 2`, applies only
after matcher selection, to each canonical replay built for a matched
candidate. An oversize matched replay exits 2.

Outer stdin and encoded calls use duplicate-key detection. A duplicate JSON
object key at any parsed depth exits 2 with the fixed diagnostic
`duplicate JSON object key`. The diagnostic does not include key or value bytes.

When a structurally valid `toolCalls` batch exists, each selected batched call
is the canonical replay. The replay removes `tool_name`, `toolName`,
`tool_input`, `toolArgs`, `tool_call_id`, and `toolCallId`, then emits the
selected call through canonical snake_case fields.

Without a batch, the shim validates top-level name, input, and call-ID alias
pairs before matcher evaluation. Name values must be non-empty, unpadded
strings. When both aliases are non-null, they must have recursive type-strict
JSON equality. JSON number `1` does not equal boolean `true`, including nested
input fields and call IDs. A null `tool_input` remains compatible with fallback
to `toolArgs`. Conflicting aliases exit 2. Matching aliases replay as one
canonical snake_case schema.

Every matching candidate inside a `toolCalls` batch is evaluated in input
order, not only the first. Each candidate's replay excludes unrelated
sibling calls, so a large unmatched sibling cannot deny a small matched
candidate. Evaluation stops at the first non-zero result; if every matching
candidate allows, the shim exits 0.

The bounded raw batch is validated in one pass before dispatch. Candidate and
selection traversal then use generators, so accepted events do not allocate a
second full candidate list.

Wrapped `SystemExit` values normalize consistently: `None` becomes 0, an
integer code passes through unchanged, and a non-integer code becomes 1.

Diagnostics include matcher, source field, count, and limit where relevant.
They never include payload content, duplicate key names, or duplicate values.

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

Rejecting malformed entries before dispatch closes the inverse bypass. A junk
`toolCalls` list can no longer suppress a matching top-level call by producing
zero candidates. Full-batch prevalidation also prevents a valid early
candidate from running before a malformed later entry is detected.

Rejecting non-list `toolCalls` values closes a fallback seam. A malformed batch
cannot be ignored in favor of a benign top-level call. Rejecting duplicate JSON
keys prevents last-value-wins decoding from erasing an earlier dangerous call.
Validating every top-level alias pair closes padded-name and conflicting name,
input, and call-ID bypasses. Type-strict equality prevents Python boolean-number
equality from treating different JSON values as the same. Canonical batch replay
removes every competing top-level alias before the wrapped guard reads stdin.

## Limit rationale

The three limits protect different resources and must stay independent:

- 64 MiB bounds each matcher shim raw stdin read and JSON parse. The prior
  2 MiB raw limit rejected valid unmatched Copilot events before matcher
  selection. The dispatcher fan-out repeats this bounded work; #3174 tracks a
  parse-once design.
- 2 MiB bounds each selected replay passed to a wrapped guard. Existing guards
  were designed and tested around this ceiling, so raising it would increase
  guard memory and parsing exposure without helping unmatched calls.
- 256 bounds candidate count before filtering. Payload bytes alone do not bound
  iteration cost because an attacker can submit many tiny entries. Malformed
  entries are rejected before dispatch, while the value fixes the maximum
  matcher and guard work for structurally valid events.

These values are defensive operating limits, not measurements of a Copilot
host guarantee. They can change independently when production evidence supports
a different bound.

## Rejected alternative

A streaming prefilter was rejected. Matchers inspect both snake_case and
camelCase payload shapes, then replay canonical JSON to unmodified guard
scripts. A streaming parser would duplicate schema and matcher semantics before
the established guard boundary. That adds a second policy implementation and
still cannot safely dispatch a matched call without materializing its replay.
The bounded full parse, bounded batch prevalidation, and lazy candidate
traversal keep one matcher policy, preserve guard compatibility, and fix byte,
candidate-count, and malformed-batch costs.

## Evidence

- Generators: `build/scripts/generate_dispatcher.py`,
  `build/scripts/generate_hooks_shim.py`.
- Tests: `tests/build_scripts/test_generate_dispatcher.py`,
  `tests/build_scripts/test_generate_hooks.py`,
  `tests/build_scripts/test_generate_hooks_schema_security.py`,
  `tests/build_scripts/test_dispatch_small_apply_patch_regression.py`.
- Focused suite (6 files): 277 passed, 1 skipped.
- Build-script suite: 891 passed, 1 skipped.
- Full suite: 14486 passed, 21 skipped, 45 expected failures, 3 warnings.
- Live generated-shim probes: mixed schema rc=2, 256 entries rc=0,
  257 entries rc=2, malformed batches rc=2 in both reviewed shims, empty
  batches with integer or null top-level name values rc=2, empty batches without
  a top-level name rc=0, padded names rc=2, non-list `toolCalls` rc=2,
  conflicting name, input, and call-ID aliases rc=2, JSON number-versus-boolean
  aliases rc=2, matching aliases replay one canonical snake_case schema,
  duplicate outer, nested, and encoded object keys rc=2 with no payload
  disclosure, and canonical batch replay removes all top-level aliases.
- Exact-ceiling dispatcher benchmark: 4.81 to 4.84 seconds and 276720 to
  277540 KiB peak RSS across three runs. Issue #3174 tracks parse amplification.
- Targeted Ruff and mypy passed on the authored Python files. The CWE-78
  scanner found zero vulnerabilities in 5 authored files.
- Final implementation tip: `2b59d62b35ab5dabef576f6120e8c6c485e60218`.
- Diff stat: 52 files changed, 9691 insertions, 4111 deletions.
- Final QA verdict: PASS, recorded in
  `.agents/qa/pr-3097-dispatcher-stdin-ceiling-test-report.md`.
