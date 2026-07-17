# Test Report: PR #3097 - Bounded dispatcher and matcher input

## Scope

Worktree `pr3097-worktree`, branch
`fix/dispatcher-oversize-allow-unmatched-3074` vs `origin/main` merge-base
`2c15968b40e8ac9a66ae42dadb1d0313f6f0ed72`. The final implementation tip is
`a34dd4667bda38e728d3610ffe66d39f20e78b53`. This report covers the committed
branch diff, including the shared 64 MiB raw-input ceiling, 2 MiB per-matched
replay ceiling, 256-entry raw `toolCalls` cap, and fail-closed malformed-batch
validation, including rejection of padded `toolCalls[].name` values.

**Diff stat (calculated independently in this session):** 50 files changed,
5461 insertions(+), 2118 deletions(-).

File breakdown:

| Category | Count | Files |
|----------|-------|-------|
| Generators | 2 | `build/scripts/generate_dispatcher.py`, `build/scripts/generate_hooks_shim.py` |
| Dispatcher entrypoints | 5 | `_dispatch.py` under PreToolUse, PostToolUse, SessionStart, SessionEnd, UserPromptSubmit |
| Generated matcher shims | 34 | `invoke_*.py` under PreToolUse (27) and PostToolUse (7) |
| Tests | 3 | `test_generate_dispatcher.py`, `test_generate_hooks.py`, `test_dispatch_small_apply_patch_regression.py` |
| Plugin manifests | 2 | `.claude/.claude-plugin/plugin.json`, `src/copilot-cli/.claude-plugin/plugin.json` (version 0.6.47) |
| QA/session/memory artifacts | 4 | this report, two session logs, `dispatcher-payload-ceiling.md` |

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
          byte limit, without payload bytes. The raw toolCalls list is capped
          at 256 entries before filtering or guard execution; every raw entry
          counts. Malformed entries and an empty batch that conflicts with a
          top-level tool name exit 2 before any guard runs. Structurally valid
          batched entries are canonical over conflicting top-level fields.
          Candidate selection is lazy after full-batch prevalidation and does
          not build a second candidate list. Wrapped direct SystemExit values
          normalize as None=0, int unchanged, non-int=1. First non-zero matched
          candidate stops the shim; all allowed matches return 0. The final
          PreToolUse dispatcher plus the real 27-shim manifest allow a
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
          the final generated dispatcher. A 3,145,728-byte Edit payload (matched by
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
          A mixed-schema event with a benign top-level command and a dangerous
          batched command evaluates the batched command and exits 2. Exactly
          256 raw toolCalls entries are accepted; 257 entries exit 2 before
          the guard runs. A non-object entry, missing/non-string/empty name,
          empty batch combined with either top-level name key, including null or
          non-string values, a malformed later entry, or a name with leading or
          trailing whitespace also exits 2 before any guard runs. Direct probes
          against
          both reviewer-cited generated shims confirmed rc=2 with no payload
          disclosure. Source inspection confirms `_shim_candidate_payloads` and
          `_shim_select_payloads` yield candidates, while
          `_shim_dispatch_selections` delegates with `yield from`.
          _shim_exit_code/_exit_code in both generate_hooks_shim.py and
          hook_dispatch.py normalize None to 0, pass ints through, and map
          non-int codes to 1, matching source read in this session.
          A live generated-shim probe with `"Edit "` exits 2 and reports
          "toolCalls[0].name must not have leading or trailing whitespace."
          `uv run pytest` on the 5 mandated files: 246 passed, 1 skipped.
          The build-script suite reported 860 passed, 1 skipped. The full suite
          reported 14455 passed, 21 skipped, 45 expected failures, and 3 warnings.
          Ruff and mypy on the changed generator and test file: 0 findings each.
          The CWE-78 scanner found no vulnerabilities in those files.
          `build_all.py --check`: exit 0, confirming no generator drift.
          `check_plugin_manifest_parity.py`: exit 0, both manifests at 0.6.47.
Gap: None against the stated contract. Stop-hook defect #3140 created
          unrelated auto-retro noise during review. Those files were
          quarantined outside PR scope, and the retrospective index was
          restored. No product files changed as part of that cleanup.
Result: PASS
```

## Summary

| Metric | Value |
|--------|-------|
| Mandated pytest suite (5 files) | 246 passed, 1 skipped, 0 failed |
| Build-script suite | 860 passed, 1 skipped, 0 failed |
| Full Python suite | 14455 passed, 21 skipped, 45 expected failures, 3 warnings |
| Ruff (changed generator and test file) | 0 findings |
| mypy (changed generator and test file) | 0 errors (Success: no issues found in 2 source files) |
| CWE-78 scan (changed generator and test file) | 0 findings |
| `build_all.py --check` | exit 0, 0 drift |
| `check_plugin_manifest_parity.py` | exit 0, both manifests at 0.6.47 |
| Direct subprocess probes | Every listed boundary confirmed against final generated artifacts |
| Diff stat (independently calculated) | 50 files changed, 5461 insertions(+), 2118 deletions(-) |

## Test Results

### Passed

- `uv run python -m pytest tests/build_scripts/test_generate_hooks.py tests/build_scripts/test_generate_dispatcher.py tests/build_scripts/test_dispatch_small_apply_patch_regression.py tests/build_scripts/test_copilot_dispatcher_artifact.py tests/test_hook_dispatch.py -q`: 246 passed, 1 skipped, 0 failed.
- `uv run python -m pytest tests/build_scripts/ -q`: 860 passed, 1 skipped, 0 failed.
- `uv run python -m pytest tests/ -q`: 14455 passed, 21 skipped, 45 expected failures, 3 warnings.
- `test_inject_shim_denies_one_byte_above_read_ceiling`, `test_inject_shim_allows_exact_read_ceiling_when_unmatched`: exact/one-over ceiling behavior at the shim layer, exercised and passing.
- `test_inject_shim_allows_payload_above_matched_limit_when_unmatched`: unmatched payload above 2 MiB and below 64 MiB exits 0, exercised and passing.
- `test_inject_shim_allows_matched_replay_at_limit`, `test_inject_shim_denies_matched_replay_above_limit_with_context`: matched-replay 2 MiB boundary, exercised and passing.
- `test_inject_shim_replays_small_match_from_large_multi_call_event`: unrelated large sibling excluded from a matched candidate's replay, exercised and passing.
- `test_inject_shim_evaluates_all_matching_calls_until_denied`: every matching candidate evaluated in order until a denial, exercised and passing.
- `test_inject_shim_mixed_schema_top_level_fields_do_not_bypass_toolcalls_selection`: batched candidates override conflicting top-level fields, exercised and passing.
- `test_inject_shim_toolcalls_candidate_cap_boundary_fires_once`, `test_inject_shim_toolcalls_candidate_cap_denies_one_above_boundary`: 256-entry acceptance and 257-entry denial, exercised and passing.
- `test_inject_shim_toolcalls_candidate_cap_denies_257_invalid_entries`: the raw cap includes invalid entries before filtering, exercised and passing.
- `test_inject_shim_denies_malformed_toolcalls_before_dispatch`, `test_inject_shim_denies_empty_toolcalls_with_top_level_tool_name`, and `test_inject_shim_validates_entire_toolcalls_batch_before_dispatch`: malformed or ambiguous batches exit 2 before any guard runs, including null and non-string top-level name values plus names padded with spaces, tabs, or newlines. `test_inject_shim_allows_empty_toolcalls_without_top_level_tool_name` preserves the no-candidate allow case.
- `TestOversizeCeiling::test_exact_ceiling_allows_unmatched_payload`, `test_above_ceiling_gate_denies_without_leaking_payload`, `test_observe_allows_on_oversize`: dispatcher-entrypoint boundary and no-payload-disclosure assertions, exercised and passing.
- `TestCeilingConstant::test_entrypoint_embeds_raised_ceiling`: drift guard on the embedded constant, supplementary only.
- `tests/build_scripts/test_dispatch_small_apply_patch_regression.py`, `tests/build_scripts/test_copilot_dispatcher_artifact.py`, `tests/test_hook_dispatch.py`: full files pass, confirming the #3083/#3130 small-apply_patch regression case and the generated-artifact regression for the dispatcher cutover remain intact.

### Independent runtime probes (this session, subprocess against real generated files)

Ran directly against `src/copilot-cli/hooks/PreToolUse/_dispatch.py`,
`src/copilot-cli/hooks/PostToolUse/_dispatch.py`, and
`src/copilot-cli/hooks/PreToolUse/invoke_security_gate__Write_Edit_c39898.py`,
and `src/copilot-cli/hooks/PreToolUse/invoke_lsp_read_guard__Read_852b43.py`
(matchers `^(Write|Edit)$` and `Read`), all from the committed worktree, with
the real 27-shim `_manifest.json`:

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
mixed schema, safe top-level + dangerous batched call -> rc=2, batched call evaluated
toolCalls batch, exactly 256 raw entries              -> rc=0, guard ran once
toolCalls batch, 257 raw entries                      -> rc=2, guard did not run
toolCalls batch, 257 invalid entries                  -> rc=2, guard did not run
malformed batch + matching top-level name, security   -> rc=2, guard did not run
malformed batch + matching top-level name, LSP Read   -> rc=2, guard did not run
empty batch + snake integer top-level name          -> rc=2, guard did not run
empty batch + camel null top-level name              -> rc=2, guard did not run
empty batch without a top-level name                 -> rc=0, guard did not run
toolCalls batch, name "Edit "                        -> rc=2, guard did not run
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
| Mixed-schema precedence | Subprocess exec, real shim | Dangerous batched command overrides benign top-level command and exits 2; `test_inject_shim_mixed_schema_top_level_fields_do_not_bypass_toolcalls_selection` | PASS |
| Raw candidate cap | Subprocess exec, real shim | 256 entries accepted; 257 entries denied before guard execution | PASS |
| Invalid entries count toward cap | Generated-shim execution | 257 non-dict entries denied; `test_inject_shim_toolcalls_candidate_cap_denies_257_invalid_entries` | PASS |
| Malformed batch validation | Generated-shim execution and unit tests | Non-object, missing-name, non-string-name, empty-name, valid-then-malformed, and empty-batch cases with any present top-level name key exit 2 before guard execution | PASS |
| Padded batch name validation | Generated-shim execution and unit tests | Leading space, trailing space, and tab/newline padding exit 2 before guard execution | PASS |
| Lazy candidate traversal | Source inspection and generated-shim execution | Bounded full-batch prevalidation, then `_shim_candidate_payloads` and `_shim_select_payloads` yield candidates; `_shim_dispatch_selections` uses `yield from` | PASS |
| Unrelated large sibling excluded from replay | Subprocess exec, real shim | 3 MiB unmatched Bash + small matched Edit, guard invoked once, rc=0; `test_inject_shim_replays_small_match_from_large_multi_call_event` | PASS |
| Malformed JSON | Subprocess exec, real shim | `{not valid json`, rc=2, decode-error message, no raw bytes echoed | PASS |
| No payload disclosure | Negative assertion on stdout/stderr across all probes | Marker/padding bytes absent in every oversize/malformed/matched-deny run | PASS |
| Generated drift (generator output matches generated tree) | `build_all.py --check` | Exit 0; generated trees match their canonical sources | PASS |
| Actual generated artifact (real 27-shim manifest, real dispatcher) | Subprocess exec against generated files, not a fixture | All probes above ran against `src/copilot-cli/hooks/PreToolUse/_dispatch.py` and `_manifest.json` from the committed worktree | PASS |

## Test Quality Assessment

The mandated pytest suite and the manual probes both execute the generated
code as a subprocess against real or generated plugin roots, not pattern-matching
against source text. Assertions check exit codes, stderr content for the
absence of payload bytes, and file-based side effects (guard-ran sentinels,
byte counts observed by a wrapped guard) rather than structural claims about
the source. `TestCeilingConstant::test_entrypoint_embeds_raised_ceiling` is
the one string-match test in the suite; it is a supplementary drift guard,
not load-bearing evidence, consistent with its stated role in the test file's
own docstring.

## Final evidence

Executed against the final malformed-batch and padded-name implementation:

- Full suite: 14,455 passed, 21 skipped, 45 expected failures, 3 warnings.
- Build-script suite: 860 passed, 1 skipped.
- `pre_pr.py`: 29 passed, 4 skipped, zero failures.
- Copilot plugin smoke suite: 16 passed, 2 live CLI cases skipped by the explicit `RUN_CLI_E2E` gate.
- Tooling defect #3140 (subagent Stop hooks creating auto-retro skeletons) is unrelated to product behavior; reproduced as a side effect during this QA session (see Reconciliation Gap above).
- Repository-wide `ruff check .` reports 406 existing findings outside the
  changed generator and test file. Targeted Ruff on both changed files passes.

## Recommendations

The generated-wrapper file-size warnings are review-tooling noise. They do
not change runtime coverage or this PASS verdict.

## Status

**QA COMPLETE**
