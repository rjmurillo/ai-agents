---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-20-session-99923-f79e70c01-review-pr-5175-pr-autofix-tier-field-contract.json
qaCommit: c2d32bf478e1005a4fa96902f92f595e65528313
---

# QA Report: session 99923, pr-autofix tier field contract

- Issue: #5094
- PR: #5176
- Session log: `.agents/sessions/2026-08-20-session-99923-f79e70c01-review-pr-5175-pr-autofix-tier-field-contract.json`
- QA commit: `c2d32bf478e1005a4fa96902f92f595e65528313`
- Branch: `claude/pr-5175-review-v21yk2`

## Verdict

PASS.

## Scope under test

One-line behavior change in `.claude/commands/pr-autofix.md` (tier read moved
from `.Data.Tier` to `.Tier`), its generated mirror in
`src/copilot-cli/skills/pr-autofix/SKILL.md`, and the static gate split across
`tests/commands/pr_autofix_field_parser.py` and
`tests/commands/test_pr_autofix_field_contract.py`.

## Evidence

### Defect reproduced before the fix

`test_pr_merge_ready.py` declares no `--output-format` argument and emits its
payload with `print(json.dumps(result, indent=2))` at line 1226, building
`result` as a flat dict literal with `result["Tier"]` assigned at line 1091.
There is no `Data` envelope, so `jq -r '.Data.Tier // "UNKNOWN"'` resolved to
null on every call and `TIER` was unconditionally `UNKNOWN`. That disabled the
T3/T4 branch of the round-cap circuit breaker and the non-T1 branch of the
auto-merge disarm gate.

### Negative control: the shipped fix

Reverted the fix in both the source command and the generated mirror, then
re-ran the suite. Three tests failed, naming the source contract, the mirror
contract, and the pinned tier regression:

```
FAILED test_source_command_has_no_contract_violations
FAILED test_copilot_mirror_has_no_contract_violations
FAILED test_tier_read_targets_the_authoritative_flat_producer
3 failed, 29 passed
```

Restored the fix; 32 passed.

### Negative control: the originally reported shape

Spec validation on PR #5176 found the first version of the gate did not catch
the defect issue #5094 actually reported: field names were checked only for
flat producers, so `.Data.tier` from `check_pr_live_state.py` passed clean.
Confirmed, then fixed. The gate now reports:

```
line 1: reads `.Data.tier` from check_pr_live_state.py, which emits no `tier`
field. Known fields: action, base_ref, base_sha, closed, head_ref, head_sha,
is_draft, merged, owner, pull_request, reason, repo, state, success,
superseded_by_base.
```

### Derivation bug caught before it shipped

Running the new wrapped-producer derivation against all 16 reads before wiring
it in showed `.Data.auto_merge_method` failing as a phantom field.
`get_pr_context.py` builds its payload as `data: dict[str, object] = {...}`,
an `ast.AnnAssign`, and the walker handled only `ast.Assign`, yielding 3 keys
instead of 30. Fixed, and pinned by
`test_annotated_payload_assignment_is_derived`. This was a false positive on a
valid read, so it would have failed CI rather than passing silently, but it was
found by measurement rather than by a test.

### Mutation test of the blind-spot guard

`test_extractor_reaches_every_jq_invocation` exists so a read the extractor
never parsed fails loudly instead of leaving the suite green. Its first version
reused `_JQ_PROGRAM`, the extractor's own regex. Mutating that pattern to match
nothing blinded the extractor and the guard together: the guard passed
vacuously, certifying the blindness it exists to catch.

Decoupled the guard onto `_JQ_TOKEN`, which only spots the word `jq`. Re-ran
the same mutation:

```
FAILED test_extractor_reaches_every_jq_invocation
  line 299: late_reason=$(printf '%s' "$late_live" | jq -r '.Data.reason ...
  line 423: ROUND_REASON=$(echo "$ROUND_CAP" | jq -r '.Data.reason ...
```

The guard now fails and names the missed lines. Restored; 32 passed.

### Test results

