---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-20-session-99923-f79e70c01-review-pr-5175-pr-autofix-tier-field-contract.json
qaCommit: aee342eb91f8eba75541ab9a133870504e68a15b
---

# QA Report: session 99923, pr-autofix tier field contract

- Issue: #5094
- PR: #5176
- Session log: `.agents/sessions/2026-08-20-session-99923-f79e70c01-review-pr-5175-pr-autofix-tier-field-contract.json`
- QA commit: `aee342eb91f8eba75541ab9a133870504e68a15b`
- Branch: `claude/pr-5175-review-v21yk2`

## Verdict

PASS.

## Scope under test

Four behavior changes in `.claude/commands/pr-autofix.md`, plus tier-dispatch
marker comments, and its generated mirror in
`src/copilot-cli/skills/pr-autofix/SKILL.md`:

1. The tier read moves from `.Data.Tier` to `.Tier`, the reported defect.
2. A fail-closed guard skips a PR whose tier the producer never declared, with
   `SKIP` given its own terminating arm because recognized and actionable are
   different questions.
3. The auto-merge disarm gate spares a T1 only when `fetched_pages_complete` is
   the boolean `true`, so a tier derived from a truncated fetch does not keep
   auto-merge.
4. That gate now runs before the round-cap breaker, so a PR the breaker
   escalates to a human is disarmed on the way out.

Three of the four are consequences of the first: correcting the tier read is
what makes those paths reachable, so they are mirror obligations rather than
adjacent work. That reasoning is set out in "The fix opened a case" below.

The tests are three support modules under `tests/commands/`, each paired with the
cases that drive it: `pr_autofix_field_parser.py` with
`test_pr_autofix_field_contract.py` and `test_pr_autofix_coverage_guards.py` for
the jq reads and the guards on that checker; `pr_autofix_tier_parser.py` with
`test_pr_autofix_tier_contract.py` for the tier set; and
`pr_autofix_dispatch_harness.py` with `test_pr_autofix_tier_dispatch_runtime.py`
and `test_pr_autofix_earned_t1_exemption.py` for the runtime behavior.

This section has now gone stale twice, and the second time is the interesting
one. First it described the one-line fix and three modules, so the PASS verdict
was recorded against less work than the PR changed. The repair restated the
scope as "six modules", which was accurate when written and wrong two commits
later when the 500-line taste rule split two more out; Copilot caught both. The
count is gone rather than corrected a third time, which is Finding 5 of the
retrospective applied here: a count is a fact about a moment, and the pairing
above is a fact about the tree that a reader can check against `git diff
--name-only`.

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
| Auto-merge disarm | `TIER != T1` | fired on **every** armed PR | spares a T1 only when the fetch behind it was complete |

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

Every command below exited 0 at the head this report is bound to, with no
failures and no errors.

| Command | Result |
|---|---|
| `uv run pytest tests/commands/test_pr_autofix_field_contract.py` | all pass |
| `uv run pytest tests/commands/test_pr_autofix_coverage_guards.py` | all pass |
| `uv run pytest tests/commands/test_pr_autofix_tier_contract.py` | all pass |
| `uv run pytest tests/commands/test_pr_autofix_tier_dispatch_runtime.py` | all pass |
| `uv run pytest tests/commands/test_pr_autofix_earned_t1_exemption.py` | all pass |
| `uv run pytest tests/commands/ tests/skills/pr-autofix/` | all pass |
| the four `tests/test_pr_autofix_*.py` files plus the two directories above | all pass |
| `uv run ruff check tests/commands/` | All checks passed |
| `uv run python build/scripts/build_all.py --check` | no staleness |
| `uv run python scripts/validation/pre_pr.py` | All validations passed |

**Why no pass counts.** They were here and went stale four times: carried
across a file split so a row described a file that no longer had those cases,
then again on each commit that added one, and Copilot caught the last two. The
PR body already applies this rule everywhere else and names this report as the
one place counts were still allowed, which is what kept the failure alive. A
count is a fact about a moment; the property that every command exits 0 is a
fact about the head, and re-running the table checks it either way.

Counts still belong in a mutation control, where the number *is* the finding
("fails 4, and only those 4"), and those are measured per run and quoted with
the mutation that produced them.

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

Every round of review after the first PASS found real defects, several of them
mine and several the same shape twice. Count the headings in the companions
rather than trusting a number here, because this sentence carried one and it
went stale on the next round, which Copilot caught.

Two companions, both split out when a file crossed the 500-line taste rule:
`session-99923-pr-autofix-review-passes.md` holds the numbered passes in order,
where the recurring theme is a coverage gate narrower than its claim, and
`session-99923-pr-autofix-later-findings.md` holds what came after them, where
the theme is the fix opening a case or breaking something.

### The fix opened a case, so the fix closes it

A silent-failure pass over the whole command body raised five reads outside this
diff. Four are genuinely separate; one is not, and the difference is what makes
it belong here.

