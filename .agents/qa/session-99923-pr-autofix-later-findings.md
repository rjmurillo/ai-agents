# Later findings: session 99923, pr-autofix tier field contract

Second companion to `session-99923-pr-autofix-tier-field-contract.md`, which
carries the verdict and the scope. The first companion,
`session-99923-pr-autofix-review-passes.md`, carries the numbered review passes
in order. This file carries what came after them.

Split out for two reasons. The combined file crossed the 500-line taste rule,
and these sections had been inserted between the fourth and fifth passes, which
broke the chronology of a file whose whole organising idea is chronology. The
seam is real: the numbered passes are "the coverage gate kept being narrower
than its claim", while everything here is "the fix opened a case, or the fix
broke something". Refs #5094, PR #5176.

### The inverted control is now a suite member, and it discriminates

Spec validation's one PARTIAL was that the inverted control above was a manual
run recorded here, not a test, so nothing re-ran it as the suite changed
underneath it. It is now
`test_a_comment_reword_changes_nothing`, which runs the block twice for the same
input and asserts the two runs agree on every accessor and byte-for-byte on
stdout. The reword is applied through a new `block_edit` parameter on
`run_dispatch`, under the same exactly-one-occurrence discipline as the tier
read.

A control that always passes is not evidence, so it was shown to fail. Two
attempts, and the first one is the instructive half:

| Edit fed to `block_edit` | Expected | Result |
|---|---|---|
| `# gate ran.` reworded (shipped form) | passes | 2 passed |
| `[ "$TIER" != "T1" ]` to `!= "T9"` | fails | **2 passed** |
| `[ "$AUTO_MERGE" != "null" ]` to `= "null"` | fails | 2 failed on `disarmed` |

The middle row is not a defect in the test. T3 is non-T1 and non-T9 alike, so
for the case this control runs the edit is behavior-preserving by construction,
and a probe that cannot move the thing it measures reports nothing either way.
Reading that row as "the control passed" would have shipped an unproven control;
it took a second edit that genuinely changes the T3-armed outcome to establish
the property. Same unit-narrower-than-the-claim shape as the rest of this PR,
found in my own verification rather than in the code.

The mutation ran under a script that asserted the edit wrote something, purged
`__pycache__` on both sides, and asserted a byte-identical restore afterwards
(testing rules MUST-7 and SHOULD-8).

The first shipped form of the control named a literal comment fragment,
`# gate ran.`, and self-review caught that this couples it to one sentence's
line wrapping: rewrapping the paragraph drops the count to zero and fails the
exactly-one assertion, reporting a defect where nothing changed. It now derives
its target, taking the first unique full-line comment in the extracted block, so
the assertion is the property (editing a comment is inert) rather than one
instance of it. Discrimination was re-run against the derived form with the same
result: shipped edit 2 passed, `!= "null"` flipped to `=` 2 failed.

### A reviewer caught what the tests could not see

The Cursor agent found the completeness read wrong within minutes of the push,
and the interesting part is why no assertion did.

The read said `.fetched_pages_complete // "unknown"`. jq's alternative operator
fires on `false` as well as `null`, so a producer that measured the fetch and
reported it truncated came out as `unknown`, telling the operator the field
could not be read when it had been read fine. Verified rather than assumed:

| Producer payload | `// "unknown"` | explicit null test |
|---|---|---|
| `{"fetched_pages_complete":true}` | `true` | `true` |
| `{"fetched_pages_complete":false}` | `unknown` | `false` |
| `{}` | `unknown` | `unknown` |

Both wrong and right values deny the T1 exemption, so every assertion in the
suite held either way. The case parameterized on `false` was passing while
running the `unknown` path, which makes it a test whose two inputs cannot
produce different results. That is the same defect shape as the rest of this
PR, one level up: the unit the assertion could see was narrower than the
behavior the case was named for.

Closed by asserting on the operator message, which is where the states differ,
with the fix taken from the reviewer rather than reimplemented. Control:
restoring `//` fails `test_an_incomplete_fetch_is_reported_as_false_not_unknown`
on both docs and nothing else (2 failed, 52 passed), restore byte-identical,
54 passed either side.

### The repair opened the worse direction of the same bug

Copilot read the fix from the pass above and found it had traded one defect for
a more dangerous one. `tostring` converts without checking the JSON type, so the
*string* `"true"` came out as the boolean `true`. Measured across the shipped
read and its replacement:

| Producer payload | `// "unknown"` | bare `tostring` | JSON-boolean check |
|---|---|---|---|
| `{"fetched_pages_complete":true}` | `true` | `true` | `true` |
| `{"fetched_pages_complete":"true"}` | `unknown` | **`true`** | `unknown` |
| `{"fetched_pages_complete":false}` | `unknown` | `false` | `false` |
| `{"fetched_pages_complete":1}` | `unknown` | `1` | `unknown` |
| `{}` | `unknown` | `unknown` | `unknown` |

