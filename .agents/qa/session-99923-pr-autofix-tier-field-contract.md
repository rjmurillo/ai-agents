---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-20-session-99923-f79e70c01-review-pr-5175-pr-autofix-tier-field-contract.json
qaCommit: e2e5ab1f8b443f097f4e355ef21240212b3e13e2
---

# QA Report: session 99923, pr-autofix tier field contract

- Issue: #5094
- PR: #5176
- Session log: `.agents/sessions/2026-08-20-session-99923-f79e70c01-review-pr-5175-pr-autofix-tier-field-contract.json`
- QA commit: `e2e5ab1f8b443f097f4e355ef21240212b3e13e2`
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

### Fourth pass: the gap I declared unreachable was reachable

The first three passes shipped a known limit saying behavioral verification of
the two gates "needs the live PR loop, not a static gate", and the PR asked
reviewers to accept that. Copilot's second review filed it as a suppressed
finding and named the counter-evidence: `tests/test_pr_autofix_late_live_state_gate.py`
already extracts a block from this same command between marker comments, writes
fake producer scripts into a temp `$SCRIPTS_DIR`, and runs the block under
`bash -c`, parameterized over the source and the generated mirror.

Checked the premise before acting on it. `_extract_guard` at `:38-43` pulls the
text between `# late-live-state-guard:start` and `:end`; `_write_fake_scripts`
at `:54` writes a stand-in `check_pr_live_state.py`; `_run_race` at `:238-352`
assembles the harness and calls `subprocess.run(["bash", "-c", harness], ...)`.
So the claim was false: the pattern existed in this repository, one directory up
from the tests I was writing, and I asserted its absence without looking.

Closed rather than re-argued. The tier-dispatch block now carries
`# tier-dispatch:start` / `:end` markers, and
`tests/commands/test_pr_autofix_tier_dispatch_runtime.py` runs it against fake
producers for both docs: 24 cases covering T1-armed, T3 and T4 round-cap entry,
round-cap escalation stopping before the disarm gate, unarmed PRs, unreadable
auto-merge state, mutation exit 75 versus a real failure, and a dead tier
producer.

Controls, each verified by putting the defect or a mutant back:

| Mutation | Result |
|---|---|
| Restore `.Data.Tier` in source and mirror | 10 failed, 14 passed |
| Disarm gate loses its T1 exemption (`!= T1` to `!= T9`) | 2 failed |
| Round-cap breaker made inert (`T3`/`T4` test to `false`) | 6 failed |
| Reword a comment inside the block (inverted control, must survive) | 24 passed |

The inverted control is there because a harness whose mutants are all one
polarity cannot tell "every mutant died" from "this fails no matter what"
(testing rule MUST-11). Note also what the restore control did to the
negative-control test itself: rather than passing vacuously against a tree with
the defect already in it, it failed on its own guard.

Copilot then found two holes in that harness, both real and both closed:

1. **Only one case checked the shell's exit status.** A log file that exists or
   a string in stdout proves a branch ran; it does not prove the block finished,
   so a shell error after the observed effect would leave a case green. The
   shared helper now asserts exit 0 and empty stderr for every case. Measured
   first: all nine input shapes exit 0 with empty stderr, including the ones
   that `continue`. Verified by injecting an unset variable under `set -u`,
   which fails 22 of the 22 cases that run the block; the two that still pass
   are the shape guard, which never spawns `bash`.
2. **The negative control mutated with an unbounded replace after an `in`
   check.** A second identical read would have hit both sites, so the control
   would no longer isolate the defect it is named for. Now requires exactly one
   occurrence and replaces one. Verified by duplicating the tier read in the
   command: the control fails with `assert 2 == 1` instead of silently mutating
   two sites.

Two of those controls assert behavior the static gate cannot see at all. The
round-cap breaker firing on T3 and T4, and the T1 PR keeping the auto-merge it
earned, are properties of the shell conditions, not of the `jq` path.

### Fifth pass: the same aggregate bug, a fourth time

Copilot found that `extract_field_reads` bound every path on a logical line to
the first producer on that line. A line running two producer pipelines had its
second read checked against the first producer's schema, so a real mismatch
there could pass. The invocation-coverage guard deliberately permits several jq
commands per line, so the two together made the hole reachable rather than
theoretical.

This is the fourth instance of one shape in this PR: an aggregate over the line
where the unit that must be checked is the invocation. Presence, then path
count, then programs, and now the producer binding.

