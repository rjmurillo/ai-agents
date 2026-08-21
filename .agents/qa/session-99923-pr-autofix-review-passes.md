# Review passes: session 99923, pr-autofix tier field contract

Companion to `session-99923-pr-autofix-tier-field-contract.md`, which carries the
verdict, the scope, the primary controls, and the known limits. This file carries
the chronological record of what review found after the first PASS and what each
finding cost to close.

Split out when the combined report crossed the 500-line taste rule, on the seam
that was already there: the report proper answers "does this change work", these
passes answer "what did we get wrong on the way". Refs #5094, PR #5176.

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
   which fails every case that runs the block; the only survivors are the
   fake-shape cases, which never spawn `bash`. Measured 22 of 22 at that
   revision, and stated as the property because the count moves on every commit
   that adds a case.
2. **The negative control mutated with an unbounded replace after an `in`
   check.** A second identical read would have hit both sites, so the control
   would no longer isolate the defect it is named for. Now requires exactly one
   occurrence and replaces one. Verified by duplicating the tier read in the
   command: the control fails with `assert 2 == 1` instead of silently mutating
   two sites.

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

### Twelfth pass: two gaps a subagent fleet found that no bot had

Five subagents reviewed the diff in parallel. Two returned findings that
changed the merge decision; both are gaps in the runtime harness, and both are
mine.

**The disarm call's flags were never asserted.** The fake
`set_pr_auto_merge.py` appended to a log and ignored `argv`, so `run.disarmed`
proved a call happened and said nothing about what was asked for. Verified
before fixing: flipping `--disable` to `--enable` in the shipped command left
the whole suite green at 429 passed. That mutation turns the gate that strips
auto-merge from a non-T1 PR into one that arms it immediately before a push,
which is the exact outcome issue #3913's gate exists to prevent. The fake now
records its argument vector and the disarm case asserts `--disable` is present
and `--enable` is not.

**A per-PR skip was indistinguishable from a queue abort.** The harness looped
over one PR, so `continue`, `break`, and `exit 0` were observationally
identical to every accessor: the gate's message printed, cleanup ran, and the
shell exited 0 because the shared helper requires exactly that. Four mutants
across the terminating arms survived. The harness now walks a two-PR queue and
every terminating arm asserts the second PR was still visited.

The second fix was wrong on its first attempt, and the way it was wrong is the
point. It printed a marker after `done` and asserted that; `break` still
reaches that marker, so the `break` mutant survived the fix written to kill it.
Only re-running the control caught it. That is the same unit-narrower-than-the-
claim mistake this whole PR is about, committed while closing an instance of
it, which is now three occasions in this branch where the fix reproduced the
defect it was fixing.

Controls at the current head:

```
--disable -> --enable        1 failed, 39 passed
SKIP continue -> break       1 failed, 39 passed
SKIP continue -> exit 0      1 failed, 39 passed
reword a comment (inverted)  40 passed
```

Adding those assertions put the runtime module over the 500-line taste rule,
so the harness moved to `pr_autofix_dispatch_harness.py`, following the parser
precedent: that module is the machinery, this one is the cases. 276 and 277
lines. Controls re-run after the split to confirm the move lost nothing:

```
--disable -> --enable          1 failed, 39 passed
SKIP continue -> break         1 failed, 39 passed
SKIP continue -> exit 0        1 failed, 39 passed
restore the pre-fix read      15 failed, 25 passed
reword a comment (inverted)   40 passed
```

**Also observed, not fixed here.** Running `pytest tests/commands/` regenerates
`src/copilot-cli/skills/pr-autofix/SKILL.md` in the working tree. It propagated
a mutation from the source into the tracked mirror during these controls, and
it means a mirror-drift failure turns green on a re-run, destroying the
evidence. That is a sibling test's behavior, older and wider than this change,
so it belongs in its own PR rather than as an addendum here.