The middle row is the whole finding. The first bug mislabelled a denial, which
costs an operator a confusing message. This one granted a merge on evidence the
command could not read, which is the exact thing the guard exists to refuse.
Three reads, three behaviors, and only the third is right.

Control: restoring the bare `tostring` fails the new wrong-type case on all five
values across both docs, 10 in total, and nothing else. Restore byte-identical.

Two more from the same review, both real:

- **The verification checklist still said the disarm runs on non-T1 PRs only.**
  Agents report completion against that checklist, so it is the one piece of
  prose in the command that functions as evidence, and it had drifted from the
  gate. Updated, plus a guard that fails when the block gates on a completeness
  field the checklist does not name.
- **The inverted control's discrimination was prose.** `Validate Spec Coverage`
  independently marked the same criterion PARTIAL and named the same reason:
  the control asserts two runs agree, and the claim that a non-inert edit makes
  them differ lived only in a docstring and this report.
  `test_the_inverted_control_can_fail` asserts it, so a harness that stops
  observing behavior fails instead of passing quietly.

And a fourth, on the checker rather than the command: `_JQ_PATH` reads dotted
identifiers only, so `.Tier // .["tier"]` yields one path, passes both coverage
guards, and leaves the bracket half unchecked. Verified against the parser
before fixing (one read, zero violations, zero unparsed). Reported rather than
parsed, since nothing uses bracket notation today and the first read that does
should fail loudly rather than pass unseen.

### The escalation path handed PRs to humans still able to merge themselves

Copilot filed this as CWE-284. The round-cap breaker's ESCALATE path terminates
the PR, and while the breaker ran first that exit came before the disarm gate,
so a T3 or T4 PR that burned its rounds was handed to a human with native
auto-merge still armed. GitHub does not wait for this loop's completion gate, so
the PR could land on its own with readiness never proven, arriving on exactly
the PRs most in need of a human.

Third case now where this PR's own fix opened the hole rather than passing it
by, and for the same mechanism each time: a pinned UNKNOWN never matched T3 or
T4, so the breaker never fired and the disarm gate reached every armed PR
anyway. Correcting the tier read makes the escalation path reachable for the
first time.

**The test asserted the defect was correct.** It read:

    assert not run.disarmed, "the loop kept acting after the round cap escalated"

That conflates disarming with acting. Disarming is not acting on a PR, it is
taking a capability away from one, so it was never the thing the escalation
needed to stop. A test that encodes the wrong contract is worse than an absent
one, because it also blocks the fix and reads as deliberate. Flipped rather than
deleted, with the old assertion quoted in its docstring.

Fixed by reordering the two gates rather than duplicating the disarm into the
escalation branch: one gate in one place cannot drift from a copy, and there is
no tier it is unsafe to run first. Control: swapping the blocks back fails the
flipped test on both docs and nothing else, restore byte-identical.

### The last red check was the body, not the code

`Validate PR` sat red while every other check was green. The job reports two
things at once and it is worth separating them, because only one was real:

    DESCRIPTION_RESULT: FAIL
    COMMIT_STATUS: BLOCKED
    COMMIT_COUNT: 79   COMMIT_LIMIT: 40
    BYPASS_USED:  (empty)

The empty `BYPASS_USED` looked like the `commit-limit-bypass` label failing to
register, which would have been a real blocker needing a maintainer. Reading
`scripts/ci/enforce_pr_validation.py` shows otherwise: it returns at

    if overall_status in {"FAIL", "ERROR"}:

before it ever reaches the commit-status branch that fetches labels. So the
commit ceiling was never evaluated, and the description failure was the whole
blocker. Those three `BYPASS_*` variables come from the *description* step and
refer to a different label, `description-validation-bypass`, which this PR does
not carry and must not, since CONTRIBUTING.md makes it human-only.

The description failure was mine, and it is the third instance of one mistake.
`pr_description.py` treats a path under `## Changes` as a claim about the diff.
Reproduced locally by calling `validate_pr_description` against the fetched body
and `git diff --name-only origin/main...HEAD`:

| Body text | Result |
|---|---|
| `.agents/sessions/...json` (abbreviated) | CRITICAL, file not in diff |
| `.agents/memory/episodes/...json` (abbreviated) | CRITICAL, file not in diff |
| `` `test_*.py` `` (a glob, introduced while fixing the above) | CRITICAL, file not in diff |
| all three written out in full | 0 CRITICAL, 0 WARNING |

The first two had already happened once and were already written into the PR
body as a note warning about exactly this. Writing the warning did not stop the
repeat, because the rewrite reintroduced it in the same two lines. What finally
worked was not a note but a check: running the validator locally against the
body before publishing it, which is now how the body gets edited.

Verified after the fix: all 15 paths the extractor pulls from the body match the
15 in the diff, and `Validate PR` went green on the next run.

Two of those controls assert behavior the static gate cannot see at all. The
round-cap breaker firing on T3 and T4, and the T1 PR keeping the auto-merge it
earned, are properties of the shell conditions, not of the `jq` path.
