---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-20-session-99923-f79e70c01-review-pr-5175-pr-autofix-tier-field-contract.json
qaCommit: d9068f9d708bdf4effea2fceccdf579310477301
---

# QA Report: session 99923, pr-autofix tier field contract

- Issue: #5094
- PR: #5176
- Session log: `.agents/sessions/2026-08-20-session-99923-f79e70c01-review-pr-5175-pr-autofix-tier-field-contract.json`
- QA commit: `d9068f9d708bdf4effea2fceccdf579310477301`
- Branch: `claude/pr-5175-review-v21yk2`

## Verdict

PASS.

## Scope under test

One-line behavior change in `.claude/commands/pr-autofix.md` (tier read moved
from `.Data.Tier` to `.Tier`) plus tier-dispatch marker comments, its generated
mirror in `src/copilot-cli/skills/pr-autofix/SKILL.md`, two static gates and
their parsers (`pr_autofix_field_parser.py` with
`test_pr_autofix_field_contract.py` for the jq reads,
`pr_autofix_tier_parser.py` with `test_pr_autofix_tier_contract.py` for the
tier set), and the runtime suite in
`tests/commands/test_pr_autofix_tier_dispatch_runtime.py`. All under
`tests/commands/`.

## Evidence

### Defect reproduced before the fix

`test_pr_merge_ready.py` declares no `--output-format` argument and emits its
payload with `print(json.dumps(result, indent=2))` at line 1226, building
`result` as a flat dict literal with `result["Tier"]` assigned at line 1091.
There is no `Data` envelope, so `jq -r '.Data.Tier // "UNKNOWN"'` resolved to
null on every call and `TIER` was unconditionally `UNKNOWN`.

A stuck sentinel does not fail one way. It fails whichever way each comparison
reads it, and the two downstream gates compare it in opposite directions:

| Gate | Condition | `TIER=UNKNOWN` before the fix | After the fix |
|---|---|---|---|
| Round-cap circuit breaker | `TIER = T3` or `TIER = T4` | never fired: the breaker was inert | fires on real T3/T4 |
| Auto-merge disarm | `TIER != T1` | fired on **every** armed PR | spares genuine T1 |

Both conditions live between the `# tier-dispatch:start` and `:end` markers in
`.claude/commands/pr-autofix.md`. Earlier drafts of this table cited absolute
line numbers, and adding the markers moved both by four; the markers are the
stable anchor and the runtime suite extracts on them, so cite those instead.

So one gate was off and the other was stuck on, stripping auto-merge from
legitimately land-ready T1 PRs. The first version of this report, the PR body,
the command comment, and the test docstring all described both as "disabled".
That is correct for the breaker and backwards for the disarm gate. Copilot
caught it in review on PR #5176; corrected in all five artifacts.

### Negative control: the shipped fix

Reverted the fix in both the source command and the generated mirror, then
re-ran the suite. Three tests failed, naming the source contract, the mirror
contract, and the pinned tier regression:

```
FAILED test_source_command_has_no_contract_violations
FAILED test_copilot_mirror_has_no_contract_violations
FAILED test_tier_read_targets_the_authoritative_flat_producer
3 failed, 35 passed
```

Restored the fix; 38 passed. Re-run at this head rather than carried forward,
because the suite keeps growing and these totals keep going stale: they were
written as 36, then 32, and Copilot caught the third drift. The three failing
names are the durable part of this control; the totals are only there to show
the run was real.

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

The guard now fails and names the missed lines. Restored; the suite passes.

### Test results

| Command | Result |
|---|---|
| `uv run pytest tests/commands/test_pr_autofix_field_contract.py` | 38 passed |
| `uv run pytest tests/commands/test_pr_autofix_tier_contract.py` | 4 passed |
| `uv run pytest tests/commands/test_pr_autofix_tier_dispatch_runtime.py` | 40 passed |
| `uv run pytest tests/commands/ tests/skills/pr-autofix/` | 450 passed, 1 skipped |
| the four `tests/test_pr_autofix_*.py` files plus `tests/commands/ tests/skills/pr-autofix/` | 688 passed, 1 skipped |
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

### Review passes

Eight further rounds of review found real defects after the first PASS, several
of them mine and several the same shape twice. They are recorded in
`session-99923-pr-autofix-review-passes.md`, split out when this file crossed
the 500-line taste rule.

## Known limits

Stated rather than claimed clean, per the clear-the-gate-or-drop-the-claim rule:

1. **`--is-bot` is never passed, so bot PRs mis-tier.** Copilot found this on
   PR #5176 and it is real. The command's own tier contract says "Pass
   `--is-bot` when the PR author is a bot" and defines T5 as a bot PR with any
   failure or threads; `classify_tier` returns T5 only when `is_bot` is true.
   The TIER invocation passes no such flag, so bot PRs now classify T2 to T4 and
   a bot PR with threads enters the T3/T4 round-cap flow instead of the
   documented individual handling. This was latent before the fix, because no
   tier dispatch happened at all.

   Not closed here, and the reason is size rather than doubt. Copilot suggested
   "preserve the Phase 1 bot flag", but no such flag exists anywhere in the
   command. `get_pr_context.py` does emit `author`, but only as a login string
   with no bot marker, and `CTX` is fetched *after* the TIER call. Closing this
   needs either a producer change (emit an author type or `is_bot`) or a login
   heuristic, plus reordering the fetch, plus a new read for the contract gate
   to cover. That is a behavior change to tier dispatch in an autonomous PR
   loop, so it belongs in its own change with its own review.
2. `_calls_data_emitter` is module-wide, not path-sensitive. A producer that
   wrapped only its error branch while printing flat on success would be
   misclassified. None of the six producers in play does this.
3. `_keys_bound_to` unions module-wide, so a second same-named dict in another
   function would widen the accepted field set. Checked: no producer in play has
   one.
4. The runtime suite fakes the four producers. It proves what the block does
   with a given tier, round-cap verdict, and auto-merge state; it does not prove
   the real producers return those shapes. The contract gate covers that half,
   and one test in the runtime module asserts the fake tier producer still
   matches the real one's flat, envelope-free output.
5. **Only the first path segment is checked.** `_field_violation` reduces the
   read to `path.lstrip(".").split(".")[0]`, so `.Data.superseded_by_base.fully_superseded`
   is validated on `superseded_by_base` alone and a renamed nested key would
   pass. Raised by spec validation on PR #5176 and confirmed by reading
   `_field_violation` in `pr_autofix_field_parser.py`, cited by symbol because
   this report has already carried two line numbers that went stale inside the
   commit that moved them. Not closed here: checking nested keys means
   deriving the shape of a nested literal, which is a different and larger piece
   of derivation than the top-level union this gate does. The reported defect
   class is a first-segment mismatch in both of its instances, so the gate
   covers what it was built for; this is the next layer, not a hole in this one.
6. **One command body.** The gate is bound to `pr-autofix.md` and its mirror.
   Sibling command bodies run the same producers through `jq` and can carry the
   same defect class. Also raised by spec validation. Closing it repo-wide is
   the ocean next to this PR's lake, and the parser is a module precisely so a
   later change can point it at other bodies.

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