Fixed by pairing each jq program with the text that actually feeds it, the
window between the previous program and this one, with the nearer of a direct
invocation and a captured-variable reference winning inside that window. The
tie-break matters: `X=$(a.py); printf '%s' "$LIVE" | jq` feeds the jq from
`$LIVE`, so taking the last producer on the line would mis-bind it to `a.py`.

Two regression cases added, and verified by restoring the per-line binding:

```
FAILED test_two_producers_on_one_line_each_bind_to_their_own_jq
FAILED test_a_captured_variable_nearer_the_jq_wins_over_an_earlier_producer
2 failed, 32 passed
```

Restored; the suite passes. The 16 reads in the real command body bind exactly as
before, so this widens what the gate can catch without moving what it currently
reports.

### Sixth pass: recognized is not actionable

Widening the guard to the producer's declared set put `SKIP` on the acting
path. The command's own tier table reads
`| SKIP | Draft, merged, or closed | No action |`, so a `SKIP` reaching the
disarm gate satisfies `TIER != T1` and strips auto-merge from a PR that went
draft, merged, or closed after the live-state gate ran. Copilot caught it.

Two properties, separated rather than merged: recognition must equal
`_TIER_ORDER`, and dispatch must equal that set minus `SKIP`, which now has its
own terminating arm. `recognized_tiers` reads every arm, `dispatched_tiers`
reads only the pass-through arm, and both are compared against the producer
over source and mirror.

Control, restated after re-running it at this head. An earlier version of this
line said "putting `SKIP` back on the pass-through arm fails exactly four
tests, two static and two runtime". Re-run, that mutation fails only the two
static ones. `case` takes the first matching arm, so a `SKIP)` arm left above
the pass-through arm still matches first and runtime behavior does not change.
The four-failure result needs the whole pre-fix shape, the `SKIP)` arm deleted
*and* `SKIP` added to the pass-through arm:

```
FAILED test_pr_autofix_tier_contract.py::test_skip_is_recognized_but_never_dispatched[doc0]
FAILED test_pr_autofix_tier_contract.py::test_skip_is_recognized_but_never_dispatched[doc1]
FAILED test_pr_autofix_tier_dispatch_runtime.py::test_skip_terminates_instead_of_reaching_the_disarm_gate[.claude/commands/pr-autofix.md]
FAILED test_pr_autofix_tier_dispatch_runtime.py::test_skip_terminates_instead_of_reaching_the_disarm_gate[src/copilot-cli/skills/pr-autofix/SKILL.md]
4 failed, 75 passed
```

Restored; 79 passed. The correction is the point: a control that names one
mutation and reports another mutation's result is not evidence about either.

### Seventh pass: the split, and what it did not change

`taste-lints` reported two files over the 500-line rule. The tier extractors
moved from `pr_autofix_field_parser.py` into `pr_autofix_tier_parser.py`, and
the two tier tests from `test_pr_autofix_field_contract.py` into
`test_pr_autofix_tier_contract.py`. Pure code motion, verified as such: 422
tests collected under `tests/commands/` before the split and 422 after, and
`taste-lints` now reports 0 errors across all five files (three warnings, all
"approaching size limit"). Line counts: 449, 103, 454, 79, 480.

The split still carried one defect, and it is the shape this PR already fixed
once. `_TIER_ARM` moved into the new module although `recognized_tiers` had
stopped using it when it switched to walking lines by hand, leaving an untested
alternate matching rule behind, exactly as `_bound_source` did earlier. Cursor
Bugbot found it on the split commit. Confirmed dead two ways before deleting:
a repository search returns one occurrence, the definition, and deleting it
leaves all 79 tests passing. What I checked when moving the code was line
counts; what a move actually needs checking for is what the moved code still
uses.

The deletion on the branch is Bugbot's autofix commit, not mine. Its agent
pushed `b933155a5` while I was committing the identical three-line removal
locally; I reset onto its commit and dropped my duplicate, the same resolution
used for the three earlier collisions on this branch. `qaCommit` is bound to
that commit because it is the head the measurements above were taken at.

### Eighth pass: the corrected claim had two survivors

"Corrected in all five artifacts" was true of the five artifacts I looked at
and false as a statement about the repository. Copilot found the original
backwards claim still standing in two more places on the merged head: the
envelope violation message in `pr_autofix_field_parser.py` ended "the gate
never gates", and the module docstring of `test_pr_autofix_field_contract.py`
said "the gate just stops gating" three lines above the truth table that
refutes it.

