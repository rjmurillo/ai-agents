# Test Report: PR #3097 - Dispatcher stdin ceiling (64 MiB) and per-candidate matched-replay limit (2 MiB)

## Scope

Worktree `.wt/3097`, branch
`fix/dispatcher-oversize-allow-unmatched-3074` vs `origin/main` merge-base
`7a40f89e82cf9a0ea0954c718899c00ec4d4c110`. This includes both the committed
history on the branch and the staged-but-uncommitted working tree changes
present in the worktree at QA time. Per the task instructions this QA pass
does not commit, stage, or otherwise alter that state; it evaluates the
worktree as delivered.

**Diff stat (calculated independently in this session):** 51 files changed,
3576 insertions(+), 1418 deletions(-).

File breakdown:

| Category | Count | Files |
|----------|-------|-------|
| Generators | 2 | `build/scripts/generate_dispatcher.py`, `build/scripts/generate_hooks_shim.py` |
| Dispatcher entrypoints | 5 | `_dispatch.py` under PreToolUse, PostToolUse, SessionStart, SessionEnd, UserPromptSubmit |
| Generated matcher shims | 34 | `invoke_*.py` under PreToolUse (27) and PostToolUse (7) |
| Tests | 3 | `test_generate_dispatcher.py`, `test_generate_hooks.py`, `test_dispatch_small_apply_patch_regression.py` |
| Plugin manifests | 2 | `.claude/.claude-plugin/plugin.json`, `src/copilot-cli/.claude-plugin/plugin.json` (version 0.6.47) |
| Session/memory artifacts | 3 | episode json, session json, `dispatcher-payload-ceiling.md` |

**Correction to the prior QA pass on this PR:** the earlier report claimed
`generate_hooks_shim.py` was untouched by this diff, that real shims reject
before matcher selection, and that the 64 MiB change helps only tools with no
registered matcher. All three claims are false. `git diff` against the
merge-base shows `generate_hooks_shim.py` modified (+117/-71 lines): the
per-matcher read ceiling moved from a 2 MiB pre-match cap to the shared 64 MiB
`HOOK_STDIN_CEILING_MIB` constant, checked before JSON parsing, and a new,
separate `MATCHED_SHIM_PAYLOAD_LIMIT_MIB = 2` cap is applied only after
matcher selection, per matched candidate. This is a real behavioral change to
every registered shim, not a documentation clarification. This report
replaces those claims with source- and runtime-verified evidence below.

## Reconciliation

```text
Promised: One source of truth (HOOK_STDIN_CEILING_MIB = 64) drives both dispatcher
          and matcher-shim read ceilings. Raw input above 64 MiB fails closed for
          gate events before parsing or dispatch; observe events return 0 and do
          not run shims. Matcher shims classify valid events up to 64 MiB.
          Unmatched payloads above 2 MiB and below 64 MiB exit 0. Every matching
          candidate in a toolCalls batch is evaluated in order. Each selected
          candidate is canonicalized into its own replay, excluding large
          unrelated siblings. The 2 MiB limit applies to each matched replay;
          oversize matched replay exits 2 and names matcher, source field, and
          byte limit, without payload bytes. Wrapped direct SystemExit values
          normalize as None=0, int unchanged, non-int=1. First non-zero matched
          candidate stops the shim; all allowed matches return 0. The final
          staged PreToolUse dispatcher plus the real 27-shim manifest allow a
          >2 MiB apply_patch and deny a >2 MiB matched Edit.
Delivered: HOOK_STDIN_CEILING_MIB = 64 is defined once in generate_hooks_shim.py
          (line 57) and imported by generate_dispatcher.py (line 46), which
          renders it into both the dispatcher entrypoint (_MAX_STDIN_BYTES) and
          every generated matcher shim (_HOOK_STDIN_CEILING_BYTES). Confirmed by
          direct subprocess probe against the generated worktree PreToolUse
          dispatcher: an
          exact 67,108,864-byte payload allows (rc=0), 67,108,865 bytes denies on
          a gate event (rc=2) and allows on an observe event (rc=0), in both cases
          before run_dispatch executes (stderr shows the entrypoint's own message,
          registered shims never run). A 5,242,880-byte apply_patch payload
          (unmatched by all 27 registered PreToolUse matchers) returns rc=0 against
          the final staged generated dispatcher. A 3,145,728-byte Edit payload (matched by
          two registered shims) returns rc=2 with stderr
          "matcher-shim [^(Write|Edit)$]: matched replay from tool_input exceeds
          2097152 bytes; refusing", naming the matcher, the source field, and the
          byte limit, with zero payload bytes in stdout or stderr. A toolCalls
          batch with two small matched Edit candidates runs the wrapped guard
          twice, both allow, rc=0. A toolCalls batch with one 3 MiB unmatched Bash
          sibling and one small matched Edit candidate returns rc=0 with the
          wrapped guard invoked exactly once, proving canonicalization strips the
          sibling from the matched replay. A toolCalls batch with a 3 MiB matched
          Edit candidate first and a small matched Edit candidate second returns
          rc=2 and the wrapped guard never runs a second time, proving the shim
          stops at the first non-zero result and does not evaluate the remaining
          candidate. Malformed JSON on stdin exits 2 with
          "malformed JSON on stdin: ..." and no raw bytes echoed.
          _shim_exit_code/_exit_code in both generate_hooks_shim.py and
          hook_dispatch.py normalize None to 0, pass ints through, and map
          non-int codes to 1, matching source read in this session.
          `uv run pytest` on the 5 mandated files: 225 passed, 1 skipped in
          8.25s. Ruff and mypy on the 4 changed canonical/test files: 0
          findings each. `build_all.py --check --platform copilot-cli`: exit
          0, tree unchanged before/after (snapshot/restore verified byte for
          byte on the 44 code-relevant files), confirming no generator drift.
          `check_plugin_manifest_parity.py`: exit 0, both manifests at 0.6.47.
Gap: None against the stated contract. One unrelated environmental artifact was
          observed during this session: a Stop-hook side effect regenerated
          .agents/retrospective/INDEX.md and added an untracked
          2026-07-17-auto-retro.md file, matching known tooling defect #3140.
          This is agent-tooling noise, not a change to this PR's product code,
          and this report does not alter or remove it per the instruction not
          to edit code, tests, generated artifacts, session logs, manifests,
          GitHub, or commits.
Result: PASS
```