| Command | Result |
|---|---|
| `uv run pytest tests/commands/test_pr_autofix_field_contract.py` | 32 passed |
| `uv run pytest tests/commands/ tests/skills/pr-autofix/` | 400 passed, 1 skipped |
| pr-autofix behavioral suites plus `tests/commands/` | 462 passed, 1 skipped |
| `uv run ruff check tests/commands/` | All checks passed |
| `uv run python build/scripts/build_all.py --check` | no staleness |
| `uv run python scripts/validation/pre_pr.py` | All validations passed |

### Coverage shape

Positive, negative, and edge cases are all present, per
`.agents/governance/TESTING-RIGOR.md`:

- Positive: source and mirror both clean; mirror reads equal source reads; the
  tier read is pinned to the authoritative producer and the envelope-free path.
- Negative controls: a `Data.` prefix on a flat producer, an unknown field on a
  flat producer, a missing `Data.` prefix on a wrapped producer, an unknown
  field on a wrapped producer (the issue's verbatim shape), a violation reached
  through a captured shell variable, and a violation in the second path of a
  multi-path jq program. One further test asserts that correct reads yield no
  findings, so a check that failed everything would not read as strict.
- Edge: backslash-continuation joining, first-physical-line reporting, comment
  lines excluded, literal `//` defaults not read as paths, and a read with no
  producer in scope reported as unbound.
- Coverage guards: every read binds to a producer, the extractor reaches every
  jq invocation, wrapped payload keys are derivable (so the field check cannot
  pass by short-circuiting), and the annotated-assignment form resolves.

### Audit of the remaining reads

All 16 jq reads in the command body bind to a producer, zero unbound, and every
jq invocation line was parsed. The other 15 were already correct: 13
`Data`-wrapped reads against `check_pr_live_state.py`, `pr_autofix_lease.py`,
`check_pr_round_cap.py`, and `get_pr_context.py`, plus a flat `.merged` read
against `test_pr_merged.py`. Each now has its field name verified against the
producer's derived schema, not only its envelope level.

## Known limits

Stated rather than claimed clean, per the clear-the-gate-or-drop-the-claim rule:

1. **No behavioral verification of the two re-armed gates.** Proving the T3/T4
   round-cap and non-T1 auto-merge branches actually execute with the parsed
   tier needs the live PR loop, not a static gate. Both branches have been inert
   for as long as the defect existed, so their first live runs are the real
   test. Spec validation raised this; it is deliberately out of scope here and
   flagged in the PR's review focus areas.
2. `_calls_data_emitter` is module-wide, not path-sensitive. A producer that
   wrapped only its error branch while printing flat on success would be
   misclassified. None of the six producers in play does this.
3. `_keys_bound_to` unions module-wide, so a second same-named dict in another
   function would widen the accepted field set. Checked: no producer in play has
   one.

## Second hardening pass

Spec validation raised two fail-open paths after the first pass. Both fixed and
mutation-verified:

1. `_field_violation` stood down whenever `top_level_keys` was None, and nothing
   required the producers in use to be decidable. Forcing derivation to return
   None now fails 5 tests, `test_every_consumed_producer_has_derivable_keys`
   among them; before the fix the suite stayed green.
2. The invocation-coverage guard compared line presence, so a line running two
   jq commands where only the first parsed counted as reached. Now compares
   per-line counts. Measured on such a line: 2 invocations, 1 path parsed, guard
   fires.

## Third hardening pass

Spec validation found the invocation-coverage guard could still be masked, and
it was right. The guard compared parsed paths against jq invocation count, but a
program may name several paths, so one well-parsed invocation supplies enough
paths to cover for a sibling the parser never read.

Reproduced: `jq -r '.Data.action // .Data.reason'` beside an unparseable
`jq -r ".Data.$field"` gives 2 invocations, 2 paths, 1 program. The old
comparison read the line as fully reached while the second command went
unchecked. Same shape as the previous round's line-presence bug, one level down.

Now compares programs to invocations, plus a check that every program read
yields a path. Verified by mutation: restoring the path-count comparison fails
exactly `test_a_multi_path_program_cannot_mask_an_unparsed_sibling`.

Worth recording as a pattern: three rounds of this guard each failed the same
way, by choosing a comparison that a sibling could balance out. Presence, then
path count, then programs. Each fix was verified by putting the old form back
and watching a named test fail.