Verified the premise before fixing, per the reviewer-findings discipline this
branch just merged: the disarm gate is `[ "$TIER" != "T1" ]`, so a sentinel
makes it fire on every input rather than never. Copilot's reading is correct
and mine was the same overgeneralization a third and fourth time.

Both now describe the fallback instead of predicting the branch. Changing the
message is safe because the tests pin the identifying substrings, `flat object
with no Data envelope` and `wraps its payload in a Data envelope`, not the
explanatory tail; a grep for the old wording now returns nothing.

The transferable part is the shape of the mistake, not the wording. A claim
corrected in the artifacts you happen to be editing is corrected in those
artifacts. Closing it means grepping the phrase across the tree, which is what
found nothing this time only because Copilot had already done it.

### Ninth pass: the coverage guards only covered the source

Copilot found `test_extractor_reaches_every_jq_invocation` running against
`COMMAND_PATH` alone. The suite claims source-and-mirror coverage, but the two
mirror checks both compare only reads the extractor already found:
`contract_violations` inspects extracted reads, and
`test_mirror_reads_match_source_reads` compares two extracted lists. An
invocation neither side parses is absent from both lists, so the lists agree
and nothing fails. The one guard written to catch extractor blindness never
looked at the mirror.

Verified the premise, then checked its siblings rather than only the reported
instance. `test_every_read_binds_to_a_producer` and
`test_every_consumed_producer_has_derivable_keys` took the same source-only
fixture and had the same hole. All three are now parameterized over both
shipped documents.

Control: inject a double-quoted `jq` program into the mirror only, which
`_JQ_TOKEN` sees and `_JQ_PROGRAM` cannot parse. The mirror case fails and the
source case passes on the same tree:

```
FAILED test_extractor_reaches_every_jq_invocation[doc1]
1 failed, 1 passed
```

Before the change that same injection produced no failure at all. Restored;
mirror byte-identical, 82 passed.

This is the sixth instance in this PR of one shape: a check whose unit is
narrower than the claim it backs. Presence, then path count, then programs,
then producer binding, then recognized-versus-dispatched, and now source
without mirror.

### Tenth pass: counts in prose keep outrunning the suite

Copilot found three stale figures in one review, all the same shape and all
mine: the revert control said 35 passed when the file had 38, the runtime
harness comment claimed "22 of the 22 cases that run the block fail" when the
current answer is 38 of 38, and the session log described the runtime suite as
covering "every tier in `_TIER_ORDER` dispatching", which is the opposite of
the `SKIP` behavior this PR shipped.

All three re-run and corrected. The unset-variable injection now fails 38 and
spares 2:

```
38 failed, 2 passed
```

The durable repair is not the new numbers. It is that the runtime comment no
longer carries any: it states the property, that every case spawning bash fails
and only the fake-shape cases survive, which stays true as cases are added. The
session log had already dropped its per-suite counts for this reason and still
carried a behavioral description that drifted, so the lesson generalizes past
counts to any restatement of what the code does.

This is the seventh instance of the PR's recurring shape, and the most
embarrassing, because the fix for it was already written down here and applied
to only one of the three surfaces that needed it.

### Eleventh pass: three more source-only guards

Spec validation went PARTIAL and named two guards the previous pass had left
on the source-only fixture, `test_every_consumed_producer_has_a_pinned_envelope`
and `test_extractor_finds_reads_for_every_producer_style`. Both real. Grepping
`command_body` rather than fixing the two reported turned up a third nobody had
named, `test_tier_read_targets_the_authoritative_flat_producer`, which was
covered only transitively through the read-equality test.

All three now run over both docs. The two remaining uses of the source-only
fixture are legitimate and were checked rather than assumed:
`test_source_command_has_no_contract_violations` has an explicit mirror twin,
and `test_mirror_reads_match_source_reads` reads both by construction.

Control, the one spec validation asked for: a mirror-only read of a producer
absent from the envelope pins.

```
FAILED test_every_consumed_producer_has_a_pinned_envelope[doc1]
1 failed, 3 passed
```

Restored; mirror byte-identical.

That this is a second round of the same fix is the finding. The previous pass
parameterized the three guards a reviewer had pointed at and stopped there,
which is the same "corrected where I was looking" failure recorded two passes
earlier. Doing it by grep instead of by report closed five guards and found the
one no reviewer had seen.

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