## Summary

| Metric | Value |
|--------|-------|
| Mandated pytest suite (5 files) | 225 passed, 1 skipped (0 failed) in 8.25s |
| Ruff (4 changed canonical/test files) | 0 findings |
| mypy (4 changed canonical/test files) | 0 errors (Success: no issues found in 4 source files) |
| `build_all.py --check --platform copilot-cli` | exit 0, 0 drift |
| `check_plugin_manifest_parity.py` | exit 0, both manifests at 0.6.47 |
| Direct subprocess probes (this session) | 10/10 confirmed against the final staged generated artifacts |
| Diff stat (independently calculated) | 51 files changed, 3576 insertions(+), 1418 deletions(-) |

## Test Results

### Passed

- `uv run pytest tests/build_scripts/test_generate_hooks.py tests/build_scripts/test_generate_dispatcher.py tests/build_scripts/test_dispatch_small_apply_patch_regression.py tests/build_scripts/test_copilot_dispatcher_artifact.py tests/test_hook_dispatch.py -q`: 225 passed, 1 skipped in 8.25s, 0 failed.
- `test_inject_shim_denies_one_byte_above_read_ceiling`, `test_inject_shim_allows_exact_read_ceiling_when_unmatched`: exact/one-over ceiling behavior at the shim layer, exercised and passing.
- `test_inject_shim_allows_payload_above_matched_limit_when_unmatched`: unmatched payload above 2 MiB and below 64 MiB exits 0, exercised and passing.
- `test_inject_shim_allows_matched_replay_at_limit`, `test_inject_shim_denies_matched_replay_above_limit_with_context`: matched-replay 2 MiB boundary, exercised and passing.
- `test_inject_shim_replays_small_match_from_large_multi_call_event`: unrelated large sibling excluded from a matched candidate's replay, exercised and passing.
- `test_inject_shim_evaluates_all_matching_calls_until_denied`: every matching candidate evaluated in order until a denial, exercised and passing.
- `TestOversizeCeiling::test_exact_ceiling_allows_unmatched_payload`, `test_above_ceiling_gate_denies_without_leaking_payload`, `test_observe_allows_on_oversize`: dispatcher-entrypoint boundary and no-payload-disclosure assertions, exercised and passing.
- `TestCeilingConstant::test_entrypoint_embeds_raised_ceiling`: drift guard on the embedded constant, supplementary only.
- `tests/build_scripts/test_dispatch_small_apply_patch_regression.py`, `tests/build_scripts/test_copilot_dispatcher_artifact.py`, `tests/test_hook_dispatch.py`: full files pass, confirming the #3083/#3130 small-apply_patch regression case and the generated-artifact regression for the dispatcher cutover remain intact.

### Independent runtime probes (this session, subprocess against real generated files)

Ran directly against `src/copilot-cli/hooks/PreToolUse/_dispatch.py`,
`src/copilot-cli/hooks/PostToolUse/_dispatch.py`, and
`src/copilot-cli/hooks/PreToolUse/invoke_security_gate__Write_Edit_c39898.py`
(matcher `^(Write|Edit)$`), all as staged in the worktree, with the real
27-shim `_manifest.json`:

```text
PreToolUse exact 64 MiB (67108864 B), unmatched     -> rc=0, stderr=b''
PreToolUse 64 MiB + 1 (67108865 B), gate, unmatched -> rc=2, stderr names event
                                                        and shim list, no payload bytes
PostToolUse 64 MiB + 1, observe, unmatched          -> rc=0, stderr names event
                                                        and shim list, no payload bytes
PreToolUse ~5 MiB (5242880 B) apply_patch           -> rc=0 (unmatched by all 27 shims)
PreToolUse ~3 MiB (3145728 B) Edit                   -> rc=2, stderr:
  "matcher-shim [^(Write|Edit)$]: matched replay from tool_input exceeds
   2097152 bytes; refusing"
toolCalls batch, 2 small matched Edit candidates     -> rc=0, wrapped guard ran twice,
                                                         both allowed
toolCalls batch, 3 MiB unmatched Bash + small Edit   -> rc=0, wrapped guard ran once
                                                         (sibling excluded from replay)
toolCalls batch, 3 MiB matched Edit + small Edit     -> rc=2, stderr names
                                                         "toolCalls.args", second
                                                         candidate never evaluated
Malformed JSON stdin ("{not valid json")             -> rc=2, stderr:
  "malformed JSON on stdin: Expecting property name enclosed in double quotes..."
```

No test payload marker (`AAAA`, `CCCC`, the padding characters, or
`apply_patch`) appeared in stdout or stderr in any of the above runs. The
static source field name `tool_input` or `toolCalls.args` was expected in
the oversize diagnostic and verified present, since the diagnostic names the
source field by design; it is not payload content.

### Failed

None.

### Skipped

1 skip in the mandated 5-file run (pre-existing, unrelated to this diff).

## Coverage Matrix

| Requirement | Test Type | Evidence | Status |
|-------------|-----------|----------|--------|
| Exact boundary (64 MiB dispatches) | Subprocess exec, real dispatcher | 67,108,864-byte payload, rc=0, stderr empty | PASS |
| One-over boundary (64 MiB + 1 fails closed before dispatch) | Subprocess exec, real dispatcher | 67,108,865-byte payload: gate rc=2, observe rc=0, both before run_dispatch | PASS |
| Unmatched large payload (above 2 MiB, below 64 MiB) | Subprocess exec, real dispatcher + real shim | 5 MiB apply_patch, rc=0; `test_inject_shim_allows_payload_above_matched_limit_when_unmatched` | PASS |
| Matched large payload (above 2 MiB matched-replay limit) | Subprocess exec, real shim | 3 MiB Edit, rc=2, names matcher/field/limit; `test_inject_shim_denies_matched_replay_above_limit_with_context` | PASS |
| Multiple matching calls (evaluated in order) | Subprocess exec, real shim | toolCalls batch, 2 small Edit candidates, both invoked in order, rc=0; `test_inject_shim_evaluates_all_matching_calls_until_denied` | PASS |
| Unrelated large sibling excluded from replay | Subprocess exec, real shim | 3 MiB unmatched Bash + small matched Edit, guard invoked once, rc=0; `test_inject_shim_replays_small_match_from_large_multi_call_event` | PASS |
| Malformed JSON | Subprocess exec, real shim | `{not valid json`, rc=2, decode-error message, no raw bytes echoed | PASS |
| No payload disclosure | Negative assertion on stdout/stderr across all probes | Marker/padding bytes absent in every oversize/malformed/matched-deny run | PASS |
| Generated drift (generator output matches staged tree) | `build_all.py --check --platform copilot-cli` | Exit 0; snapshot/restore left the 44 code-relevant files byte-identical before and after | PASS |
| Actual staged artifact (real 27-shim manifest, real dispatcher) | Subprocess exec against staged generated files, not a fixture | All probes above ran against `src/copilot-cli/hooks/PreToolUse/_dispatch.py` and `_manifest.json` as staged in the worktree | PASS |

## Test Quality Assessment

The mandated pytest suite and the manual probes both execute the generated
code as a subprocess against real or staged plugin roots, not pattern-matching
against source text. Assertions check exit codes, stderr content for the
absence of payload bytes, and file-based side effects (guard-ran sentinels,
byte counts observed by a wrapped guard) rather than structural claims about
the source. `TestCeilingConstant::test_entrypoint_embeds_raised_ceiling` is
the one string-match test in the suite; it is a supplementary drift guard,
not load-bearing evidence, consistent with its stated role in the test file's
own docstring.

## Corroborating Evidence (parent session, not independently rerun here)

Cited for context only, not as the basis for this verdict:

- Full suite: 14,434 passed, 21 skipped, 45 xfailed, 3 warnings in 197.30s.
- Build-script suite: 839 passed, 1 skipped in 16.64s.
- `pre_pr.py`: 29 passed, 4 skipped, zero failures.
- Live Copilot vendor-hook smoke: 1 passed.
- Final security re-review: no blockers.
- Final code review: no blocking findings.
- Plugin 0.6.47 is the highest version among current open PRs; next is 0.6.46.
- Tooling defect #3140 (subagent Stop hooks creating auto-retro skeletons) is unrelated to product behavior; reproduced as a side effect during this QA session (see Reconciliation Gap above).

## Recommendations

No pending QA work. No optional follow-up.

## Status

**QA COMPLETE**