`classify_tier` returns T1 on `CanMerge` alone
(`test_pr_merge_ready.py`, `classify_tier`), and `CanMerge` is
`len(reasons) == 0` with `fetched_pages_complete` computed on the following line
and never appended to `reasons` (`check_merge_readiness`). So a fetch truncated
at the pagination cap that happens to surface no unresolved thread and no
failing required check classifies T1. The producer's own module docstring says
so: "a partial fetch that happens to find no failing checks is not evidence that
no failing checks exist."

That was covered by accident before this PR. With `TIER` pinned at `UNKNOWN`,
`TIER != T1` held for every PR, so the disarm gate stripped auto-merge from the
truncated-fetch PR along with everything else. Making T1 reachable removes the
accident. The verification that matters is the direction: this is not an
adjacent defect found while passing by, it is a case this PR's own fix exposes,
which is the mirror obligation rather than a follow-up.

The gate now asks "provably T1" instead of "T1", and only that. It never stops
work on any tier; it declines to *spare* auto-merge on unproven evidence.
Anything other than the literal `true` denies the exemption, so a producer
predating the field cannot buy a merge by omitting it.
`.claude/commands/pr-review-config.yaml` already ANDs the same field into its
completion-gate criterion, so this applies one existing rule at the other place
a merge can be armed rather than inventing a policy.

Controls, each counting occurrences before patching and asserting a
byte-identical restore, over source and mirror together:

| Mutation | Result |
|---|---|
| baseline | 93 passed |
| Guard removed, back to the bare `!= T1` test | 4 failed |
| Missing field defaulted to `true` (fail open) | 4 failed |
| Completeness alone grants the exemption | 8 failed |
| restored | 93 passed |

**Caught in the same change, by the suite.** Rewriting the read to capture the
producer once, I put `2>/dev/null` on both `jq` calls. The producer's stderr is
already suppressed, so a `jq` parse error is the only signal an operator gets
that the output was unreadable, and both guards would otherwise skip the PR
with no explanation. The malformed-producer case failed by name. That is the
same finding (F1 below) committed while fixing a sibling of it, which is the
third time this PR has produced an instance of the pattern it is closing.

### Flagged, not fixed

Per see-something-say-something. All four are pre-existing on `origin/main` and
none is opened by this change.

| # | Finding | Verdict | Severity |
|---|---|---|---|
| F1 | The producer's stderr is discarded on both `test_pr_merge_ready.py` and `get_pr_context.py` calls | Real | Low. Both reads fall through to an explicit empty-check, so the loop skips rather than acting wrong. Diagnostic only. |
| F2 | `check_pr_round_cap.py` emits `escalation_posted`, and the command never reads it | Real | Medium. The command's comment says the script "already posted a human-readable PR comment", but that POST is caught as non-fatal, so the escalation note can be silently absent while the loop stops anyway. |
| F3 | The round-cap read cannot tell a crash from a malformed reply from a real API error | Real | Low. All three print the same fallback reason and all three stop the loop, so it fails closed. Diagnostic only. |
| F4 | `auto_merge_method` read with `// "null"` collapses "producer said null" with "read failed" | **Refuted** | The command checks `[ -z "$AUTO_MERGE" ]` separately first. Verified rather than reasoned: `printf '' \| jq -r '.foo // "null"'` emits nothing at all (empty stdin is no document, so `//` never applies), while `printf '{"foo":null}'` emits `null`. The two states are already distinguished. |

F2 and F3 belong in their own change: they read a different producer, neither
has a wrong-mutation path, and this PR already carries a `needs-split` label.

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
5. **Only the first path segment is checked, and this limit is now guarded
   rather than merely stated.** `_field_violation` reduces the read to
   `path.lstrip(".").split(".")[0]`, so a rename below that segment would pass.
   Raised by spec validation on PR #5176.

   The limit is latent, not active, and an earlier draft of this entry got that
   wrong twice over. It claimed `.Data.superseded_by_base.fully_superseded` was
   validated on `superseded_by_base` alone, implying a live unchecked read.
   Measured: all 16 reads in the command body are single-segment, so zero of
   them reach past what the check inspects. That string appears once in the
   command, in a comment at line 378, and the extractor excludes comment lines
   by design, so it was never a read. Two spec-validation runs reasoned from
   that error and marked the criterion partial.

   Closed as prose and reopened as a test.
   `test_no_read_needs_nested_field_checking` asserts, over source and mirror,
   that no read has a segment past the checked one, and its message says to
   extend `_field_violation` first. Control: injecting
   `.Data.superseded_by_base.fully_superseded` as a real read fails `[doc0]`
   and passes `[doc1]`; restored, both pass. Deriving nested literal shapes is
   still the larger job and still deferred, but the day someone needs it, the
   suite says so instead of staying quiet.
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
