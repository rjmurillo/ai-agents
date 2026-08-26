---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-5189-54e494d-adr-corpus-evaluation-and-tooling.json
qaCommit: aac1400909c75935841732f7aea597ff557ee693
---
<!-- # taste-lint: ignore file-size, this is an append-only QA audit trail; addenda are numbered sequentially and splitting the file would break that numbering and scatter one campaign's evidence across files (issue #3779). -->

# QA: ADR Corpus Evaluation and Repair Campaign (issues #5189 to #5201, #5205)

**Branch**: `claude/adr-evaluation-tooling-6od8rd`
**Validated at commit**: `aac1400909c75935841732f7aea597ff557ee693` (see Addendum 60)
**Session log**: `.agents/sessions/2026-08-21-session-5189-54e494d-adr-corpus-evaluation-and-tooling.json`

## Verdict

PASS. 388 tests green, every gate at or below its baseline, `pre_pr.py` clean
apart from the session-end check this report exists to satisfy.

**This verdict and the test evidence immediately below are historical: the
campaign's own opening state on 2026-08-21, not current counts.** The
`qaCommit` frontmatter and the `Validated at commit` header above track the
latest commit this file has been checked against, per this report's own
rebind discipline; they do not mean the 388/85/63/57 figures below still
hold. Later rounds grew every one of these suites substantially: Addendum 52
records both `test_check_adr_lifecycle.py` at 130 tests (not 85) and
`test_check_adr_links.py` at 148 tests (not 63), and both counts still match
a direct re-run today (`uv run pytest tests/validation/test_check_adr_lifecycle.py -q`
and the `test_check_adr_links.py` equivalent). Addendum 58 separately records
a 554-test targeted run covering the retarget merge. Copilot flagged this
top-of-file drift on PR #5230 round 14. Re-measure with the commands below
rather than trusting either the historical numbers or this note's own
summary of them.

## Test evidence

```
uv run pytest tests/validation/test_check_adr_lifecycle.py \
              tests/validation/test_check_adr_links.py \
              tests/build_scripts/test_generate_adr_index.py \
              tests/skills/adr-review/ \
              tests/skills/test_misc_skill_scripts.py \
              tests/validation/test_pre_pr_sequence_registry.py \
              .claude/skills/adr-review/tests/ -q

============================= 388 passed in 6.98s ==============================
```

Breakdown of new coverage:

| Suite | Tests | Subject |
|---|---|---|
| `test_check_adr_lifecycle.py` | 85 | The nine lifecycle checks, containment, cycle termination, never-mutates |
| `test_check_adr_links.py` | 63 | Four link violation classes, historical-root exemption, fenced-block edges |
| `test_generate_adr_index.py` | 57 | Section routing, failure policy, determinism, no-banner, chain walk, review-by rendering |
| `test_detect_adr_changes.py` (x3 trees) | 93 | Frontmatter-only parsing, `unknown` sentinel, fenced-yaml regression guard |

Coverage measured on the new gates: `check_adr_links.py` 99% (single miss is the
`__main__` guard), `check_adr_lifecycle.py` 96% (misses are the `__main__` guard,
a `sys.path` insert, and two defensive I/O legs).

## Gate evidence

```
check_adr_lifecycle.py   [PASS] 78 violation(s), no check above its baseline.
check_adr_links.py       check_adr_links: 0 violation(s)
check_adr_uniqueness.py  [PASS] All ADR numbers unique (next free: 099)
taste count ratchet      OK. 573 violations <= baseline 576 (-3 slack).
ruff count ratchet       OK (count == baseline 27).
pre_pr.py                all gates PASS except Session End Validation
```

`pre_pr.py`'s single failure was `Session End Validation`, whose QA-evidence
check requires a path to a report under `.agents/qa/`. This file is that report.

## Corpus movement, measured

Run against a `git archive HEAD` extraction of the pre-campaign corpus versus the
working tree:

| Check | Before | After |
|---|---|---|
| `frontmatter-parses` (records with no parseable frontmatter) | 59 | 54 |
| `supersession-reciprocal` | 1 | 0 |
| ADR link violations | 26 | 0 against baseline, 21 pre-existing elsewhere |

The "After" column is this campaign's own measurement, taken at the time of the
run, and is left as measured. Both figures moved again afterwards for reasons
outside this campaign; the current numbers and what moved them are in "Known
gaps carried forward" below. Read that section, not this table, for the live
state.

`_get_adr_status` before and after, on real corpus files:

```
BEFORE  ADR-042 -> proposed    ADR-005 -> proposed
AFTER   ADR-042 -> accepted    ADR-005 -> superseded
```

ADR-073 regression guard held at `accepted` on both sides: its real frontmatter
says `accepted` and its Decision section contains a fenced YAML block whose
`status:` line the old whole-file regex could have read instead.

## Governance evidence

Ten ADR records were modified. Every substantive edit routed through the
mandatory six-role `adr-review` debate, which the pre-commit gate
`check_adr_review_policy` enforces. No surviving commit skipped a hook: one
`git commit --no-verify` invocation was recorded on the stacked branch, on a
scratch commit a `git reset --soft` discarded in the same command, reaching
no ref (see the correction below and Addendum 7 of
`session-5209-adr-review-fixes-stacked.md`). `LEFTHOOK=0` and
`LEFTHOOK_EXCLUDE` were not used at any point.

Consensus: 2 Accept (architect, high-level-advisor), 3 Disagree-and-Commit
(independent-thinker, security, analyst), 1 Block (critic) whose blocking
findings were all resolved before merge.

Debate logs, one per change-set rather than one for the batch:

- `.agents/critique/ADR-corpus-repair-5189-5201-debate-log.md`
- `.agents/critique/ADR-079-091-092-chain-debate-log.md`
- `.agents/critique/ADR-005-042-scripting-language-debate-log.md`
- `.agents/critique/ADR-023-032-033-link-repair-debate-log.md`

The per-change-set split was deliberate. The security reviewer proved that the
gate accepts one log as authorization for every ADR staged in the same commit
(issue #5205), so a single batch log would have exploited a defect the same
review had just found.

## Reviewer P0s found and fixed

| Finding | Resolution |
|---|---|
| ADR-055 claimed live accepted ADR-014 was retired. ADR-014 is Distributed Handoff Architecture, bound by `universal.md` MUST-3. | Rewritten to say where the marker actually points. |
| ADR-055 cited two ADR-007 survivals while the same diff removed one. | Claim deleted; it was also unverifiable. |
| `implemented: true` on ADR-055 while 21 of 132 `runs-on` declarations are non-ARM and none carries an exception marker. | Set to `false`; the residual gap is stated in the Metrics table with the 2026-08-21 measurement. |
| ADR-055's provenance prose was fabricated (claimed PR #476, 2025-12-29). | Refuted against `mcp__github__list_commits`: single commit `3e24d2c0`, PR #1604, 2026-04-10. This record **was ADR-032**. Corrected. |
| ADR-042 carried the corpus's most load-bearing enum without citing its evidence. | `## Status` now names `.agents/critique/ADR-042-debate-log.md` and four supporting artifacts. |
| ADR-025 quoted "111 of 127" with no matcher; measured total is 132. | Corrected with the command and the matrix-expression caveat. |

## Author errors found by reviewers and corrected on the issues

Two findings in the originally-filed issues were the author's and were wrong.
Both are corrected on the issues so an implementer does not chase them.

1. **#5197**: the reported malformed nested-bracket ADR-080 links do not exist.
   All eleven are well-formed. The audit regex began matching at the opening
   paren of a surrounding prose parenthetical and ran through the `](`.
2. **#5200**: five of the six `proposed` plus `implemented` records are
   deliberate, documented refusals to self-ratify, not drift. Zero flips made,
   which is the correct outcome.

## Known gaps carried forward

- Closed. This gap read 54 when the campaign filed it, was corrected to 53 as a
  stale carried-forward count, and is now 0: `1d15e0d06` (PR #5291, "ADR-073
  lifecycle frontmatter across 67 ADRs") merged into this branch and backfilled
  the remainder for issue #5190. Re-measured at this commit:
  `check_adr_lifecycle.py` reports `frontmatter-parses 0 / 0`, and the index's
  "Needs backfill" section, which this bullet named as the live meter, reads
  "None." No follow-up work remains behind this line.
- 19 pre-existing ADR link violations in files outside this change, each
  baselined with a written diagnosis. (Corrected from 21; `check_adr_links_baseline.txt`
  currently holds 19 non-comment entries.)
- 21 non-ARM `runs-on` declarations carry no exception marker (issue #5199).
- The debate-log gate is forgeable (issue #5205), filed with a proven exploit.
- Six governance forks deferred to the owner, four of which the tie-breaker
  judged decidable by evidence rather than taste.


## Addendum: review-by renderer (commit 46ba46368)

CI's spec-validation completeness reviewer returned PARTIAL naming a real gap:
this campaign added `review-by` to `ADR-TEMPLATE.md` and shipped an index that
never read it, while issue #5198 specifies the Proposed table carries "the
condition or review date blocking acceptance".

Fixed. The index now reads `review-by` from frontmatter and renders it in the
Proposed blocking column, alone or alongside the prose blocker.

Re-verified at this commit:

```
388 passed in 6.98s
check_adr_lifecycle    [PASS] 78 violation(s), no check above its baseline.
check_adr_links        0 violation(s)
generate_adr_index     --check OK (README byte-identical)
```

Four added tests: the date renders; date and prose render together; absence
leaves prior output unchanged (negative control); and a determinism guard that
renders a long-past and a far-future date and asserts the output differs only in
the date itself. That last one pins a deliberate limitation: the renderer does
not compare against today, because it must be byte-identical for identical input.
Past-due detection belongs in the lifecycle gate, where a test can freeze the
clock. Tracked on #5193.

The generated README is byte-identical because no record sets `review-by` yet,
so this adds the reader ahead of the first writer rather than leaving the field
inert.


## Addendum 2: owner-directed removal of prose status duplication (commit 4faed5931)

The repository owner reviewed the PR and flagged ADR-005's prose status line as
duplicating its frontmatter. He was right, and this campaign introduced the
duplication: the record previously stated status, date and deciders once as inline
labels, and this campaign added frontmatter restating all three.

Honouring the edit tripped this campaign's own `status-section-present` check
(7 to 8, ratchet fail). The check was removed rather than the edit reverted,
because it overreached ADR-073 line 57 ("the prose section remains for humans and
**may** carry the nuance the enum cannot", permissive) by turning a MAY into a
MUST, and what it mandated was duplication on records with nothing to add.

Lifecycle baseline falls 78 to 71. Seven violations were deleted with the rule
that manufactured them, not hidden behind a raised ceiling. The full reasoning,
including why four other records keep their prose sections, is at
`.agents/critique/ADR-005-status-duplication-debate-log.md`.

Re-verified at this commit:

```
388 passed in 7.40s
check_adr_lifecycle    [PASS] 71 violation(s), no check above its baseline.
check_adr_links        0 violation(s)
generate_adr_index     --check OK (README byte-identical)
```

`prose-frontmatter-agree` is unchanged and still enforces what ADR-073 does state:
when prose and frontmatter both speak and disagree, frontmatter wins.


## Addendum 3: status prose stops restating frontmatter (commits 1615ffa40 and the gate fix in this same push)

A second owner review comment, on ADR-024 line 16 ("Redundant"), established the
principle: prose says what frontmatter cannot and never restates what it carries.
Every status section this campaign wrote opened by restating the enum and then
narrating the frontmatter. Those openings are removed; the content frontmatter
cannot hold moved under `## Provenance` (ADR-024, ADR-025, ADR-055) and
`## Acceptance Evidence` (ADR-042).

**A gate bug this surfaced.** With the redundant sections gone, the lifecycle
checker began reading ADR-042's `### Status` at line 171 (a migration-phase
subsection) and ADR-055's `**Status**: COMPLETE` at line 119 and
`**Status**: APPROVED` at line 168 (a phase result and an exception ruling) as
those records' lifecycle status. It had been searching the whole document and
taking the first hit anywhere. The bug shipped green because a redundant Status
section higher in each file masked it.

That is the same defect this campaign filed as #5189 against `_get_adr_status`,
reproduced inside the checker written to police it. Fixed by bounding the search
to the record header, with two negative controls built from the records that
broke.

Re-verified at this commit:

```
392 passed
check_adr_lifecycle    [PASS] 71 violation(s), no check above its baseline
                       prose-frontmatter-agree 1/1 (ADR-068, pre-existing)
check_adr_links        0 violation(s)
generate_adr_index     --check OK
```

**One process note worth recording.** The first attempt to append this addendum
used an unquoted heredoc, so the shell executed every backtick span and wrote a
version with the heading names and file paths silently deleted. It read "moved
under  (ADR-024...)". That is the defect class this PR exists to close, produced
while documenting it, and caught only because the output was re-read rather than
assumed. The fix was a quoted delimiter.

## Addendum 4: merge of origin/main, and a base-branch failure fixed on the way through

The branch merged `origin/main` (8 commits behind). Two things came with it that
this report has to account for, because neither is about ADRs.

**A red test inherited from main.** `caae865fb` (Renovate PR #5215) bumped
`astral-sh/setup-uv` in `.github/workflows/vendor-provenance.yml` from
`ae62891f` to `20cfd1bf`, and left the same SHA restated as a literal in
`tests/ci/test_validate_vendor_provenance.py`. The test asserts only that the
workflow installs uv; nothing it checks depends on which build of the action
runs. So the bump broke it, it was already red on main before this branch
touched anything, and every future bump would break it identically.

Fixed at the duplication rather than by retyping the new SHA: the assertion now
requires an `astral-sh/setup-uv` reference pinned to a full 40-character commit
SHA, read from the workflow, which is the one place that owns it. That still
enforces the property the repo actually cares about (universal.md MUST-8, no
floating tags) and survives every bump.

The control was proven falsifiable rather than observed passing
(`.claude/rules/testing.md` SHOULD 17). With the workflow rewritten to
`astral-sh/setup-uv@v10` the assertion goes DEAD; restored, it passes. A
companion probe runs the shared pattern against six regression shapes (major
tag, semver tag, branch ref, abbreviated SHA, wrong action, absent step) and
requires no match on each.

One SHA duplication was deliberately left alone. `PATHS_FILTER_PIN` in
`tests/ci/test_pytest_paths_filter_covers_episodes.py` restates a
`dorny/paths-filter` SHA, but that one is load-bearing: the test models the
action's internal `MatchOptions`, so a version bump really does invalidate the
model and has to fail loudly. Restating a SHA is correct exactly when the
assertion depends on that specific build. Sweeping it would have removed a real
control.

**A gate that blocks every commit after a merge when `origin/HEAD` is unset.**
The merge imported another branch's session log, and `check_branch_context`
then blocked every commit with `branch context mismatch: current=...,
session=...pr-automerge-goal.json`. The exemption written for exactly this case
(issue #3343) requires `_is_merged_history`, which resolves the upstream default
branch with `git rev-parse --abbrev-ref origin/HEAD`. This clone had no
`origin/HEAD` set, so `upstream` was empty, the function failed closed as
documented, and the exemption could not fire.

Fixing the clone (`git remote set-head origin --auto`) cleared it, and the
exemption then evaluated correctly (branch owns a log: yes; winner is merged
history: True). No surviving commit skipped a hook at any point in this
campaign (see the correction above on the one non-surviving invocation). The
fragility is worth recording anyway: on a clone without `origin/HEAD`, a routine
`git merge main` hard-blocks all further commits, and the error message names
none of the three real causes. Filed as #5220 with the reproduction and a
two-part fix, rather than patched here, since it is outside this PR's subject.

Re-verified at this commit:

```
414 passed   ADR lifecycle, links, index, detect_adr_changes (+2 mirrors),
             misc skill scripts, pre_pr sequence registry
 51 passed   tests/ci/test_validate_vendor_provenance.py
check_adr_lifecycle    [PASS] 71 violation(s), no check above its baseline
check_adr_links        0 violation(s)
generate_adr_index     --check OK, exit 0
taste_count_ratchet    OK, 574 <= baseline 576
pre_pr.py              all gates PASS
```

## Addendum 5: UnicodeDecodeError is not an OSError (Cursor Bugbot, PR #5209)

A review bot reported that `Path.read_text(encoding="utf-8")` wrapped in
`except OSError` never catches `UnicodeDecodeError`, because that subclasses
`ValueError`. It named three locations. The finding is correct and was
reproduced before any fix:

```
_read_record   ESCAPED: UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff
read_baseline  ESCAPED: UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff
```

The consequence is worse than a crash. One ADR with a stray byte aborted the
whole lifecycle gate with a traceback, so the other 97 records went unreported
and the run read as tooling breakage rather than as a finding about the corpus.
That is this PR's own subject matter reproduced in the gate written to police
it, which now makes three times in this campaign.

**The sweep found more than the report.** Every `read_text` site in this PR's
files was checked rather than only the three named:

| Site | State | Action |
|---|---|---|
| `check_adr_lifecycle._read_record` | `except OSError` | fixed (reported) |
| `check_adr_lifecycle.read_baseline` | `except OSError` | fixed (reported) |
| `detect_adr_changes:234` | `except OSError` | fixed (reported) |
| `detect_adr_changes:60` | `except OSError` | **fixed (not reported)** |
| `detect_adr_changes:274` | already catches `ValueError` | unchanged |
| `generate_adr_index.main` | already catches `UnicodeDecodeError`, exit 3 | unchanged |
| `check_adr_links:222` | reads `errors="replace"`, cannot raise | unchanged |

`_get_dependent_adrs` at line 60 is the one the report missed. Fixing only the
named handlers would have left the dependent scan crashing on the same input,
which is the partial-guard failure the mirror obligation exists to prevent.

Two sites were verified correct and deliberately left alone rather than
"fixed". `generate_adr_index` already handles it at the top level with an
ADR-035 exit 3, and `check_adr_links` reads with `errors="replace"` so it cannot
raise at all. Those two contracts differ on purpose: a validator that must
report corruption should surface it, not silently substitute characters, which
is why the gates report and the link reader replaces.

**Messages distinguish the two failures.** "is not valid UTF-8" and "could not
be read" send a reader to different fixes, so they do not share wording.

**Every guard proven falsifiable, not observed passing** (`testing.md`
SHOULD 17). Reverting each arm and re-running:

```
check_adr_lifecycle   4 failed, 1 passed   (restored: 5 passed)
detect_adr_changes    3 failed, 1 passed   (restored: 4 passed)
```

The one test passing either way in each pair is the negative control. It
catches a handler that returns the violation or the `unknown` sentinel
unconditionally, which would satisfy every positive test and be
indistinguishable from a correct fix.

**A violation I introduced and then removed.** The new cases took
`test_detect_adr_changes.py` from 490 to 562 lines, past the 500-line ceiling,
and the taste ratchet from 574 to 575. The baseline had two slots of slack, so
it would have passed. Extracted to `test_detect_adr_changes_encoding.py`
instead; the ratchet is back to 574, its pre-change value. A scoped suppression
was available and is what the repo does for a few tightly-paired harnesses, but
`code-quality.md` ranks the idiomatic fix above it and these cases are cohesive
enough to stand alone.

Re-verified at this commit:

```
429 passed   ADR gates, index, detect_adr_changes across all four trees,
             misc skill scripts, pre_pr sequence registry
check_adr_lifecycle    [PASS] 71 violation(s), no check above its baseline
check_adr_links        0 violation(s)
generate_adr_index     --check OK
taste_count_ratchet    OK, 574 <= baseline 576, unchanged from pre-review
```

### Concurrent fix by the Bugbot autofix agent, and what the merge broke

The autofix agent fixed the same family on this branch while I was fixing it.
Both fixes are real and both cover the same four sites, including
`_get_dependent_adrs`, which the bug report did not name. Resolved toward this
branch's version because it is a superset: distinct messages, comments stating
why each arm exists, and nine falsifiable tests where theirs has none.

**Git's automatic merge of `check_adr_lifecycle.py` was itself a defect.** It
kept their broadened `except (OSError, UnicodeDecodeError) as exc` AND my narrow
`except UnicodeDecodeError`, leaving the second arm unreachable and silently
reverting the message to "could not be read". Nothing about that is visible in
the merged text; both arms read as intentional.

Three tests went red on it:

```
FAILED test_the_undecodable_message_names_utf8_not_unreadable
FAILED test_a_baseline_that_is_not_valid_utf8_is_a_config_error
FAILED test_a_corrupt_baseline_exits_config_rather_than_traceback
```

That is precisely why those tests assert the message text rather than only the
absence of a traceback. A test that checked "does not crash" would have passed
the broken merge, and the distinct diagnostic would have been lost with a green
suite. Worth carrying forward: when two fixes for one defect meet in a merge,
the risk is not a conflict git reports, it is the one it resolves.

Re-verified at the merge commit:

```
300 passed   lifecycle, detect_adr_changes across all four trees, misc skills
check_adr_lifecycle    [PASS] 71 violation(s), no check above its baseline
taste_count_ratchet    OK, count == baseline 576
```

### A defect `pre_pr.py` cannot see

The colocated test added above spelled `.agents/architecture` literally. Those
tests ship inside the plugin, so on a consumer using any other entry in
`ADR_DIRECTORIES` it asserts a path their repository does not have. The
vendor-portability ratchet (issue #2050) blocked the push for it.

`pre_pr.py` reported all 133 gates PASS with that defect present. The ratchet
lives in the pre-push pytest sweep rather than the pre-PR sequence, so a green
`pre_pr` run is not the same claim as "ready to push", and this report should
not be read as making that claim anywhere it says `pre_pr.py` passed.

Fixed by reading `ADR_DIRECTORIES[0]` from the module, which is also the more
honest test: the behaviour under test is the scan over whatever directories the
module declares.

### Two fixes to one test, combined rather than chosen between

PR #5219 landed a fix to `test_workflow_sets_up_uv` on main while this branch
carried its own. Both are real and they close different holes:

| Property | Source | What it catches |
|---|---|---|
| Parse the job's steps, require exactly one `Setup uv` | #5219 | The step deleted while its `uses:` line survives in a comment or on another step (testing.md MUST 9) |
| Assert the pin *shape*, never the SHA | this branch | The next Renovate bump, which breaks any restated literal |

Each version had the other's hole. #5219 asserts equality against `20cfd1bf`,
so the next bump breaks it exactly as #5215 broke the literal before it. This
branch searched the file as text, so a stray `uses:` line in a comment would
have satisfied it. The resolution keeps both.

Proven falsifiable on both axes rather than observed passing:

```
workflow pinned to @v10        -> FAILED   (pin-shape axis)
step renamed to "Install uv"   -> FAILED   (structural axis)
restored                       -> passed
```

Recorded because the tempting resolutions were both wrong. Taking main's
version wholesale would have re-introduced the drift this PR fixed; taking mine
wholesale would have discarded a genuine improvement from another author.

## Addendum 6: Copilot review, and the record this PR silently broke

### The duplicate-key forgery vector

`yaml.safe_load` resolves duplicate mapping keys last-wins and reports nothing:

```
yaml.safe_load("id: A\nstatus: proposed\nstatus: accepted")
-> {'id': 'A', 'status': 'accepted'}
```

So a record could declare `status: proposed` near the top and `status: accepted`
lower in the same block, and every reader in this PR would enforce accepted
while a human scanning the first lines sees proposed. In a PR whose subject is
making ADR lifecycle trustworthy, that is a forgery vector rather than a
formatting nit.

The repo already knew. `detect_adr_changes` carries
`_has_duplicate_top_level_keys`, documented as catching "a second `status:` line
masking the first", and fails its frontmatter-only exemption closed on it. It
guarded the exemption path and nothing else, so the status path and the
exemption path disagreed about whether such a record is readable at all.

Fixed in all three readers, with the mechanism chosen per site rather than
copied: `detect_adr_changes` defers to the existing tested helper;
`check_adr_lifecycle` scans top-level lines and returns the offending key so the
violation can name it, deliberately not touching the shared `yaml_utils` helper
whose other consumers this change has no mandate to alter; `generate_adr_index`
subclasses `SafeLoader` so duplicates nested inside a mapping value are caught
too, which a line scan cannot do.

### The record this PR broke, and why nothing caught it

ADR-063 carried no frontmatter. Its machine-readable status was a bare
`status: accepted` line inside the body of its `## Status` prose, at line 12,
which resolved only because the parser searched the whole document. That is
exactly the defect #5189 closed here, so fixing the parser silently changed
ADR-063 from `accepted` to `unknown`.

Three tests covered ADR-063's status and none noticed, because each
reimplemented the old regex instead of calling the parser. Measured from one
file before the repair:

```
docstring claims          "proposed"
test assertion requires   "accepted"
canonical parser returns  "unknown"
```

The docstring and the assertion contradicted each other in the same file, and
both contradicted the parser they claimed to mirror. This is the
canonical-source-mirror rule earning its place: a test that copies a contract
instead of calling it will pass through the contract changing underneath it.

ADR-063 now carries frontmatter transcribing the acceptance its prose has
recorded since 2026-06-17, the orphan body line is gone, and the tests call
`_get_adr_status`. Debate log:
`.agents/critique/ADR-063-frontmatter-transcription-debate-log.md`.

### A template overreach, corrected

The template comment told authors to name lifecycle sections anything but
`## Status`. ADR-073 says the opposite verbatim: it retains that section as "the
human-readable secondary rendering", says it "may carry the nuance the enum
cannot", and lists under Neutral that it "is retained, so human reading habits
do not change".

Removing the pre-filled duplication was right and is what the owner asked for.
Telling authors not to use the section was an overreach past both the review
comments and the ADR. **This is the second time in this campaign the same
mistake was made**: the `status-section-present` check turned the same MAY into
a MUST in the opposite direction. Recording the repeat, because one instance is
an error and two is a pattern worth naming.

Re-verified at this commit:

```
check_adr_lifecycle    99 passed
generate_adr_index     60 passed
detect_adr_changes     56 passed across four trees
ADR-063 structural     26 passed
mypy ratchet           clean after annotating the loader
taste ratchet          within baseline
```

### A UTF-8 site my own sweep missed

The autofix agent found one I did not: `check_adr_links.py:291`, a handler whose
`except (OSError, subprocess.CalledProcessError)` guarded a read several lines
above it. My sweep grepped for `read_text` calls and inspected the four lines
after each, so a handler sitting further from its read fell outside the window.
Merged from `ade5308fc`.

Recording the method failure, not just the miss. A proximity heuristic finds
handlers that hug their read and silently reports clean on the ones that do not,
which is the same shape as the whole-document scan this campaign has now hit
three times: a search whose scope is not the scope of the question. The reliable
sweep is over exception handlers, asking which reads each one guards, rather
than over reads, guessing which handler catches them.

### Both of this PR's inherited reds are now fixed on main

`#5225` bumped the audited pip to 26.2 (issue #5222) and `#5219` fixed
`test_workflow_sets_up_uv`. Both are merged, so `PR #5223` (this session's
unblock-main PR) is fully redundant: main's pip block updated every comment that
named the old version and kept all three CVE ignores, which is what that PR
existed to do.



## Addendum 7: rebound to the stacked branch's head

**Rebound from** `b7b87c395677b7a1611e29390262af906324e466` **to** `b38d43b0fa5f293d0f68f07bab5183039dda68a6`.

`scripts/validation/check_adr_lifecycle.py` and its test module changed again
after the previous binding, so Session End Validation reported this report stale
against them. That is the check working: a QA verdict that predates the code it
attests to is not evidence.

The two commits are `df9c75495` (close the `_status_prose` prose-drift bypass
Copilot found, replacing a header bound applied to every status form with a
three-way rule scoped by form) and `b38d43b0f` (bring both files under
`ruff format`). The findings, the corpus measurements, the mutation proof, a
figure I re-measured and corrected before pushing, and a `--no-verify`
invocation I recorded rather than let an absolute claim paper over, all live in
addendum 7 of `.agents/qa/session-5209-adr-review-fixes-stacked.md`. Not
duplicated here: that report owns the stacked branch's evidence, and copying it
would create two copies to keep in sync.

Re-verified at this commit: `check_adr_lifecycle` 102 passed, the corpus gate
`[PASS] 70 violation(s), no check above its baseline`, `ruff check` clean,
`mypy` clean over all 19 changed Python files.


## Addendum 8: rebound again for the two diagnostic fixes

**Rebound to** `66bd167c35df9d7ca76b336ac5382c582e9dd5c6`.

`build/scripts/generate_adr_index.py` and `scripts/validation/check_adr_lifecycle.py`
changed again, so the previous binding went stale. Evidence lives in addendum 8
of `.agents/qa/session-5209-adr-review-fixes-stacked.md`: a query recipe that
disagreed with all four real status readers, a frontmatter diagnostic that named
the wrong defect, a mutation probe that turned out not to discriminate, and the
corpus measurements showing both fixes latent. `.agents/architecture/README.md`
is regenerated because the recipe ships inside it.


## Addendum 9: rebound after the Bugbot and Copilot review round

**Rebound to** `5ec9be82445ceaddfde320df60dcfd6473047d4f`.

Nine findings across both reviewers, plus an unprompted autofix commit on the
branch. Evidence lives in addenda 9 and 10 of
`.agents/qa/session-5209-adr-review-fixes-stacked.md`. The headline: the
duplicate-key guards this campaign added did not close the forgery vector they
were built for, because a line scan compares raw prefixes and YAML compares
constructed keys. All three readers now detect at the parser.


## Addendum 10: rebound past the Gate 3 fix

**Rebound to** `ce176cb339ac7f9d862afb74b7a0729df7d595b0`.

`scripts/invoke_session_start_gate.py` and its test changed again (Gate 3's
false `[WARN]` on the now-expected absence of a session log). Evidence lives
in Addendum 11 of `.agents/qa/session-5209-adr-review-fixes-stacked.md`:
mutation-proven by reverting to the old wording, which fails exactly the two
new tests and nothing else in the file.


## Addendum 11: rebound past the `origin/main` merge (ADR-099, ADR-102 land)

**Rebound to** `9f5df8d092baf5b2a977dfd06ca3b8c9dc2c98bb`.

Merge conflict resolution and full re-verification recorded in Addendum 12 of
`.agents/qa/session-5209-adr-review-fixes-stacked.md`. Summary: the only real
conflict was in `tests/ci/test_validate_vendor_provenance.py`, resolved by
keeping this branch's fuller fix; ADR-102's change to
`.claude/lib/qa_report.py` only loosens the `session_qa_binding()` contract
and invalidates none of this campaign's prior verification.


## Addendum 12: rebound past the post-merge index regeneration

**Rebound to** `9baa0a9fad1131b14ad203c016d5483025c30d61`.

`.agents/architecture/README.md` needed regenerating after the Addendum 11
merge; see Addendum 13 of `.agents/qa/session-5209-adr-review-fixes-stacked.md`.


## Addendum 13: workspace-budget fix, discovered mid-push

**Rebound to** `2cc0faa83d63586f0a380fcfa26f2a72d09be5ed`.

`AGENTS.md` breached its 3000-byte budget as a side effect of the Addendum
11 merge (two independently-compliant sides combined past the ceiling by
git's line-based merge). Full detail in Addendum 14 of
`.agents/qa/session-5209-adr-review-fixes-stacked.md`.


## Addendum 14: PR #5209's own branch independently merged `origin/main`, and one more fix landed

**Rebound to** `986ab2641b1b68cd326b68c5a06f314eccbeb79a`.

The frontmatter `qaCommit` had drifted from this file's own last `Rebound
to` value (`5ec9be82445...` in Addendum 9); noted here rather than silently
carried forward, since reconciling it was out of scope for that rebind.

Full detail lives in Addendum 15 of
`.agents/qa/session-5209-adr-review-fixes-stacked.md`: committed the
already-drafted `build_all.py` ADR-index fix, merged `origin/main` to clear
this branch's `mergeable_state: "dirty"` (one conflict, the same
`tests/ci/test_validate_vendor_provenance.py` Renovate-drift collision
already resolved independently on the stacked branch, addenda 10-13 above),
and regenerated the ADR index for the resulting drift. 279 tests passed.


## Addendum 15: PR #5209's own workspace-budget fix and a real taste-lint ratchet regression

**Rebound to** `92304f8231a2de5977820f73d63452999b21b60f`.

Full detail in Addendum 16 of
`.agents/qa/session-5209-adr-review-fixes-stacked.md`. Summary: `AGENTS.md`
breached its 3000-byte budget as a merge side effect (fixed, 2984 bytes),
and this file (the one carrying this addendum) crossed 500 lines, a real
taste-count ratchet regression against `origin/main`'s baseline (this file
does not exist there). Suppressed with the documented per-repo escape
rather than splitting; verified the whole-tree ratchet returns to baseline.


## Addendum 16: the two stacked branches merged back together

Merge commit `9f0e7d552d6a683c816f959fd894d3a009171905` on
`claude/adr-5209-review-fixes`. Full detail in Addendum 17 of
`.agents/qa/session-5209-adr-review-fixes-stacked.md`: this branch and PR
#5209's branch had each independently fixed the same class of problem
(an `origin/main` merge, an ADR-index regen, and an `AGENTS.md` budget
fix), so merging them back together conflicted only in these two QA
reports' addenda tails and frontmatter; resolved by renumbering into one
consecutive sequence. 305 tests passed.


## Addendum 17: rebound past PR #5230's second review-round fixes

**Rebound to** `7108a372ca4b6017db46b0f7de44452e42903c52`.

These commits landed only on `claude/adr-5209-review-fixes` (PR #5230),
not yet on this file's own `claude/adr-evaluation-tooling-6od8rd`
(PR #5209); rebinding here reflects that both QA reports live in the
same working tree on the branch this session validated, and
`post_qa_code_changes()` walks ancestry from the current `HEAD`, not from
either PR's own remote branch tip. Full detail in Addendum 18 of
`.agents/qa/session-5209-adr-review-fixes-stacked.md`: a hidden HTML
comment could forge an ADR status the same way a fenced code sample
could (Addendum 9's fix blanked `fence`/`code_block` tokens, not
`html_block`); two ellipsis placeholders where the canonical-source-mirror
rule requires a verbatim quote; a stale per-reader detection rationale;
and `_has_duplicate_top_level_keys` renamed to `_has_duplicate_keys` since
it stopped being top-level-only. 355 tests passed.


## Addendum 18: rebound past a self-inflicted taste-count ratchet trip

**Rebound to** `db398cb4cabdfe1d114130eff627c01e59b99413`.

The rename commit's own docstring addition tripped the whole-tree
taste-count ratchet it had nothing to do with fixing: it pushed
`detect_adr_changes.py` from 498 lines (warning) to 504 (the 500-line
error threshold). Full detail in Addendum 19 of
`.agents/qa/session-5209-adr-review-fixes-stacked.md`: fixed by
condensing the docstring's quoted-spelling illustration, back to 499
lines in both trees. `taste_count_ratchet.py`: OK (count == baseline
576). 355 tests passed, unchanged.


## Addendum 19: a Copilot review round on this branch's own head, eight findings

**Rebound to** `853b61fad7b09b6887c4c13e2cda92ff8f3f5922`.

Copilot reviewed this branch's head directly (not the stacked #5230
branch). Eight findings, all fixed and mutation-proven where the fix was
code, none a design reversal:

- **`_status_prose` swallowed a markdown parse failure into "no status
  section"**, silently exempting an unparseable record from
  `prose-frontmatter-agree`. `blank_code_block_lines`'s own contract
  (`scripts/utils/markdown_parser.py:175-180`) requires the exception to
  propagate. Fixed to catch it one level up, in `_check_prose`, and
  report a violation instead. New test
  `test_unparseable_markdown_is_a_violation_not_a_silent_skip`;
  mutation-proven by reverting the fix, which fails exactly that test.
- **`implemented-implies-decided` blocked a pattern the corpus already
  uses by design.** ADR-073's schema comment defines `implemented` as
  flipping "at first merged change", independent of `status`, and
  ADR-098 documents `status: proposed` with `implemented: true` as
  deliberate (a governance ADR cannot self-assert its own acceptance).
  Removed the check; baseline drops from 78 to 64 (-6 from the removal,
  -1 from a pre-existing, unrelated `frontmatter-parses` improvement
  already present on this branch, confirmed via `git stash` comparison
  before attributing it here).
- **ADR-055's `implemented: false` was the same conflation, applied to a
  live record.** 111 of 132 `runs-on` declarations are already ARM,
  well past "first merged change". Set to `true`; the remaining 21-job
  gap stays in the record's Metrics section and issue #5199.
- **The query-recipe docstring in `generate_adr_index.py` had the
  absent-vs-unterminated-frontmatter behavior backwards.** Verified by
  execution: absent frontmatter `continue`s past the snippet's check;
  unterminated frontmatter (opens with `---`, never closes) skips that
  `continue` and raises `ValueError`. The snippet crashes on the
  unterminated case rather than silently dropping it. Corrected,
  README regenerated.
- **ADR-024's Provenance line wrote "(commit PR #224)" and "(commit PR
  #476)"**, conflating pull request numbers with commit identifiers.
  Removed the parentheticals.
- **The PR description's checks list and violation count were stale**
  after the `implemented-implies-decided` removal (nine checks, 78
  violations, now seven checks, 64). Corrected on the PR itself.
- **Two absolute "no hook was bypassed" claims, in the session log and
  in this file**, were contradicted by this campaign's own stacked-branch
  QA report, which records one `git commit --no-verify` invocation on a
  scratch commit a `git reset --soft` discarded in the same command.
  Corrected both to the accurate scope: no *surviving* commit skipped a
  hook, and the one invocation reaches no ref.

The ADR-055 and ADR-024 corrections are appended to the existing
`ADR-024-025-042-055-status-redundancy-debate-log.md` (already covers
both records) rather than a new debate log, since neither is a
governance decision. 316 tests pass across `check_adr_lifecycle`,
`generate_adr_index`, the `adr-review` skill (all trees), and the
ADR-063 structural test.

## Addendum 20: a third Copilot review round, five fixed, one filed

**Rebound to** `5205bf29d366afe80d2174302a1d5326be6fae16`.

A further Copilot review on this branch's own head found six findings.
Commits `17e0a15f3` and `5205bf29d`:

- **`generate_adr_index.py`'s successor lookup missed non-padded and
  bare-integer `superseded-by` references** (`ADR-91`, bare `91`) that
  `check_adr_lifecycle.py`'s `_normalize_reference` already accepts. A
  record naming either form passed lifecycle validation while the index
  printed it as an unlinked plain-text reference. Fixed with a
  `_normalize_adr_id` helper mirroring the lifecycle gate's acceptance
  regex, at both the initial lookup and the chain-walk lookup.
  Mutation-proven: reverting the fix fails exactly the new test,
  `test_successor_lookup_accepts_non_padded_and_bare_int_references`.
- **`check_adr_links.py`'s external-scheme check was case-sensitive.**
  URI schemes are case-insensitive (RFC 3986 section 3.1);
  `HTTPS://example.test/ADR-005-x.md` was treated as a repository-relative
  path and reported as a false `unresolved` finding. Fixed by
  lower-casing before the scheme comparison. Mutation-proven.
- **A bare filename in `check_adr_links_baseline.txt` was a silent,
  unbounded wildcard.** A `finding.file in allowed` branch let one
  file-only baseline entry suppress every current and future ADR-link
  defect in that file, though the baseline file's own header requires
  `<kind>:<file>:<target>` and forbids anything looser. Fixed two ways:
  the wildcard branch is removed, and the baseline is now validated
  against that exact shape at load time, failing loudly (a `ValueError`
  config error, not a silent empty result) on a malformed entry. The
  existing test that asserted the old wildcard behavior,
  `test_whole_file_baseline_entry_suppresses_every_finding`, is flipped
  to `test_whole_file_baseline_entry_is_rejected_as_malformed`, asserting
  the new rejection instead of the forgeable old behavior.
- **The "ten records repaired" count was off by one.** `60b9ee306`
  (already on this branch) gave ADR-063 the frontmatter its prose had
  claimed since 2026-06-17, a lifecycle repair by the same definition as
  the other ten; the PR description's bolded list never counted it.
  Corrected to eleven records. The frontmatter/backfill counts also
  corrected, 54 to 53, confirmed by direct measurement:
  `adr_lifecycle_baseline.json`'s `frontmatter-parses` reads 53 and the
  generated index's Needs backfill section lists 53 rows.
- **Two debate logs had gone stale**, corrected in commit `5205bf29d`:
  `ADR-corpus-repair-5189-5201-debate-log.md`'s resolution table still
  described ADR-055 as `implemented: false` after the second round's
  correction reversed it; `ADR-023-032-033-link-repair-debate-log.md`'s
  verdict said ADR-023 was "left without frontmatter" and named a
  `status-section-present` check that is not one of the seven shipped
  checks. Both corrected in place with a note explaining what changed
  and why, rather than silently rewriting the historical record.
- **Deferred, filed as issue #5270**: neither `check_adr_lifecycle.py`'s
  `--write-baseline` nor `check_adr_links.py`'s baseline file enforces
  that its ceiling can only fall relative to the PR's base branch, so a
  branch could in principle raise either and commit the raised version
  alongside the regression it should have caught. Same forgeability
  class already proven against the debate-log gate in #5205; filed for
  follow-up rather than expanding this already-oversized review-response
  round further.

Test counts: `check_adr_links` 79 tests (up from 66, +13: the malformed-baseline
coverage plus the two new scheme-case parametrize entries), `generate_adr_index`
73 tests (up from 72, +1). All four touched suites plus
`test_pre_pr_sequence_registry.py` pass together: 272 tests. `check_adr_links.py
--repo-root .` and `check_adr_lifecycle.py --repo-root .` both re-run clean
against the full corpus (0 violations; 64 baselined violations, no check above
its baseline). `generate_adr_index.py --check` confirms the generated index
still matches: the real corpus has no non-padded or bare-integer
`superseded-by` value today, so the normalization fix is latent-defect
coverage, the same shape as the original `_get_adr_status` fix.

## Addendum 21: a fourth Copilot review round, two MUST-7 gaps, plus a backlog cleanup

**Rebound to** `d1fc64595bf5bc6e9c2d54b6a4210ef194f7eff7`.

A fourth Copilot review on this branch's own head found two
`.claude/rules/ci-scripts.md` MUST-7 worktree-identity gaps. Both fixed,
mutation-proven:

- **`generate_adr_index.py:main()` never verified the caller's cwd before
  writing.** Relative `--adr-dir`/`--output` are anchored to `_REPO_ROOT`
  (derived from `__file__`), not `Path.cwd()`. Added the identity check
  MUST-7 requires, mirroring `scripts/generate_third_party_notices.py:446-452`
  verbatim.
- **`check_adr_lifecycle.py --write-baseline` had the same gap**, fixed with
  a guard that fires only when `--repo-root` is the implicit `__file__`-derived
  default: every existing `--write-baseline` test in this file passes
  `--repo-root` explicitly, pointing at a synthetic `tmp_path` corpus
  unrelated to cwd, and an explicit `--repo-root` is a stated write target
  with no worktree-identity risk.

Five more findings from the same investigation pass, self-identified rather
than bot-flagged (all mutation-proven; real corpus and skill-portability
suite re-verified unaffected):

- **`generate_adr_index.py`'s `_status_of()` conflated an absent `status`
  key with one present but null or empty**, both returning `None` via
  `frontmatter.get("status")` and routing a record with partial, broken
  metadata into the same Needs Backfill bucket as a record with zero
  frontmatter. A present-but-broken status now raises, matching the
  function's own out-of-enum contract.
- **`check_adr_links.py`'s fence tracking was a bare open/closed toggle,
  not fence-character-aware.** A `~~~`-opened block containing a line that
  starts with backticks was incorrectly closed by that line under
  CommonMark's actual same-character rule. Now tracks the opening marker.
- **`check_adr_lifecycle.py`'s `_status_prose()` blanked code but not raw
  HTML blocks before searching for `## Status`.** `blank_code_block_lines()`
  deliberately keeps HTML visible for `check_skill_md_portability.py`, so
  widening it in place would have regressed that caller. Added
  `blank_non_prose_block_lines()` instead, sharing the existing blanking
  loop under a wider token-type set.
- **`memory-gate/SKILL.md` overclaimed Python as "the only sanctioned
  scripting language."** ADR-042 deprecates PowerShell for new scripts
  while explicitly keeping it for quick fixes and Windows-specific
  operations. Reworded; copilot-cli mirror regenerated.
- **`.claude/skills/adr-review/tests/test_detect_adr_changes.py` was a
  stale, colocated test file**, violating `.claude/rules/testing.md` MUST 6.
  Not a byte-for-byte duplicate of the relocated `tests/skills/adr-review/`
  suite: five cases were genuinely unique and ported before the stale copy
  (and its copilot-cli mirror) were deleted. Porting them pushed the
  target file past the taste-lint file-size ceiling; split into a new
  `test_detect_adr_changes_cli_contract.py` sibling instead of a
  suppression, matching the existing `_encoding.py` / `_duplicate_keys.py`
  split pattern in the same directory.

Ten round-2/3 threads closed out this round that were already fixed in
code but never replied-to or resolved on GitHub (compaction interrupted
that step): duplicate-key rejection in both lifecycle files (`06c4b5abd`),
the ADR-063 test calling the canonical parser (`aed2530fb`),
`prose-frontmatter-agree` searching the whole body (`df9c75495`), ADR-link
targets resolved against the tracked inventory (`01798f214`), the
absent-vs-unterminated-frontmatter distinction (`a6e38f6b7`), the baseline
key including violation `kind` (`e2cb80a44`), `build_all.py` failing loud
on a missing ADR directory (`75a82f209`), `ADR-TEMPLATE.md` no longer
forbidding `## Status` (`483f74adb`), the "checks 2 to 9" containment note
corrected to "2 to 7" (`1d4960414`), and this description's own stale
check/violation counts (already corrected in a prior round). One thread,
`ADR-005-status-duplication-debate-log.md`'s claim that four records "keep
their prose status sections," was genuinely still stale (their nuance
moved to purpose-specific headings after the log was written) and is
corrected in this round, verified against each file directly rather than
from memory.

Test counts: `check_adr_lifecycle` 116 tests (up from 111), `check_adr_links`
80 tests (up from 79), `generate_adr_index` 78 tests (up from 73), plus 6
new tests in `tests/test_markdown_parser.py` for `blank_non_prose_block_lines`
and 6 new tests in `tests/skills/adr-review/test_detect_adr_changes_cli_contract.py`.
`check_adr_lifecycle.py --repo-root .` and `check_adr_links.py --repo-root .`
both re-run clean against the full corpus (64 baselined violations for the
former, 0 for the latter, no check above its baseline). `taste_count_ratchet.py`
confirmed at 576 (the baseline), after the file-size split above.

## Addendum 22: a fifth Copilot review round, three findings fixed

**Rebound to** `fefa8bf5e0ddd4c6d416032c2e35e62070b82765`.

A fifth Copilot review on this branch's own head found three defects,
all fixed and mutation-proven:

- **`check_adr_links.py`'s baseline allowance was per-key, not per-finding.**
  `Finding.key()` is `kind:file:target` with no line number, so two
  occurrences of the same broken link sharing a key (or a later, genuinely
  new occurrence that happens to match an already-baselined one) both
  matched a single `in` membership test. One baseline entry silently
  suppressed every finding sharing its key, forever.
  `find_broken_adr_links()` now discards each baseline entry from a working
  copy on its first match, so a second occurrence of the same key still
  surfaces. The real corpus had exactly this shape: `docs/search-dont-load.md`
  cited the same absolute ADR-007 link on two lines under one baseline
  entry. Both are fixed (relative links) rather than double-baselined, and
  the stale baseline entry is removed. New test:
  `test_a_second_identical_finding_is_not_covered_by_one_allowance`; it
  failed against the code as first shipped, on the `in`-check.
- **`pre_pr.py` did not re-export `validate_adr_links`**, breaking its own
  documented promise ("the imports below keep
  `from scripts.validation.pre_pr import X` working for callers and tests")
  for one caller. Fixed by adding the missing import. Writing the most
  literal version of that contract as a test (identity comparison against
  `pre_pr_sequence`'s bound names) surfaced the same promise already broken
  for 15 unrelated pre-existing validators; that gap is filed as issue
  #5272 rather than fixed here, matching this campaign's own precedent
  (#5205, #5270) for a proven pre-existing defect found along the way. The
  shipped test is narrowed to the two ADR validators this PR owns.
- **`generate_adr_index.py`'s `_INTRO` carried two inaccurate claims about
  its own documented query recipe.** First, `_blocker_cell()`'s docstring
  claimed a past-due `review-by` date "is marked rather than silently
  rendered"; false, the cell renders the date identically whether current
  or overdue, and `check_adr_lifecycle.py`'s `CHECKS` tuple has no rule
  that reads `review-by` at all (verified: the string does not appear in
  that file). Corrected to say nothing today flags an overdue date, and
  the check belongs to issue #5193. Second, the recipe's fence search
  (`text.index('\n---', 3)`) matched any line merely starting with three
  dashes, not the exact closing fence `_FRONTMATTER_RE` requires (three
  dashes immediately followed by `\r?\n`). A closing line padded with one
  trailing space (`"--- \n"`) fails `_FRONTMATTER_RE`, so the real
  generator raises `AdrIndexError` for that file; the old recipe matched
  the padded line anyway and printed an answer with no error, silently
  disagreeing with the generator. Replaced with a regex requiring the
  same `\r?\n` on both sides of the dashes. New test:
  `test_the_documented_recipe_agrees_with_the_generator_on_a_padded_closing_fence`;
  it failed against the recipe as first shipped (`DID NOT RAISE
  ValueError`). `.agents/architecture/README.md` regenerated;
  `generate_adr_index.py --check` confirms no further drift.

Test counts: `check_adr_links` 81 tests (up from 80), `generate_adr_index`
79 tests (up from 78), `pre_pr_sequence_registry` 10 tests (up from 9,
including the new `TestPrePrReexportsTheAdrValidators` class). All three
mutations were reverted before being re-verified as fixed (backup/restore
via `/tmp`, never `git checkout --`, per the round-4 near-miss this
campaign already recorded). `taste_count_ratchet.py` confirmed at 576
(the baseline, unchanged).

## Addendum 23: a sixth Copilot review round, four findings fixed

**Rebound to** `890da965b710b153be17aeb617ad895d2ec6dbf6`.

A sixth Copilot review round on this branch's own head found four
defects, all fixed and mutation-proven:

- **`check_adr_links.py`'s `scan_file()` read tracked file content with
  `errors="replace"`.** A non-UTF-8 byte in a tracked markdown file was
  silently substituted with U+FFFD and scanned as if it were valid text,
  which could turn a genuinely broken link into one that happens to
  re-parse as resolvable, or the reverse. Removed: this is a plain file
  read, not one of the `subprocess` text-capture calls
  `check_subprocess_encoding.py` mandates `errors="replace"` for (issue
  #4261), so that convention does not reach it. `main()` already has a
  `UnicodeDecodeError` handler (exit 2) for exactly this.
- **`git_ls_markdown()`'s `subprocess.run()` IS one of those mandated
  calls**, so `errors="replace"` stays there (per #4261's own reason,
  quoted verbatim in the new docstring: "a child process on Windows can
  emit bytes invalid for UTF-8"). But a replacement-corrupted tracked
  filename doesn't match the real file on disk, so `scan_file()`'s
  `path.is_file()` check silently treated it as absent: zero findings,
  indistinguishable from an untracked file. Added a post-decode check
  that raises when any returned entry still carries the replacement
  character, closing the silent-skip without touching the mandated call.
  New test builds a real git-tracked file with an invalid-UTF-8-byte
  filename (raw bytes; not constructible through `pathlib.Path` directly)
  and confirms the raise.
- **`detect_adr_changes.py`'s `_get_adr_status()` accepted a non-scalar
  `status` value.** A YAML sequence or mapping under `status:` (valid
  YAML; ADR-073's schema never intends one) reached
  `str(status).strip().lower()` unconditionally and returned a Python
  repr such as `"['accepted']"` instead of `STATUS_UNKNOWN`. Fixed to
  mirror `check_adr_lifecycle.py`'s canonical `_status_of()` verbatim
  (`if value is None or isinstance(value, (list, dict)): return ""`).
  Applied to both shipped trees, confirmed byte-identical before and
  after; new tests parametrized across both. Trimming the added
  docstring prose to fit the file back under the 500-line taste-lint
  ceiling was needed on both trees (a 6-line net addition pushed each
  from 498 to 511).
- **The baseline header comment and a related docstring both said
  "twenty entries, three absolute"**, stale since round 5 removed a
  stale `absolute` entry; actual measured counts are 19 and 2. Corrected
  both, and added a test that measures the live baseline file and
  asserts the header states the true counts, so a future edit cannot
  drift the same way silently again.

Test counts: `check_adr_links` 85 tests (up from 81: the corrupted-filename
raise, the strict-decode raise, a `main()`-level exit-2 case, and the
baseline-header self-check), plus 8 new tests in
`tests/skills/adr-review/test_detect_adr_changes_status_scalar.py`
(parametrized across both trees). `taste_count_ratchet.py` regressed to
577 after the `detect_adr_changes.py` docstring addition crossed 500
lines on both trees (a genuinely new violation, unlike
`test_check_adr_links.py`, which was already over 500 before this
round); fixed by trimming the docstring rather than suppressing, back to
576 (the baseline). `build/scripts/build_all.py --check` confirmed clean
after committing both `detect_adr_changes.py` copies together (mid-edit,
before committing, `--check` correctly reports the uncommitted mirror as
"regen drift" under `OWNED_PREFIXES` for `src/`; that is the check
working as designed on an in-progress edit, not a defect).

**Addendum 23 correction.** Cursor Bugbot reviewed the round-6 push
minutes after it landed and found one more defect, in the round's own
new test: `test_git_ls_markdown_raises_on_a_non_utf8_tracked_filename`
wrote a raw `0xff` byte into a filename with no platform guard. ext4
accepts arbitrary bytes in filenames; APFS (macOS) and NTFS (Windows)
validate UTF-8 or reject the byte at file-creation time, so the test
would fail before it could exercise `git_ls_markdown` at all on those
filesystems. This repo's CI only runs this suite on
`ubuntu-latest`/`ubuntu-24.04-arm` (the Windows pytest job filters to
`@pytest.mark.windows_path` only), so CI itself was never at risk; the
guard protects a contributor running the full suite locally on a
non-Linux machine. Fixed with
`@pytest.mark.skipif(sys.platform != "linux", reason=...)`, matching
this repo's established `sys.platform == "win32"` skip convention
(`tests/test_check_doc_interpreter_portability.py` and others). 85
tests still pass.

**Rebound to** `bfad327fb752a4bc2a476a2e13fd6d01cd9cd773`. Cursor's own
autofix agent pushed `602340af3` directly to this branch minutes after
the local fix above, landing the identical fix
(`@pytest.mark.skipif(sys.platform != "linux", ...)`) independently on
top of the same parent commit. Merged rather than force-pushed over;
the only conflict was the two skipif reason strings, resolved by
keeping the local version's longer one (names the actual filesystems
and cites the finding source). 85 tests pass after resolution; no other
content differed between the two commits.

## Addendum 24: a seventh Copilot review round, five fixed, one filed

A seventh Copilot review found two new defects plus seven suppressed
("previously missed, code unchanged since last review") findings. Six
fixed, one filed as follow-up, one confirmed already resolved by a
documented earlier decision:

- **`detect_adr_changes.py`'s `_has_duplicate_top_level_keys` undersold
  its own behavior.** The PyYAML constructor it registers fires for
  every mapping node the loader builds, not only the document root, so
  a duplicate nested inside a mapping value is caught too; the existing
  `test_a_nested_duplicate_is_caught` already proved it. Renamed to
  `_has_duplicate_keys` across both shipped trees, the test file, and
  the two files that reference it by name.
- **The same function's "Mirrors" docstring quoted the canonical
  `_no_duplicate_keys` with a `raise ...` placeholder**, not the real
  line, violating `.claude/rules/canonical-source-mirror.md`'s
  character-for-character requirement for a Mirrors claim. Replaced
  with the actual fragment from `generate_adr_index.py:198-205`.
- **`check_adr_lifecycle.py`'s module docstring listed four historical
  defects as though this gate closes all of them**; two are
  intentionally not violations (`implemented: true` + `proposed` is
  deliberate per ADR-098; a missing `## Status` section is skipped, not
  flagged, since the frontmatter enum is authoritative). Clarified
  which two the gate actually closes.
- **The removed check was mislabeled "a ninth check"** when the active
  list holds seven, making it the eighth. Corrected.
- **Both `check_adr_lifecycle.py` and `generate_adr_index.py` accepted
  an empty or misrouted ADR corpus as clean.** `scan()`/`collect_records()`
  on zero real `ADR-NNN-*.md` matches returns zero violations or an
  index whose sections all read `None`, and each `main()` exited 0.
  Both now reject a directory with no filename-pattern match before
  scanning or generating, using each script's own filename regex so
  `ADR-TEMPLATE.md` alone does not count as evidence records were
  examined. Five existing `check_adr_lifecycle.py` config-error tests
  wrote no ADR record and would have silently started passing for the
  new reason instead of the one they assert; each got a valid ADR
  fixture so the original assertion is still what runs.
- **`generate_adr_index.py`'s worktree-identity guard ran before
  `--check` too**, a read-only path with nothing to protect against,
  so a caller with absolute paths and a cwd outside the repository got
  exit 2 for a comparison that never writes. Scoped the guard to the
  generation branch only.
- **The per-check ratchet in `check_adr_lifecycle.py` compares only
  totals**, so fixing one baselined violation and introducing a
  different one under the same check nets to a pass. Same forgeability
  class as #5205 and #5270 but a distinct mechanism (no base-ref
  involved at all); filed as
  [#5273](https://github.com/rjmurillo/ai-agents/issues/5273) rather
  than redesigning the baseline format inline in an already-oversized
  review-response round.
- **The four-backtick CommonMark fence gap in `check_adr_links.py`**
  Copilot re-raised is not new: the module's own docstring already
  documents it as a deliberately deferred scope limit from an earlier
  round ("Length is not tracked... deferred rather than guessed at,"
  citing this same PR's review). No action; already resolved and
  recorded.

Three commits, five files, 21 new/modified tests, all mutation-proven
(guard removed, target test fails for the stated reason, guard
restored). 200 tests pass across the touched suites
(`test_check_adr_lifecycle.py`, `test_generate_adr_index.py`, the
`adr-review` suite).

**Addendum 24 correction.** The full `pre_pr.py` push gate surfaced four
`test_build_all.py` failures the round-7 diff above did not touch
directly: fixtures that create `.agents/architecture` empty to test
unrelated `build_all.py` behavior (skills generation, untracked-file
detection, skill-mirror staleness). `_build_adr_index()` runs
unconditionally inside `build_all.run()` by that function's own design
(it deliberately does not pre-check and skip a missing corpus, per its
docstring and PR #5209 review discussion_r3831902216), so every fixture
driving `run()` now needs a real ADR record, not an empty directory.
Added a `_write_minimal_adr()` helper and used it at the four affected
call sites. 90 tests pass in `test_build_all.py`; the sibling
stale-mirror test now fails for the mirror staleness it actually tests
(confirmed by its own "STALENESS DETECTED" output), not a masked ADR
error it had been coincidentally passing through before.

**Rebound to** `7e8d3f850e184853e7fd8ff2f25d63e4b683dec4`.

**Addendum 24, second correction.** The round-7 review's remaining two
findings, investigated after the two corrections above landed:

- **`check_adr_links.py`'s four-backtick fence gap was re-raised as a
  live, unresolved thread**, not merely a suppressed repeat: the
  earlier docstring calling it "deferred rather than guessed at" was
  itself the defect, since it staked the deferral on a corpus property
  ("no fence in this corpus nests same-character runs of different
  lengths") that was never something the scanner could rely on going
  forward. Fixed this time: `FENCE` now captures the whole run, and
  `scan_file` tracks the opening character and its length, closing only
  on a fence-shaped line whose character matches and whose length is at
  least as long, per CommonMark (spec.commonmark.org section 4.5). New
  test mirrors the existing character-mismatch test; mutation-proven.
  86 tests pass.
- **`generate_adr_index.py`'s summary/title extraction has the same
  class of gap** (`_FENCE_RE` matches only triple-backtick fences, and
  `_section_body` searches for the section heading before any fence is
  stripped, so a heading-shaped line inside a code example can match
  instead of the real heading). Unlike the sibling fix above, this
  scanner is a whole-body regex substitution, not a per-line state
  machine, so converting it to the same stateful approach is a larger
  change across two functions. Filed as
  [#5274](https://github.com/rjmurillo/ai-agents/issues/5274) rather
  than fixed inline, following the same-PR precedent (#5205, #5270,
  #5273): this is a data-quality issue in a generated index cell, not a
  gate that can pass or fail incorrectly.

**Rebound to** `1c6da1909c0f335c06e760fb31675cc6ca68add2`.

## Addendum 25: an eighth Copilot review round, five fixes across five files

Copilot posted two separate review submissions on the same commit
(`ebcf4f52f`), 35 minutes apart, each listing a different "previously
missed" suppressed-findings set. The first submission's items (duplicate-key
rename, the Mirrors verbatim fix, the defect-list docstring, the ordinal
correction, the cwd-guard scope, the empty-corpus guard, the four-backtick
fence fix) are Addendum 24 above. This addendum covers the second
submission's six items, confirmed genuinely unprocessed by cross-referencing
both reviews' timestamps and bodies before starting:

- **`invoke_session_start_gate.py`'s `check_session_log_gate()` docstring
  asserted two "Mirrors" claims (AGENTS.md no longer lists a session log;
  the pre-commit gate validate-if-present contract) without quoting either
  source**, violating `.claude/rules/canonical-source-mirror.md`'s
  character-for-character requirement. Added both quotes: `AGENTS.md`'s
  Start row (`Init Serena|Read HANDOFF+latest issue handoff|Resume
  check|Search mem|Verify git`, no session-log step named) and
  `.claude/rules/session-logs.md` MUST 1's validate-if-present description
  verbatim.
- **`check_adr_links.py`'s external-link detection used a fixed
  `("http://", "https://", "mailto:", "ftp://")` tuple**, so `ssh://`,
  `git://`, and any other valid URI scheme fell through and were treated as
  a (broken) internal ADR reference. Replaced with a regex derived from RFC
  3986 section 3.1's scheme ABNF (`scheme = ALPHA *( ALPHA / DIGIT / "+" /
  "-" / "." )`), plus a `path.startswith("//")` check for the
  protocol-relative form RFC 3986 section 4.2 names a "network-path
  reference." New parametrize cases for `ssh://`, `git://`, mixed-case
  `SSH://`, and `//example.invalid/...`; mutation-proven by reverting to
  the old tuple check, which fails all four.
- **`check_adr_links.py`'s `validate_adr_links()` and `main()` both printed
  a bare violation count**, so "0 violation(s)" against an existing but
  emptied or narrowed markdown-file scope reads identically to a completed
  scan of the full one. Added a `_scannable_files()` helper (duplicating
  `find_broken_adr_links()`'s default-path candidate computation rather
  than changing that function's return type, which 30+ existing call sites
  depend on as `list[Finding]`) and an examined-file count in both
  messages. Mutation-proven at both call sites.
- **`check_adr_lifecycle.py`'s `run()` had the same gap** in its `[OK]`
  (write-baseline) and `[PASS]` messages. `main()` already rejects a fully
  empty corpus before `run()` runs (Addendum 24's empty-corpus guard), so
  this closes the case that guard cannot: a narrowed-but-nonzero scope.
  Read the record count once via `collect_records()`, separately from
  `scan()`'s own internal call, since `scan()`'s `list[Violation]` return
  type also has many existing dependents. Mutation-proven at both
  messages.
- **`generate_adr_index.py`'s `_run_check()` had the same gap** in its `OK`
  message. Unlike the two fixes above, no duplicate read was needed:
  `render_index()` already takes the record list as an argument rather
  than recomputing it internally, so splitting the existing
  `collect_records()`/`render_index()` call into two statements was free.
  Mutation-proven.

Four commits, seven files (five source, two tests), 5 new/modified test
functions, all mutation-proven (fix reverted, target test fails for the
stated reason, fix restored). Test counts: `check_adr_links` 92 (up from
90, +2), `check_adr_lifecycle` 120 (up from 118, +2), `generate_adr_index`
83 (up from 82, +1), `invoke_session_start_gate` unchanged at 13 (docstring
only, no behavior change). All four suites together: 308 tests pass.
`ruff check` clean across every touched file.

**Rebound to** `80ba38e0c39c111bb73c60246cf113e634aa124c`.

**Addendum 25 correction.** The round-8 diff above grew
`check_adr_links.py` from 491 to 537 lines, crossing the 500-line
taste-lint ceiling for the first time; `pre_pr.py`'s taste-count-ratchet
caught it as a real +1 regression against the 576 baseline. 243 of the 537
lines are comments and docstrings, so suppressed with the documented
per-repo escape rather than split, matching `generate_adr_index.py`'s
existing precedent for the same rule. Ratchet confirmed back at baseline.

**Rebound to** `702e3819074c2d623fda38bea5d4900d69eb67f2`.

## Addendum 26: a ninth Copilot review round, two fixed, one filed, one rebutted

A ninth Copilot review landed while round-8's fixes were still local
(queued against commit `47492781b`, the pre-round-8 head): two suppressed
findings plus two inline review comments. Investigated all four before
acting; two were genuine and fixed, one was a real defect too large to fix
inline and was filed as a follow-up issue, and one was a re-raise of an
already-considered and documented design decision.

- **`check_adr_links.py` accepted an empty-but-valid repository root as
  clean.** `find_broken_adr_links()`'s default path calls `git_ls_markdown()`
  (`git ls-files -z *.md`), which succeeds with empty output when
  `repo_root` resolves to a real git repository that happens to track zero
  markdown files. `validate_adr_links()` and `main()` would then scan
  nothing and print the identical "0 violation(s)" a genuinely clean
  full-corpus scan prints, so a wrong-but-valid repository root
  manufactured a green result. `main()`'s existing
  `subprocess.CalledProcessError` handler already covers "not a git
  repository at all"; this closed the narrower "valid git, empty result"
  case that handler cannot catch. Both entry points now fail closed
  (`main()` returns 2, `validate_adr_links()` returns `False`) when the
  examined-file count is zero. New tests:
  `test_main_fails_closed_on_a_valid_repo_with_no_tracked_markdown`,
  `test_validate_adr_links_fails_closed_on_a_valid_repo_with_no_tracked_markdown`.
  Mutation-proven.
- **`scan_file()`'s fence tracker closed on any fence-shaped line matching
  the opener's character and length, even with trailing text after the
  marker.** Per CommonMark (spec.commonmark.org/0.31.2/#fenced-code-blocks,
  quoted verbatim): "The closing code fence may be preceded by up to three
  spaces of indentation, and may be followed only by spaces or tabs, which
  are ignored." A line like `` ```python `` inside an already-open ` ``` `
  block is content (an inner example), not a close. The old behavior closed
  on it, then reopened on the real closing fence: a link inside the example
  could be reported broken (false positive), and a broken link in the live
  prose that followed could be silently swallowed into a fence that never
  closes (false negative). Fixed by requiring the closing candidate's
  trailing text to be whitespace-only; openers keep allowing any info
  string. New test:
  `test_a_fence_shaped_line_with_trailing_text_does_not_close_it`.
  Mutation-proven: reverting the trailing-text check reproduces exactly the
  false-positive-then-false-negative pattern the finding described (ADR-999
  reported broken, ADR-998 silently swallowed).
- **Three ADR frontmatter parsers disagree on closing-fence strictness**,
  confirmed by direct execution: a closing `---` line with one trailing
  space parses successfully via `scripts/validation/yaml_utils.py`'s
  `_parse_yaml_frontmatter` (and therefore `check_adr_lifecycle.py`, which
  deliberately mirrors it) and via `detect_adr_changes.py`'s
  line-`.strip()`-based split, but `generate_adr_index.py`'s
  `_FRONTMATTER_RE` requires the closing `---` to be followed immediately
  by `\r?\n` with nothing else, so it raises `AdrIndexError` ("opens with
  '---' but has no closing '---' fence; the frontmatter block is
  unterminated") on the identical input. A record could pass the lifecycle
  gate cleanly while crashing the index generator (and therefore
  `build_all.py --check`, wired into CI) on a one-space authoring
  difference. The complete fix means choosing one canonical closing-fence
  contract and propagating it across at least three parser
  implementations, one of which (`yaml_utils.py`) is a shared helper with
  an unmapped blast radius beyond these three call sites ("other
  validators" per its own docstring). Bigger and riskier than fits this
  round; filed as
  [#5275](https://github.com/rjmurillo/ai-agents/issues/5275), matching
  this PR's own precedent (#5205, #5270, #5273, #5274).
- **Re-raised, not fixed: `check_adr_lifecycle.py`'s `--write-baseline`
  worktree-identity guard only fires when `--repo-root` is the implicit
  default**, framed this round as "does not exempt explicit CLI targets"
  and "running from worktree A with `--repo-root` pointing at worktree B
  can still overwrite B's baseline." This is the same scoping round 4
  already considered and documented, and the framing does not hold against
  `.claude/rules/ci-scripts.md` MUST 7's own stated rationale, quoted
  verbatim: the threat is a script's *implicit* resolution being silently
  redirected by state the caller cannot see ("a local `core.worktree`
  value or a `GIT_WORK_TREE` environment variable redirects it to a
  directory you are not standing in ... the redirection is always
  something a person or a tool set on purpose, which is exactly why a
  script that inherits it has no way to notice"). A caller-typed
  `--repo-root` is the opposite of that: nothing is inherited or hidden.
  Worktree A/B is a possible user mistake, not an undetectable one, and no
  mechanism could distinguish a mistaken B from an intentional one without
  breaking every existing test that deliberately points `--repo-root` at
  an unrelated `tmp_path` fixture. Strengthened the docstring to name this
  specific re-raise and rebut it directly, so the next reviewer sees the
  reasoning was already applied to this exact framing rather than
  re-deriving it. No code change.

Two commits, three files touched, 3 new test functions, both behavioral
fixes mutation-proven. Test counts: `check_adr_links` 95 (up from 92, +3),
`check_adr_lifecycle` unchanged at 120 (docstring only). Both suites
together: 215 tests pass. `ruff check` and the whole-repo taste-count
ratchet (576, at baseline) both clean.

**Rebound to** `8a702a650b1bb4e4ae02916f4b777e448babf0ca`.

**Addendum 26 correction.** The round-9 push surfaced six failures in
`test_validation_pre_pr.py` that neither local `pre_pr.py` run (round 8 or
round 9) caught, because `pre_pr.py` invoked directly does not run the full
pytest suite; only the push-time lefthook `python-tests` job does. Root
cause: `_healthy_git_run`'s blanket `subprocess.run` mock answers any git
command other than `symbolic-ref`/`rev-parse` with `stdout=""`, so
`git_ls_markdown()`'s `git ls-files -z *.md` call returns an empty list
under the mock regardless of the real repo's tracked files, which the new
empty-corpus guard correctly (but here spuriously) treats as a
wrong-but-valid repository root. Fixed by adding "ADR Link Resolution" to
the existing `corpus_gates` bypass set in
`_sequence_with_passing_corpus_gates()`, the same treatment already given
to the other real-filesystem-dependent gates in that test file. Same class
of regression as round 7's `test_build_all.py` fixture fix (Addendum 24
above): a new fail-closed guard exposing a pre-existing test mock that
never modeled the corpus state the guard now checks. Full pytest suite
re-run clean: 28090 passed, 74 skipped, 0 failed.

**Rebound to** `416ef5e427de0fe97f7e3dcae61812d17ffe1791`.

## Addendum 27: merge of `origin/claude/adr-evaluation-tooling-6od8rd` (PR #5209), closing this branch's own "dirty" state

PR #5230's base branch had moved 18 commits ahead of this branch's recorded
base SHA (`886d353aa`), a separate review-fix campaign against PR #5209
covering rounds 4 through 9 of Copilot/Cursor review on that branch's own
head. `git merge origin/claude/adr-evaluation-tooling-6od8rd --no-edit`
(no rebase, no force-push, per `universal.md` MUST-1).

Eight files conflicted. Two were this file and its sister
`session-5209-adr-review-fixes-stacked.md`: both branches had independently
inserted new addenda after a shared "Addendum 11"/"Addendum 15" point (this
file's own prior merge-back had already renumbered once), so origin's
Addenda 12-19 here (and 14-21 in the sister file) are appended after this
branch's own continuation and renumbered to a single consecutive sequence
(19-26 here; 20-27 there) rather than dropped, with every internal
cross-reference between the two files rewritten to match.

Six were code/test conflicts, all real (not whitespace-only), because both
branches independently fixed overlapping defects during their own Copilot
review rounds:

- `.claude/skills/adr-review/scripts/detect_adr_changes.py` (+ its
  `src/copilot-cli/` mirror): both branches independently renamed
  `_has_duplicate_top_level_keys` to `_has_duplicate_keys` for the same
  reason (the constructor catches nested duplicates too, not only
  top-level). Kept the more complete docstring, corrected to attribute the
  rename to both PR #5209 and PR #5230's review rounds rather than either
  alone.
- `build/scripts/generate_adr_index.py`: cosmetic difference in how the
  docstring cites `detect_adr_changes.py`'s rename; kept the fuller version
  that names the rename explicitly.
- `scripts/utils/markdown_parser.py`: both branches independently extracted
  the same shared blanking helper behind `blank_code_block_lines` and
  `blank_non_prose_block_lines`, under two different names
  (`_blank_block_token_lines` vs `_blank_block_lines`) and two different
  file layouts (helper-and-wrappers together vs. wrappers defined later in
  the file). Resolved to origin's layout (`_blank_block_lines`, wrappers
  defined later) since it matched the non-conflicting remainder of the file
  and avoided a duplicate-definition mess the other layout would have left.
- `scripts/validation/check_adr_lifecycle.py`: **a real behavioral
  conflict, not just wording.** This branch's `_status_prose` caught any
  exception from `blank_non_prose_block_lines` internally and returned
  `None` (silently exempting an unparseable record from
  `prose-frontmatter-agree`). Origin's version let the exception propagate,
  to be caught one level up in `_check_prose` and converted into a
  violation instead of a skip, exactly the fix origin's own PR #5209
  review round made to this same defect. The non-conflicting, already-merged
  `_check_prose` body already implements the catch-and-report-violation
  side of that contract, so keeping this branch's internal catch would have
  silently reintroduced the bug origin fixed, with `_check_prose`'s own
  exception handler becoming dead code. Resolved to origin's version
  (propagate, no internal catch).
- `tests/validation/test_check_adr_lifecycle.py`: the two branches wrote a
  same-named test (`test_a_status_heading_inside_an_html_comment_...`) for
  two different scenarios: this branch's checked that a real status
  elsewhere in the body is still found despite a misleading HTML comment
  (1 violation expected); origin's checked that a comment-only "status"
  with no real section elsewhere is not read as the record's status at all
  (0 violations expected). Both are genuine, non-overlapping cases, so kept
  both as two separate tests rather than picking one.

The `check_adr_lifecycle.py` conflict is the one judgment call in this list
that changes runtime behavior rather than only prose: verified against the
non-conflicting `_check_prose` body before resolving, not merely by
preference between two plausible edits.

Full pytest re-verification, and the final `qaCommit` rebind for the
resulting merge and any follow-up fixes, are recorded in a following
addendum once complete.

## Addendum 28: the merge's own regression, found by the push gate

The merge in Addendum 27 introduced a defect the merge itself could not
surface: `tests/test_markdown_parser.py` ended up with two classes both
named `TestBlankNonProseBlockLines`, one from each branch's own round of
adding coverage for `blank_non_prose_block_lines`. Git kept both bodies with
no textual conflict, since they landed at different line ranges in the
file. Python silently drops the first definition at import time (`F811`),
so the first class's five assertions never ran again after the merge, with
no test failure to flag it, since the second class still collected and
passed cleanly. The push-time `python-lint-ratchet` job caught it (`ruff`'s
`F811`), not the pytest run.

Consolidated into one class carrying the union of both branches' distinct
test behaviors, taking the stronger assertion where both covered the same
case (a five-line fenced-code check over a three-line one). Verified by
mutation: removing one of the merged class's test methods
(`test_blanks_a_block_level_html_comment`) drops collection from 72 to 71
tests in that file, confirming the class is live and not
shadowed. Fixed in `485b1db68`.

**A second push-gate finding, unrelated to the merge conflict itself:** an
em-dash in this file's own Addendum 27 prose (introduced while writing that
addendum, not carried over from either branch) tripped the
`em-dash-prohibition` gate. Corrected to a comma.

Full pytest suite re-run clean after the `F811` fix: 28092 passed, 74
skipped, 0 failed (`1324.62s`). `ruff count ratchet`, `python-lint-ratchet`,
`merge-tree-ratchet`, `taste-count-ratchet` (576, at baseline), and
`type-ignore-count-ratchet` all confirmed clean against the fix commit.

**Rebound to** `485b1db684a3cea5248f0e5d7dfa645f98a360b2`.

## Addendum 29: a tenth Copilot review round, four fixed, seven documented

A tenth Copilot review found 13 distinct items: 10 suppressed ("previously
missed") findings plus 3 new inline comments. Four were genuine code
defects, fixed and mutation-proven; one was a stale comment corrected
alongside one of those fixes; two were volatile-exact-count taste-lint
suppressions reworded per the review's own suggestion; seven were stale
debate-log references corrected with two unifying notes (matching each
file's own established correction pattern) rather than seven separate
edits.

- **`check_adr_links.py`'s `FENCE` regex accepted unbounded (and tab)
  indentation before a fence marker.** CommonMark caps fence indentation at
  three spaces (spec.commonmark.org/0.31.2/#fenced-code-blocks, quoted
  verbatim: "Four spaces of indentation is too many"). A four-space-indented
  ` ``` ` line put the scanner into fence mode anyway, silently hiding a
  broken ADR link in what CommonMark actually treats as live prose. Capped
  to `{0,3}` spaces. New tests confirm the four-space case is caught and the
  three-space boundary case still opens a fence. Mutation-proven.
- **`split_destination()` only stripped angle brackets when the raw
  destination ended in `">"`**, but a legal CommonMark destination can
  combine brackets with a title: `[ADR-005](<./ADR-005-x.md> "Title")`. The
  trailing title text made `endswith(">")` false, so the brackets were
  never stripped, `is_adr_target()`'s basename match failed, and a broken
  or wrong-numbered link written this way bypassed the gate entirely. Fixed
  by finding the closing `">"` explicitly instead of requiring it be last.
  Mutation-proven.
- **`check_adr_lifecycle.py`'s `write_baseline()` truncated and rewrote the
  only baseline file directly**, despite the module's own docstring
  claiming baseline rewrites are atomic. An interruption mid-write leaves
  invalid JSON in place, blocking every subsequent `pre_pr.py` run until
  someone reconstructs the baseline by hand. Fixed by writing through a
  temp sibling file plus `os.replace()`, mirroring `scripts/
  ai_review_common/cache_guard.py`'s `_atomic_write_text` verbatim. New
  tests confirm no temp file survives a successful write, and a failed
  `os.replace()` leaves the pre-existing baseline untouched. Mutation-proven.
- **The same file's file-size taste-lint suppression said "an eight-check
  gate"**, but the eighth check (`implemented-implies-decided`) was removed
  two review rounds ago; the gate has seven. Corrected, and its other
  volatile exact line/file counts (including a sibling file's line count)
  dropped for the same reason as the next item.
- **Three taste-lint file-size suppressions cited exact line or test-case
  counts that had already gone stale** (`generate_adr_index.py`: "192 of
  the 558 lines" against an actual 882; `test_generate_adr_index.py`: "51"
  cases against 71+; `check_adr_links.py`: "243 of the 537 lines" against a
  count that had already moved twice). Reworded all three to state the
  ratio/rationale without a number that drifts on every subsequent edit,
  per the review's own suggestion ("Avoid a volatile exact count here").
- **Two debate logs described ADR-024, ADR-025, ADR-042 and ADR-055 as
  gaining or carrying a `## Status` section**, accurate for the diffs those
  logs record, but a later round (commit `1615ffa40`, "stop restating
  frontmatter in status prose") renamed those sections: `## Provenance` for
  ADR-024/025/055, `## Acceptance Evidence` for ADR-042, so a reader
  following either log today looks for a section that no longer exists.
  Added one correction note per file (matching each file's own established
  "leave the historical record unrewritten, note what changed after it"
  pattern, already used for the `implemented: true` reversal) rather than
  rewriting the seven flagged bullets individually. Both point to
  `ADR-024-025-042-055-status-redundancy-debate-log.md`, which already
  documents the rename in full.

Four commits, eight files touched, 6 new test functions, all three
behavioral fixes mutation-proven. Test counts: `check_adr_links` 99 (up
from 95, +4), `check_adr_lifecycle` 124 (up from 122, +2). All three
touched suites together: 304 tests pass. `ruff check` and the whole-repo
taste-count ratchet (576, at baseline) both clean.

**Rebound to** `c2055b1b91ddc7fb8406e15e6f9a84f41dfca220`.

## Addendum 30: a second merge of `origin/claude/adr-evaluation-tooling-6od8rd`, closing this branch's own "dirty" state again

PR #5230's `mergeStateStatus` went `DIRTY` again after PR #5209's own
round-10 review-fix commits landed on the base branch, 18 commits past
this branch's Addendum 27 merge point. `check_pr_merge_state.py`
confirmed it live, not a stale GitHub cache: `PR #5230
mergeStateStatus=DIRTY. Pull request workflows are unreachable while
this conflict persists.` A `git merge-tree <merge-base> A B` three-way
diff had misleadingly reported the merge clean; only an actual trial
merge in a disposable worktree (`git worktree add --detach`, `git
merge --no-commit --no-ff`) surfaced the two real conflicts, both in
this file and its sister.

Both conflicts were the same shape as Addendum 27's: this file's own
frontmatter (`qaCommit`) and its addenda tail, where both branches
independently continued the same numbering after the prior merge
point. Resolved the same way: kept both sides' addenda in one
consecutive sequence, appending origin's continuation after this
branch's own (this file's Addendum 29 above is origin's round-10
addendum, renumbered from its own "Addendum 20"; the sister file's
Addendum 30 is origin's shorter, cross-referencing version of the same
round-10 addendum, renumbered from its own "Addendum 22", with its
internal cross-reference to "Addendum 20 of the campaign report"
corrected to point at this file's Addendum 29).

Nine non-conflicting files merged automatically, since both branches
touched the same functions with non-overlapping edits: both debate
logs, three ADR gate scripts (`generate_adr_index.py`,
`check_adr_lifecycle.py`, `check_adr_links.py`), and four test files
(the three gate scripts' own tests plus `tests/test_markdown_parser.py`).
Verified against `git show --stat` on the merge commit
(`9d9cf3120ad407583d909cbd55ca57d43e36682f`), which lists 11 changed
files total: 9 non-conflicting plus the 2 QA files that conflicted and
were resolved by hand above. An earlier revision of this addendum said
six; Copilot flagged the mismatch (PR #5230) and a follow-up count of
eight also undercounted, since three ADR gate scripts have four test
files between them, not three.

**Three review findings against this branch's prior head (`3cb5bb0af`)
applied in the same pass, since the content they flagged survives into
this merge unchanged:**

- **Two absolute "no hook was bypassed" claims** (this file's own
  Governance Evidence section and its worktree-identity-guard
  discussion) contradicted this same file's later correction note,
  which discloses one `git commit --no-verify` invocation on a scratch
  commit a `git reset --soft` discarded in the same command. Narrowed
  both to "no surviving commit skipped a hook," matching the
  correction note's own stated scope.
- **The Addendum 28 mutation-evidence wording said "removing one of
  the merged class's assertions"**, but pytest collection counts test
  items, not assertions, so removing a single assertion cannot move a
  collection count from 72 to 71. The actual mutation removed a whole
  test method (`test_blanks_a_block_level_html_comment`). Reworded to
  name the method, here and in the sister file.
- **The sister file's human-readable "Validated at commit" header**
  still pointed at a commit and addendum number two rebinds stale.
  Updated to match the frontmatter's then-current binding before this
  merge landed.

**Two test-quality findings, also against the prior head, fixed in
`tests/test_markdown_parser.py`:** `test_blanks_a_block_level_html_comment`
and `test_keeps_inline_html_comment_on_a_prose_line` asserted only a
substring ("Accepted" absent, "prose" present), which a mutant leaving
the hidden heading intact while blanking only its content, or dropping
the inline comment's own text, would still pass. Both now assert the
exact transformed text.

Full pytest suite re-run clean after all resolutions and fixes: 28098
passed, 74 skipped, 0 failed. `ruff check` clean across the full tree.

**Rebound to** `9d9cf3120ad407583d909cbd55ca57d43e36682f`.

## Addendum 31: a merge from `origin/main` plus two unrelated commits, no ADR-tooling changes

The push gate caught the report outliving its code again: `origin/main`
merged into this branch (bringing in dependency bumps, `voice.md`'s
Confusion Protocol carve-out, and an unrelated ADR-073 prose correction),
plus this session added a merge-conflict resolution to
`tests/ci/test_validate_vendor_provenance.py` and a retrospective file.
None of the commits in `c2055b1b91ddc7fb8406e15e6f9a84f41dfca220..HEAD`
touch `check_adr_links.py`, `check_adr_lifecycle.py`,
`generate_adr_index.py`, or the `adr-review` skill's scripts.

Re-ran rather than bumped the SHA:

```
uv run pytest tests/validation/test_check_adr_lifecycle.py \
              tests/validation/test_check_adr_links.py \
              tests/build_scripts/test_generate_adr_index.py \
              tests/skills/adr-review/ \
              tests/skills/test_misc_skill_scripts.py \
              tests/validation/test_pre_pr_sequence_registry.py -q

============================= 504 passed in 13.42s =============================
```

504 rather than the prior 388/304 because the `.claude/skills/adr-review/tests/`
suite the earlier addenda ran separately has since been relocated to
`tests/skills/adr-review/` by an unrelated repo-wide colocated-test move
merged in from `origin/main`; the same test bodies, one path.
`check_adr_links.py` reports 0 violations across 1590 tracked files;
`check_adr_lifecycle.py` reports 64 violations across 102 ADR records
(up from 98 records at the prior addendum, from ADR-052's merge), no check
above its baseline; `generate_adr_index.py --check` reports the index
matches the corpus.

**Rebound to** `4d5b443a0c9ee104cd98bb40d9c13bbcf2130015`.

## Addendum 32: a third merge of `origin/claude/adr-evaluation-tooling-6od8rd`, plus the round-2 review fixes it had been blocking

PR #5230's `mergeable_state` went `dirty` a third time after PR #5209's
base branch advanced again (`dd20f49d3` -> `05161ccba`, one commit: an
ADR-055 table repair). A real trial merge in a disposable worktree
(same practice as Addenda 27 and 30) surfaced the same two files in
conflict as every prior round: this file and its sister. Both
conflicts were the familiar shape, frontmatter `qaCommit` and the
addenda tail with independently-continued numbering. Resolved the
same way: kept HEAD's own Addendum 30 above, appended origin's
continuation (its own "Addendum 21") as Addendum 31 above. 25
non-conflicting files merged automatically, including origin's own
resolution of the `tests/ci/test_validate_vendor_provenance.py`
conflict against `main` that Addendum 21 of the sister file's earlier
round had left as a merge-tree-ratchet CI failure on this branch;
merging it in resolved that failure too. 514 tests pass across the
touched suites (adr-review, `generate_adr_index`, `check_adr_lifecycle`,
`check_adr_links`, `markdown_parser`, `validate_vendor_provenance`).
Merge commit `7e2fc2f17b14295b363903dcf4353638f8c1c550`.

Two `/review` findings drafted during this session's `/review` run on
PR #5230, held uncommitted (`git stash`) since the scope-policy
pre-commit gate could not resolve this stacked PR's real base (the
`gh` CLI cannot authenticate in the sandbox that produced them) and
mismeasured the branch against `main` instead, landed in the same
batch once a human explicitly authorized the documented
`SKIP_SCOPE_CHECK=1` bypass for this specific situation:

- The `generate_adr_index.py:198-205` citation in both
  `detect_adr_changes.py` copies, stale by 11 lines after this
  campaign's own docstring growth, corrected to `209-216`.
- This addendum's own predecessor (Addendum 30) undercounted the
  prior round's non-conflicting-file merge at "Six"; re-verified
  against `git show --stat` on that merge commit
  (`9d9cf3120ad407583d909cbd55ca57d43e36682f`) at nine files. Corrected
  in place above.

Commit `ac48551ce7b4b29ca73e4792fe52ccb01c60540c`.

**Rebound to** `ac48551ce7b4b29ca73e4792fe52ccb01c60540c`.

## Addendum 33: a direct merge of `origin/main`, plus a taste-lint suppression the merge surfaced

This branch had never merged `origin/main` directly, only inherited
occasional main-merges indirectly through PR #5209's base branch. A
human explicitly authorized merging `origin/main` in and resolving the
result. `git merge --no-commit --no-ff origin/main` in a disposable
worktree (same practice as Addenda 27, 30, and 32), then repeated on
the real branch, surfaced six real conflicts, none the QA-doc shape:
five ADR governance documents and one test file, all in ADR-073
lifecycle-frontmatter territory. `origin/main`'s own bulk normalization
commit (`1d15e0d06`, "ADR-073 lifecycle frontmatter across 67 ADRs")
had landed independently of this branch's own ADR-073 backfill and
provenance work, so the same files carried two different, uncoordinated
edits.

Resolution, file by file:

- `ADR-005`, `ADR-042`, `ADR-063`: took `origin/main`'s normalized
  `date`/`decision-makers` frontmatter values as the later, deliberate
  bulk pass; kept this branch's body content changes (an Acceptance
  Evidence section, the dropped prose status-duplication, the
  `review-by` field) where `origin/main` had not touched the same
  lines.
- `ADR-032`: a trivial one-word wording difference in the same
  sentence from two independent edits; kept this branch's phrasing.
- `ADR-055`: kept this branch's full Provenance section (duplicate-slug
  history, exception-marker rename rationale, a metrics update, a
  review-schedule fix) over `origin/main`'s minimal frontmatter-only
  patch. First pass took `origin/main`'s `supersedes: []` on the theory
  that it was the more recent, deliberate decision; `check_adr_lifecycle.py`'s
  `supersession-reciprocal` ratchet caught that this was wrong; it rose
  from 0 to 2 because `ADR-024` and `ADR-025` already carry
  `superseded-by: ADR-055`, set by this branch's own `25b263d16` before
  `origin/main`'s bulk commit existed. `origin/main`'s author had not
  seen that commit when writing the struck-supersession note, so its
  `supersedes: []` broke a reciprocal relationship this branch had
  already completed correctly. Restored `supersedes: [ADR-024, ADR-025]`
  and rewrote the Provenance note to describe the reciprocal state
  accurately instead of the now-false "not yet in frontmatter" claim.
- `tests/test_adr_063_memory_skill_decomposition.py`: both sides
  independently fixed the same frontmatter-precedes-H1 test; kept this
  branch's version (asserts exactly one matching title line, carries a
  richer docstring naming the specific coupling bug it replaces).

Verified: `check_adr_links.py`, `check_adr_lifecycle.py`
(`supersession-reciprocal` 0/0 after the fix), `check_adr_uniqueness.py`,
and the ADR-063 test file all pass. 1481 tests across the merge's
non-ADR touched areas pass. No leftover conflict markers, no em/en
dashes in edited prose. Merge commit `72da57ae5f3bc2f19f5001013ae31cbf4fa88033`.

Re-running `scripts/ci/merge_tree_ratchet_check.py` against the fresh
`origin/main` after the merge landed still failed: `taste count ratchet:
REGRESSION. 577 > effective baseline 576`. Diffing full `(file, rule)`
violation sets between `origin/main` and this branch (`ci-scripts.md`
MUST-15 practice) isolated the single new entry to
`tests/validation/test_check_adr_links.py`, which crossed the 500-line
`file-size` threshold to 1001 lines over ten rounds of small regression-test
additions in this same campaign, no single round crossing the ratchet on
its own. Confirmed pre-existing on this branch
(`163fddb7a6960bba2dafc48b7e8232cb3b562b75:tests/validation/test_check_adr_links.py`
was already 1001 lines), not introduced by the merge. Splitting the file
into cohesive modules is real work out of scope for a merge task; applied
the documented `# taste-lint: ignore file-size` escape hatch (issue #3779)
with a rationale comment instead of raising the baseline (forbidden,
`ci-scripts.md` MUST-NOT-4). Fix commit `f1b026885ed51aea56f864b51eae4bf5cd096127`.
`merge_tree_ratchet_check.py` passes clean after that commit.

**Rebound to** `f1b026885ed51aea56f864b51eae4bf5cd096127`.

## Addendum 34: ADR index regeneration after the merge

`build/scripts/build_all.py --check` flagged `.agents/architecture/README.md`
as stale after Addendum 33's merge: many ADRs gained ADR-073 frontmatter
(from `origin/main`'s bulk commit and from this branch's own backfill)
that the generated index table had never picked up. Regenerated with
the documented order (`sync_plugin_lib.py` then `build_all.py`,
`ci-scripts.md` generator-ordering rule) in commit
`b0ab960ea4c8fc522ecad971bf77bb72428db710`, which also carried this
addendum and Addendum 35 of the sister file. No test changes; this is
a pure index regen plus QA-doc bookkeeping.

**Rebound to** `b0ab960ea4c8fc522ecad971bf77bb72428db710`.

## Addendum 35: Cursor Bugbot's ADR-055 table fix, a debate-log note, and a stale-count correction

Three more non-evidence commits landed: Cursor Bugbot's autofix agent
repaired ADR-055's broken Cost Impact table (`05161ccba`), the debate log
this record is covered by got a note recording that fix (`6794aa67d`),
and this report's own "Known gaps carried forward" section had two stale
carried-forward counts corrected against the committed baselines
(`45ed8d7f4`). None of the three touch the ADR-tooling scripts. Re-ran
the same evidence as Addendum 21; unchanged: 504 tests pass,
`check_adr_links.py` 0 violations across 1590 files,
`check_adr_lifecycle.py` 64 violations across 102 records at baseline,
`generate_adr_index.py --check` matches.

**Rebound to** `45ed8d7f41525a0b3cc838ca48d36e703d8e6934`.


## Addendum 36: retro remediation owner and a session-log claim correction

One more non-evidence commit (`00e590330`) touched
`.agents/retrospective/2026-08-25-pr5209-push-notification-false-completion.md`
(not one of the QA-evidence-exempt prefixes, so it re-triggers the staleness
check) to give an unowned remediation item issue #5301, and corrected the
2026-08-21 session log's `changesCommitted` evidence, which still claimed
"--no-verify... were all unused" outright after this report's own record had
already been corrected to "invoked once, on a scratch commit discarded via
`git reset --soft`, reaching no ref". No ADR-tooling script changed. Re-ran
the same evidence as Addendum 22; unchanged: `check_adr_lifecycle.py`
`[PASS] 64 violation(s) across 102 ADR record(s), no check above its
baseline`, `check_adr_links.py` 0 violations across 1590 tracked files.

**Rebound to** `00e5903306bfdbe1bc8296799b6d0e9f5094b86c`.

## Addendum 37: merged `origin/main`, resolved 6 conflicts, fixed a merge-driven taste-lint regression

`origin/main` had advanced with PR #5291 (a separate autonomous session's ADR-073 lifecycle-frontmatter campaign across 67 ADRs) and PR #5287 (an unrelated concurrent-commit guard). Merging it conflicted on `ADR-005`, `ADR-032`, `ADR-042`, `ADR-055`, `ADR-063`, and `tests/test_adr_063_memory_skill_decomposition.py`. Each was resolved by inspection, not by blindly taking one side:

- `ADR-005`/`ADR-042`: `date`/`decision-makers` conflicts. PR #5291's campaign preserved the wrong extraction for both (a later-event date mistaken for the original decision date); this branch's values matched the files' own prose exactly, so kept, with `decision-makers: [rjmurillo]` adopted from the campaign's uniform convention.
- `ADR-032`: a one-word grammar difference ("the template" vs "template"); kept this branch's more complete wording.
- `ADR-055`: the interesting one. PR #5291 added ADR-055's frontmatter independently and deliberately left `supersedes: []` with a note that the ADR-024/ADR-025 reciprocal edit was "owed to issue #5192". This branch had already completed that reciprocal (`superseded-by: ADR-055` on both targets, commit `25b263d16`), so the merge keeps `supersedes: [ADR-024, ADR-025]` and drops the now-stale placeholder note, replacing it with a Provenance paragraph recording why.
- `ADR-063`: `date` conflict, same shape as ADR-005/ADR-042 (this branch's value matched the file's own prose, `2026-06-01`; kept, plus PR #5291 dropped this branch's `review-by: null` field, which is a legitimate `ADR-TEMPLATE.md` field; restored).
- `tests/test_adr_063_memory_skill_decomposition.py`: both sides independently fixed the same test for the same reason (frontmatter now precedes the H1); merged to the stronger implementation (finds the actual first H1 and asserts it is the ADR-063 title, not just uniqueness of a matching line) plus this branch's richer docstring.

Merge commit `9f93fc1ef91f6ab28c59e320e12223402851f484`. Re-verified post-merge: `check_adr_lifecycle.py` improved to `[PASS] 1 violation(s) across 102 ADR record(s)` (down from 64, because PR #5291 fixed most of the corpus), `check_adr_links.py` 0 violations across 1590 files, the full `tests/test_adr_063_memory_skill_decomposition.py` suite (26 tests) passed, `ruff`/`mypy` clean on the merged test file.

The full `python-tests` suite then surfaced a real, narrow regression: `tests/ci/test_count_ratchet_against_real_git.py::test_the_shipped_baseline_describes_the_tracked_tree[taste_count_baseline.txt-current_count]` failed, `577 violations > baseline 576`. Root-caused by diffing `list_violations()` output across three trees (`origin/main` alone, this branch alone pre-merge, and the merged tree, via disposable `git worktree add --detach` copies, each independently measuring exactly 576): the only new entry was `conftest.py` crossing 500 lines (544), a pure merge artifact of two branches each independently adding content to the same root fixture file while staying under budget alone. Not a design change worth a mid-merge refactor of shared pytest fixtures; suppressed with the documented per-repo escape (`# taste-lint: ignore file-size`, matching the pattern this report's own Addendum 11 used), reasoned and dated in the comment. Re-verified: `list_violations()` back to 576, `conftest.py` excluded, `ruff check conftest.py` clean.

**Rebound to** `29eb28e9451ca0b3c285325f022a52ae271a87bc`, the commit carrying the suppression comment.

## Addendum 38: regenerated the ADR index after the merge

`build/scripts/build_all.py --check` (run as part of `pre-pr-validation` on the push this addendum responds to) correctly flagged `.agents/architecture/README.md` as stale: the origin/main merge brought in PR #5291's ADR-073 frontmatter across 67 records, changing dates, statuses, and decision-makers the generated index renders. Regenerated via `scripts/sync_plugin_lib.py` then `build/scripts/build_all.py`; `--check` now reports zero staleness. No ADR-tooling script changed; `check_adr_lifecycle.py` and `check_adr_links.py` re-run unchanged from Addendum 37.

**Rebound to** `bfd3a008d336ff6e4d8e50ef4cdb766a457d1a6a`.

## Addendum 39: a fourth merge, PR #5209's branch this time, correcting three dates the third merge got wrong

PR #5230's `mergeable_state` went `dirty` a fourth time: PR #5209's own
branch (this stack's real base) advanced past this branch with its own
independent merge of `origin/main` (`9f93fc1ef91f6ab28c59e320e12223402851f484`)
plus four follow-up commits, the last of which,
`b0c3550025863c37a0571964463ea3585d655888`, explicitly corrected ADR-005's
`date` from `2026-01-17` back to `2025-12-18`, stating the earlier value
"contradicted both the prose Date field in the document and the merge
resolution documented in QA Addendum 24".

That earlier merge resolution was mine, in Addendum 33 above: I had taken
`origin/main`'s bulk-normalized `date` for `ADR-005`, `ADR-042`, and
`ADR-063` on the theory that the later, deliberate campaign commit should
win. The other branch's independent resolution of the same three-way
conflict (its own Addendum 24, referenced above) instead kept each file's
original date because it matched that file's own `## Date` prose section,
and PR #5291's bulk campaign had mis-extracted a later, unrelated event
date (ADR-042's ratification date, in ADR-005's case) as if it were the
original decision date. Verified against each file's own body: ADR-042's
`## Date` section reads `2026-01-17`, not `2026-04-13`; ADR-063's reads
`2026-06-01`, not `2026-07-27`. Corrected all three to match, in a trial
worktree first, then on the real branch: `ADR-005` to `2025-12-18`,
`ADR-042` to `2026-01-17`, `ADR-063` to `2026-06-01`.

`ADR-055`'s `supersedes: [ADR-024, ADR-025]` conflict converged
independently on the same answer both branches had already reached (this
file's own Addendum 33 above, and the other branch's Addendum 24): took
the other branch's more precisely cited Provenance paragraph, which names
PR #5291 and the reciprocal commit `25b263d16` explicitly. The ADR-063
test conflict and this file's own addenda-tail conflict were resolved the
same way as every prior round: kept this file's own numbering (through
Addendum 38 above), appended the other branch's continuation (its own
Addenda 22-25) renumbered to Addenda 35-38.

Merge commit `d50df2fa38b0de179fa19b64820eb5af098c575d`. Verified post-merge:
`check_adr_links.py` 0 violations across 1590 files, `check_adr_lifecycle.py`
`supersession-reciprocal` 0/0, `check_adr_uniqueness.py` clean,
`build/scripts/build_all.py --check` reports no staleness, the ADR-063
test file (26 tests) passes, and `taste_count_ratchet.py` reports
575 violations against a 576 baseline.

**Rebound to** `d50df2fa38b0de179fa19b64820eb5af098c575d`.

## Addendum 40: a weakened test control, a PR-description rewrite, and 8 review threads closed

Six GitHub notifications arrived after the fourth-merge push landed: a stale
`PR Merge State` check on a superseded SHA (no action needed, CI recomputes on
the new head), a Copilot review summary restating the same points as its
line comments, a PR-VALIDATION bot PASS, and three substantive items.

**A real, previously-flagged test weakness, fixed.** Copilot's review found
`tests/test_markdown_parser.py::test_blank_code_block_lines_does_not_strip_the_same_comment`
asserted only `"Accepted" in blank_code_block_lines(text)`, so a mutant
blanking the `"Accepted"` line while leaving the comment's own `"## Status"`
line intact would still pass. This was already named as a known gap in an
earlier PR-description revision's `/review findings` section
("Not yet drafted, follow-up needed"); Copilot independently found the same
defect on the current head. Fixed in `34bfc867d`: asserts full output
equality against the unchanged input, matching the sibling positive control
(`test_blanks_a_block_level_html_comment`), which already asserted exact
transformed text for the same reason.

**A real defect on inherited code, verified and left unfixed here.**
Copilot flagged `.claude/skills/taste-lints/scripts/taste_lints.py:429`:
`_looks_like_yaml_value` rejects any multi-word unquoted scalar, so common
frontmatter like `description: Run all checks before push` fails
`_looks_like_yaml_mapping` and `_suppression_window` falls back to the
first-10-lines path. Verified real by reading the function. But
`git diff origin/main -- .claude/skills/taste-lints/scripts/taste_lints.py`
is empty: this file is byte-identical to `origin/main` on this branch,
arrived via merging `origin/main` (PR #5302, which wrote this exact code),
and is not authored or touched by PR #5230. Not fixed here, matching the
established pattern on this PR for `new_pr_validations.py` and
`workflows.json` findings: fixing it would expand this PR's diff into a
file it does not otherwise change.

**The PR description rewritten to explain the file-count mechanism instead
of chasing the number.** The diff has been reported at 2, 9, 10, 108/168,
114, and now 29 files across successive revisions, and Copilot flagged the
mismatch every time. The pattern is base-branch lag, not scope creep: this
branch merges `origin/main` and/or PR #5209's own branch, the diff
temporarily collapses toward the true 9-11 file scope, then one side
advances again and the diff balloons with inherited-but-unauthored content.
The description now splits "Files changed" into "this branch's own
contribution" (11 files, byte-different from `origin/main`) and "inherited
from merging `origin/main`" (18 files, byte-identical to `origin/main`),
so the count is explained structurally rather than re-derived after each
merge.

**Eight review threads investigated and resolved**, four of them already
addressed by content that had landed before the comment's anchor (the
`--no-verify` disclosure, the `test_blanks_a_block_level_html_comment`
control, both pytest-collection-count corrections, and the "Validated at
commit" header), one already-correct citation, one already-current file
count, the weakened test control above, and the file-count mechanism
explanation above. Each reply cites the specific commit or line that
resolves it rather than a bare "done".

**Rebound to** `34bfc867daf873f1b28ea6538a1c193c40bf379c`.

## Addendum 41: reverting my own regression on ADR-042 and ADR-063 dates, and a QA header mismatch

Two GitHub notifications arrived on PR #5230 after the previous push: a
Copilot review comment on `.agents/critique/ADR-073-phase2-backfill-debate-log.md:545`,
and a Copilot review comment on this file's own line 11.

**The debate log finding, investigated and fixed in the opposite direction
from what it literally suggested.** Copilot flagged the debate log's
`ADR-042 | accepted | 2026-04-13` row as stale against the live frontmatter
(which read `2026-01-17` after Addendum 39's merge-conflict resolution) and
asked for the row to be changed to match. Before making that edit, checked
ADR-073's own schema comment for what the frontmatter `date` field actually
means: `.agents/architecture/ADR-073-adr-lifecycle-frontmatter.md:49` reads
`date: YYYY-MM-DD          # last updated`. ADR-042 carries a genuine
"Amendment 1" section with its own `### Date` subheading reading
`2026-04-13` (line 169), and its Amendment Log table confirms the same date
for the amendment event (line 234). ADR-063 has the identical shape: an
"Amendment 2026-07-27" section (line 313) with real content, updating a
citation per ADR-088. The debate log's own deliberated table already had
both values right (`ADR-042` at line 545, `ADR-063` at line 563), each
following the full six-role debate documented earlier in that same file
(the "seven wrong date values" investigation, lines 592 to 609, which
names ADR-042 specifically and cites the confirming commit `4d1aaa5e1`,
PR #1647).

**What that means: Addendum 39's merge-conflict resolution was itself the
regression on these two records.** That addendum reasoned that PR #5291's
bulk campaign had "mis-extracted a later, unrelated event date... as if it
were the original decision date" for all three ADRs, and corrected all
three to match each file's own `## Date` section. That reasoning holds for
ADR-005, which carries no `## Amendment` section, so its `## Date` value is
also its last-updated value. It does not hold for ADR-042 or ADR-063: both
carry a later `## Amendment` section with real content, and the campaign's
values matched those amendment dates, not a mis-extraction. Addendum 39
checked only the top of each file and missed the later section. Restored
both frontmatter fields to the debate log's values
(`2026-04-13`, `2026-07-27`), added Batch 29 to the debate log itself
documenting the correction and citing this same evidence chain, and
regenerated `.agents/architecture/README.md`. Commit `d331cba4f`.

`check_adr_lifecycle.py`: 1 violation across 102 records, no check above
baseline (unchanged from Addendum 34). `tests/validation/test_check_adr_lifecycle.py`
(122), `tests/test_adr_063_memory_skill_decomposition.py`, and
`tests/validation/test_check_adr_links.py` (125 combined) all pass.

**The QA header mismatch, a real drift, fixed.** Copilot separately found
this file's own `**Validated at commit**` header (line 11) still read the
pre-fix-round commit `63c04c4029c289a973b29595cb516f2b0911c15c` after the
`qaCommit` frontmatter field had already been rebound to `34bfc867d...` in
Addendum 40. The sister report keeps the two fields in lockstep; this one
had drifted for one round. Both now read the current commit.

**Rebound to** `d331cba4f9ea50a32ca362ab0eb82f69b2188bb9`.

## Addendum 42: a real title-test gap, and the file count drifting again

Two more Copilot notifications arrived after the previous push.

**A real gap in the ADR-063 title test, found by Copilot, fixed.** An
earlier round's conflict resolution
(`tests/test_adr_063_memory_skill_decomposition.py`) kept this branch's own
implementation over the sibling branch's alternative, on the reasoning that
no proof of superiority had been found by inspection. Copilot's review
supplied that proof: `titles = [ln for ln in adr_text.splitlines() if
ln.startswith("# ADR-063:")]` filters for a matching line anywhere in the
document rather than checking the document's actual first H1, so a file
beginning with `# Wrong title` followed later by the real title would still
pass. Verified by mutating the fixture text (prepending a wrong H1) and
confirming the old filter-based check passed on the mutant while a
first-H1-by-position check correctly failed it. Fixed by locating the first
H1 with `build/scripts/generate_adr_index.py:114`'s own `_H1_RE` regex
(quoted verbatim per `canonical-source-mirror.md`) and asserting it, not a
filtered line, is the ADR-063 title. All 26 tests in the file still pass
against the real record. Commit `55fc50542`.

**The file count drifted from 29 to 32 again**, this branch's own recurring
pattern: the previous round's fix commits (`d331cba4f`, `a0912d444`) added
four files to this branch's own contribution (`ADR-042`, `ADR-063`,
`README.md`, the debate log) that the "Files changed" section had not yet
folded into its primary count, instead noting them in an "Also touched"
caveat. Re-measured against the base with `git diff --name-only
origin/claude/adr-evaluation-tooling-6od8rd...HEAD`: 32 files total, split
15 own-contribution (byte-differs from `origin/main`) versus 17 inherited
(byte-identical to `origin/main`). PR description rewritten to fold the four
files into the primary "own contribution" list rather than carrying a
separate caveat, and the summary line updated to 32.

`check_adr_lifecycle.py`: 1 violation across 102 records, no check above
baseline (unchanged). `tests/test_adr_063_memory_skill_decomposition.py`:
26 passed.

**Rebound to** `55fc50542fcb5a7b250bf0a28557478f995357e6`.

## Addendum 43: the title-test fix itself had the same reimplementation defect

A third Copilot review on the same test found that Addendum 42's fix had
not actually closed the gap it claimed to. The regex-based fix in
`55fc50542` located the first H1 by searching the whole `adr_text`,
including the YAML frontmatter block, rather than only the body
`build_record` passes to `_extract_title`
(`build/scripts/generate_adr_index.py:459,470`). A frontmatter YAML
comment starting with `#` would match before the real title. That is not
a hypothetical: `parse_frontmatter`'s own docstring (line 252-253) states
ADR-068 and ADR-085 both open their frontmatter block with exactly such a
comment. The claimed mirror ("matching that module's `_extract_title`
semantics exactly") was true of the regex pattern but false of the input
it was applied to, which `canonical-source-mirror.md`'s divergence-section
requirement exists to catch.

**Fixed by not reimplementing the extractor a second time.** Instead of
writing a second regex with the correct scope, the test now imports
`generate_adr_index` (via the same `import_skill_script` helper already
used for the ADR-review detector) and calls its `parse_frontmatter` then
`_extract_title` directly, matching `build_record`'s own call shape
exactly. This closes the input-contract gap by construction: there is no
second copy of the frontmatter-splitting logic left to drift.

Verified in both directions rather than assumed. Two throwaway mutations
against the real fixture file, restored after each: (1) prepending
`# Wrong title` to the H1's own line in the body shifts
`_extract_title`'s return from `"Decompose the Memory Skill Into Focused
Sub-Skills"` to `"Wrong title"` and fails the test, killing the original
defect Addendum 41 fixed; (2) prepending `# migration note` to the
frontmatter block leaves the extracted title unchanged and the test
passes, proving the frontmatter-comment false-rejection this addendum
fixes is actually closed. Real file: 26/26 tests pass. Commit `997a954bf`.

**Rebound to** `997a954bf09827104ee17638954aaaf746489ea4`.
## Addendum 44: Cursor Bugbot caught a real merge-resolution mistake on ADR-005's date

The ADR-005/ADR-042 conflict resolution in Addendum 37 above claimed "this
branch's values matched the files' own prose exactly, so kept" for both
records. True for ADR-042; false for ADR-005, where the committed
frontmatter actually kept origin/main's `2026-01-17` (ADR-042's own
supersession date, not ADR-005's) instead of this branch's
prose-matching `2025-12-18`. Cursor Bugbot flagged the contradiction
between the committed file and this report's own claim. Fixed by
restoring `2025-12-18`, with a correction appended to
`.agents/critique/ADR-005-status-duplication-debate-log.md` per ADR-073's
evidence requirement (commit `6471bbdd2`). Re-verified: `check_adr_lifecycle.py`
unchanged (`[PASS] 1 violation(s) across 102 ADR record(s)`), `check_adr_links.py`
0 violations, `build_all.py --check` clean (the date is not rendered in the
generated index's Retired-section row, so no regeneration needed).

**Rebound to** `6471bbdd22424244dabf0aa1e3e9b70c3ae9e8f7`.

## Addendum 45: an eleventh Copilot review round, three commits

Six findings fixed across three commits (`58f54b806`, `bec815948`,
`15fc72fda`): two stale `adr_lifecycle_baseline.json` ceilings (53, 10,
both already 0 in the live corpus since the origin/main merge) lowered
to 0; a new ratcheted `status-edge-consistency` check added to
`check_adr_lifecycle.py` (status: superseded requires a resolved
successor edge and vice versa, `deprecated` exempt), 0 violations on
the real corpus; a silent stale-allowance gap in `check_adr_links.py`
fixed (an unused baseline entry now reports as its own finding on a
full-corpus scan); two wording-accuracy fixes
(`memory-gate/SKILL.md` + its Copilot mirror, `pre_pr.py`'s comment).
Full detail in the three commits' own messages. Re-verified:
`check_adr_lifecycle.py` `[PASS] 1 violation(s) across 102 ADR
record(s)`, `check_adr_links.py` 0 violations, `build_all.py --check`
clean, `tests/test_mutation_workspace_signals.py` (8 tests) passed
clean in isolation after two contention-driven timeouts were confirmed
as flakes (both coincided with a concurrent push's own python-tests
phase running in a sibling worktree; a clean re-run with no other
push or pytest process active passed all 8).

**Rebound to** `15fc72fdab4ba7a7cf01e6712f1fcc53df6cb982`.

## Addendum 46: merged `origin/main` again, resolved 5 conflicts

`origin/main` advanced past the previous merge with PR #5283 (ADR-005/
ADR-042/ADR-028/ADR-031/ADR-056 status reconciliation, plus the new
ADR-103). Merging conflicted on 5 files, all resolved by inspection:

- `ADR-005`: date/decision-makers conflict. This branch's `2025-12-18`
  date matched the file's own prose (kept); origin's `decision-makers`
  (`[User, Orchestrator Agent, Implementer Agent]`) matched the prose
  `**Deciders**:` line exactly, more accurate than this branch's
  `[rjmurillo]` (adopted).
- `ADR-042`: date conflict. Origin's `2026-08-25` reflects a real,
  same-day frontmatter addition (`supersedes: [ADR-005]`), a
  legitimate "last updated" value distinct from the file's own
  `## Date` prose section (`2026-01-17`, the original decision date,
  unchanged); kept.
- `.claude/skills/memory-gate/SKILL.md` (+ Copilot mirror): both sides
  fixed the same bullet's citation-of-superseded-ADR-as-current-policy
  problem, origin's rewrite is the more complete fix (this branch's was
  a narrower wording correction inside the framing origin replaced
  entirely); kept origin's, regenerated the mirror via
  `build/scripts/generate_skills.py` rather than hand-editing it.
- `scripts/forgetful/README.md`: a stale `.ps1` filename in this
  branch's copy vs. origin's correct `.py` filename (verified the `.py`
  file exists, the `.ps1` does not); kept origin's.

Merge commit `63bac7e5615f1c3417e971272100e918ced03788`. Re-verified
post-merge: `check_adr_lifecycle.py` `[PASS] 1 violation(s) across 103
ADR record(s)` (including a clean `status-edge-consistency` result
against PR #5283's new reciprocal ADR-005/ADR-042 edges), `check_adr_
links.py` 0 violations across 1591 files, `taste_count_ratchet.py` `575
<= baseline 576`, `tests/validation/test_check_adr_lifecycle.py` +
`test_check_adr_links.py` + `tests/build_scripts/test_generate_adr_
index.py` (311 tests) passed.

**Rebound to** `63bac7e5615f1c3417e971272100e918ced03788`.

## Addendum 47: merged PR #5286's squash-merge, fixed the first real `stale-allowance` finding

The prior push attempt (commit `c921f9058`) failed with `GIT_PUSH_REAL_EXIT=1`
after `python-tests` ran 684.84s. Diagnosed the failure from the push log:
`tests/test_pr_autofix_late_live_state_gate.py::test_fast_exit_reports_
lease_loss_after_wait[.claude/commands/pr-autofix.md]` failed on a timing
assertion (`mutation_command="true"`, `LEASE_RENEWAL_INTERVAL_SECONDS=0.05`,
inherently race-dependent under `python-tests`' full parallel xdist load).
Confirmed no concurrent push or pytest process was running, then re-ran the
single test 5 times in isolation: 5/5 passed. Confirmed flake, not a
regression, per the CI-feedback re-run-once-to-confirm rule.

Separately, `origin/main` had advanced 1 commit past this branch's last
merge base: PR #5286 (`f3fad42a5`, accepting ADR-052 and superseding
ADR-036) squash-merged while the failed push was in flight. Fetched and
merged `origin/main` (`6a937fe99`); the merge was conflict-free (PR #5286's
files, this branch's ADR-052/ADR-036 debate-log and retrospective work were
disjoint).

Post-merge re-verification surfaced a new `check_adr_links.py` finding:
`stale-allowance` on `scripts/validation/check_adr_links_baseline.txt` line
74 (`unresolved:templates/AGENTS.md:../agents/architecture/ADR-036-...`).
This is the detector added earlier this branch (PR #5209 review response)
firing on its first real case: PR #5286 fixed `templates/AGENTS.md`'s
broken `../agents/...` link (missing the leading dot) to the correct
`../.agents/...` path, which resolved the defect the baseline entry had
been allowing. Removed the stale entry, updated the header's entry-count
comment (18, was 19; `test_baseline_header_counts_match_the_live_file`
re-measures it), regenerated `.agents/architecture/README.md`
(`generate_adr_index.py`, picking up PR #5286's status/supersession edges).

Re-verified: `check_adr_lifecycle.py` `[PASS] 1 violation(s) across 103 ADR
record(s)`; `check_adr_links.py` `0 violation(s) across 1591 tracked
markdown file(s)` (down from 1, the stale-allowance finding, before the
fix); `taste_count_ratchet.py` `575 <= baseline 576`;
`tests/validation/test_check_adr_lifecycle.py` +
`test_check_adr_links.py` + `tests/build_scripts/test_generate_adr_
index.py` (311 tests) passed. Commits: `241d1aad5` (index regen),
`99066a857` (stale-allowance fix).

**Rebound to** `99066a857d9e6dd4efe5cbaf00c12f987bdeb005`.

## Addendum 48: an eleventh Copilot review round, five commits

Pushed the round-10 rebind, then an eleventh Copilot review landed nine
findings on the pushed head: three suppressed, six inline. Six confirmed
real and fixed; one (reference-style ADR links never scanned) filed as
issue #5312 rather than built into this round, since a full-corpus
`git grep -P` for a reference definition targeting an ADR returned zero
matches, so the gap is real but not live; two were PR-description
accuracy findings this session had already corrected in the same window,
before the review's delivery reached the session (the &#34;53 records&#34;
checklist item and its companions, and the stale round-2 test/check/
violation counts, now further annotated to say those are the round-2
snapshot rather than current).

Fixed, five commits:

1. `c7a73be41`: ADR-005/024/025 frontmatter `date` corrected to reflect
   ADR-073's `# last updated` contract instead of the original decision
   or first-commit date. ADR-005 in particular: this is the *second*
   correction of the same field this campaign, after an earlier merge
   resolution reverted a correct `origin/main` value on a mistaken belief
   about which record it dated; verified against the record's own body
   (&#34;Superseded by ... (2026-01-17)&#34;) this time, not against a removed
   prose line. Appended the second-correction note to
   `ADR-005-status-duplication-debate-log.md`.
2. `dc22389f9`: ADR-055/063 frontmatter `date`, same class. Regenerated
   `.agents/architecture/README.md` for all five date changes.
   Correction notes appended to the two records' existing debate logs
   (`ADR-024-025-042-055-status-redundancy-debate-log.md`,
   `ADR-063-debate-log.md`) to satisfy `adr-review-policy`&#39;s mandatory
   debate-log-staged-alongside-ADR-changes gate.
3. `e80a79e06`: `check_adr_links.py`&#39;s empty-corpus guard (round 9) only
   rejected zero tracked markdown files of any kind; an unrelated valid
   git repository with a bare `README.md` still passed with a
   manufactured &#34;0 violation(s)&#34;. Added `_has_adr_corpus()`: at least
   one scanned file&#39;s basename must be ADR-shaped. First design attempt
   anchored the check to `.agents/architecture` (mirroring
   `check_adr_lifecycle.py`&#39;s own sentinel), which broke 3 of 101
   existing tests that rely on an `adr/`-prefixed fixture directory;
   redesigned to check the scanned-file basenames instead, matching this
   module&#39;s actual repo-wide scanning scope. 6 new tests; mutation-proven
   via a safe backup/restore cycle, not `git checkout --` (an earlier
   attempt at the mutation proof used `git checkout --` to undo the
   mutation and it wiped the entire uncommitted fix instead, since
   `checkout` restores to `HEAD`, not to a point mid-edit; redone safely
   and the fix reapplied from scratch).
4. `8db8ee417`: two file-size taste-lint suppression rationales
   (`check_adr_lifecycle.py`, `test_check_adr_lifecycle.py`) still said
   &#34;seven checks&#34;, stale since `status-edge-consistency` shipped as the
   eighth.
5. `9cb04f01d`: the session log&#39;s `sessionLogCreated.Evidence` field made
   an unqualified &#34;No hook was bypassed&#34; claim contradicting a
   correction already present later in the same file; narrowed to
   surviving commits. `tests/test_adr_063_memory_skill_decomposition.py`&#39;s
   module docstring still called ADR-063 &#34;DRAFT (Proposed)&#34; while the
   file&#39;s own assertion requires `accepted`.

Re-verified: `check_adr_lifecycle.py` `[PASS] 1 violation(s) across 103
ADR record(s)`; `check_adr_links.py` `0 violation(s) across 1591 tracked
markdown file(s)`; `taste_count_ratchet.py` `575 <= baseline 576`;
`tests/validation/test_check_adr_lifecycle.py` +
`test_check_adr_links.py` + `tests/build_scripts/test_generate_adr_
index.py` + `tests/test_adr_063_memory_skill_decomposition.py` (343
tests) passed.

**Rebound to** `9cb04f01d9b2c74423317f92b26bdd3abcd6fada`.
## Addendum 49: Cursor Bugbot found two of the round-11 fix's own test fixtures were unfixed

Pushed the round-11 rebind. `copilot-pull-request-reviewer` failed with
`Error: Prompt too big after adding PR context`, confirmed via
`mcp__github__get_job_logs` as the bot's own prompt-budget limit hit by
this PR's now-66KB+ description and 62-file diff, not a code defect;
not fixed (nothing to fix), and this same job also never completed
before PR #5286 merged successfully, so it does not gate mergeability.

Cursor Bugbot, reviewing the same push, found a real gap in round-11's
own `_has_adr_corpus` fix (commit `e80a79e06`): three
`main()`/`validate_adr_links()` tests got a companion
`adr/ADR-006-present.md` fixture so the new corpus guard would not
intercept them before reaching their real assertion, but two more were
missed:

- `test_main_returns_two_when_a_file_has_invalid_utf8_content`: exit 2
  either way (the guard's "no ADR records found" and the real
  `UnicodeDecodeError` handler both exit 2 with a `check_adr_links:`
  prefix), so the assertion silently passed without ever exercising the
  UnicodeDecodeError path.
- `test_validate_adr_links_reports_a_bool`: `False` either way, same
  shape.

Fixed both with the same companion-fixture pattern, and strengthened the
first test's assertion to require `codec can't decode` in the output
specifically, not just the shared prefix. Verified the strengthened
assertion is not vacuous: reverting only the fixture (keeping the
stronger assertion) reproduces the exact failure Cursor Bugbot
described, `AssertionError: must reach the UnicodeDecodeError handler,
not the _has_adr_corpus guard`, with the guard's own message quoted in
the failure. Mutation-proven the other direction too: neutralizing
`_has_adr_corpus` (`return True`) still passes both fixed tests, since
they now reach and correctly validate the real code path independent of
the guard.

Commit `f06b2aef9`. Re-verified:
`tests/validation/test_check_adr_links.py` 107 tests passed, `ruff
check` clean on both touched files, no em/en dashes.

**Rebound to** `f06b2aef9eb4d242eaac673857e55ba074848b10`.

## Addendum 50: merged Cursor Bugbot's own autofix of the identical finding

The push above failed: `remote tip d47763245efb ... is not present in the
local object store`. Cursor Bugbot Autofix (enabled on this repo) had
pushed `d47763245` directly to the branch while this session was still
working the finding, titled "fix(tests): add ADR corpus fixture to UTF-8
and bool return tests". Diffed it against this session's own commit
`f06b2aef9` before merging: both add the identical
`write(tmp_path, "adr/ADR-006-present.md", "# present\n")` fixture line to
both tests; this session's commit additionally strengthens the UTF-8
test's assertion to require `codec can't decode` in the output (Bugbot's
version left the original weak `"check_adr_links:" in err` assertion,
which cannot distinguish the guard's message from the real
`UnicodeDecodeError` message, the exact ambiguity this whole finding was
about). This session's version is a strict superset, so kept it rather
than discarding for Bugbot's: `git merge origin/... --no-edit` auto-merged
cleanly (git recognized the fixture-line insertions as textually
identical), no manual conflict resolution needed.

Re-verified post-merge: `check_adr_lifecycle.py` `[PASS] 1 violation(s)
across 103 ADR record(s)`; `check_adr_links.py` `0 violation(s) across
1591 tracked markdown file(s)`; `taste_count_ratchet.py` `575 <= baseline
576`; `tests/validation/test_check_adr_links.py` 107 tests passed; `ruff
check` clean.

**Rebound to** `30cb898b272a42d114822238d9293fd9757d06dc`.

## Addendum 51: an eleventh Copilot review round, 61 unresolved threads, not 9 (reconciled with a second concurrent-session round)

This addendum was written independently by this session, in parallel with the concurrent session's Addenda 49 and 50 above: both branches forked from the same commit (`d47763245`) and neither knew of the other's follow-on work until this reconciliation. Renumbered to 51 (was locally numbered 31, then 33 after an earlier round's renumbering, superseded by this stack merge's own renumbering) so it follows rather than collides with the concurrent session's own 49 and 50.

This addendum and Addenda 44 to 48 below were written independently by two concurrent sessions working the same branch across two separate divergences: the first reconciled earlier in this file (Addenda 44 to 47), the second below (Addendum 48), discovered only when this session's push was rejected a second time after the first merge's own pre-push hooks ran for over 15 minutes. Merged and reconciled both times rather than either side discarding the other's work; see "Reconciling with the concurrent session's second round" below for what the second reconciliation took.

`git rev-list HEAD ^origin/main` had advanced past `origin/main` (the stack's out-of-date banner) after Addendum 38's rebind; `origin/main` merged, then re-merged a second time as it advanced again mid-round (two commits, five conflicts). Fetching this PR's live review threads directly (`get_review_comments`, filtered `isResolved == false`) found 61 unresolved threads, not the smaller count a prior session summary had tracked before a context compaction. Investigating each against the actual current code, rather than the review text alone, found roughly a third already fixed in earlier rounds and never marked resolved on GitHub; the rest split across four independent files, each handed to a separate implementer subagent scoped to disjoint files (so no two agents could git-conflict), plus this session's own direct work on `check_adr_lifecycle.py`.

**Real defects fixed, each mutation-proven:**

- `check_adr_lifecycle.py`: `adr_lifecycle_baseline.json`'s `frontmatter-parses`/`id-matches-filename` ceilings were stale at 53/10 against a corpus that measures 0/0; tightened. `_reciprocity_findings` validated edge reciprocity and cycles but never bound either to `status`, so an `accepted` record could carry a `superseded-by` edge (or `status: superseded` carry no successor) and pass silently; two new rules close both directions, guarded so a record whose successor was already rejected by `supersession-target-exists` is not double-counted. `--write-baseline` wrote the current counts and exited 0 without comparing against the baseline at the base ref, so a branch could raise a count and launder it through the documented updater; now refuses any raise, reusing `scripts/validation/checks_common.py`'s `_resolve_default_base_ref`/`_refresh_remote_base` and mirroring `scripts/ci/count_ratchet.py`'s git-show-at-ref shape for the JSON counts mapping (bootstrap, an absent baseline path outside `--repo-root`, and no resolvable ref at all all no-op rather than hard-fail, each covered by its own test).
- `check_adr_links.py`: `LINK` only matched inline `[text](dest)`; reference-style `[text][label]` / `[text][]` / `[text]` forms were invisible to the scanner. Added a file-wide, case-folded definition table feeding the same `_target_findings`/`_resolves_to_tracked_file` pipeline inline links already use (so the CWE-22 traversal guard covers the new entry point without a second copy of the rules). The baseline file was a pure exemption list with no provenance check; now a three-direction ratchet (shape-enforced `kind:file:target` keys, base-ref provenance so a branch cannot add its own allowance, and unused-allowance rejection on a full-corpus scan). The unused-allowance check immediately caught a real stale entry (`unresolved:templates/AGENTS.md:../agents/architecture/ADR-036-...`, already repaired by an upstream commit merged into this branch); deleted, header count corrected.
- `build/scripts/generate_adr_index.py`: the Decision-summary and title extractors stripped only triple-backtick fences with a single-line regex, so a tilde fence, a 4+-backtick fence, or a heading shown inside a code sample could leak into the published title or summary. Replaced with a CommonMark-correct scanner mirroring `check_adr_links.py`'s fence tracking (full marker run, closing fence must be whitespace-only after the marker), applied once before any heading search.
- `scripts/validation/pre_pr.py`: the module docstring and a comment both overstated the facade as re-exporting "every validator"; measured 15 validators `pre_pr_sequence` imports with no re-export here. Rewritten to describe only the two ADR exports this PR added, pointing the pre-existing gap at issue #5272.
- `.claude/skills/memory-gate/SKILL.md` (+ generated Copilot mirror): the ADR-042 PowerShell exception had broadened from "quick fixes to existing PowerShell scripts and PowerShell-specific operations" (ADR-042:127-129, quoted verbatim) to "existing scripts and Windows-specific operations"; narrowed back, mirror regenerated via `build_all.py` rather than hand-edited.
- A cluster of stale-documentation threads (session-log `--no-verify` claims, QA-report carried-forward counts, debate-log citations, a broken markdown table in ADR-055, a PR/commit-number conflation in ADR-024): most were already corrected in earlier rounds; two genuinely new drifts (a citation line number that had moved, and 54/21 counts the PR #5291 backfill had since made 0/19) were fixed with re-measured evidence.

**Investigated and explicitly not changed, with reasons recorded rather than silently skipped:**

- The ratchet compares only per-check totals, not finding identities, so a branch can swap one baselined finding for a different one under the same check without tripping the gate. Real, but closing it needs a baseline schema change (per-finding identity tracking, at minimum `(check, path)` pairs) larger than a review-round fix; documented in `_report`'s docstring for a follow-up.
- `ADR-TEMPLATE.md`'s `## Status` section removal (raised as a Copilot finding on this same round) directly contradicts two other threads in the same round asking to remove exactly that kind of duplicative prose from ADR-005 and ADR-024. The template's own prose already states the ADR-073 "may" reading and why omission is not a violation; whether a generated ADR should pre-fill the section anyway is an ADR-073 interpretation question this session did not resolve unilaterally.
- The stacked session log's `endingCommit` rebind: the thread's requested target SHA is now older than the log's current value, and the post-ADR-096 `qa_report.py` no longer requires `endingCommit == qaCommit` at all. Left for the standing rebind chore rather than moved backwards.
- Two terse "Duplicative"/"Redundant" threads on ADR-005 and ADR-024 with no line number: investigated against `git diff main...HEAD` on each file; both point at content already removed in earlier rounds (prose restating frontmatter, a `## Status` section replaced by `## Provenance`). No further edit needed.

**Two self-inflicted regressions caught before push, both closed in the same round:** the reciprocity fix's two new rules pushed `_reciprocity_findings` to cyclomatic complexity 14 (max 10), caught by `taste_lints.py` and the whole-tree `taste-count-ratchet` (baseline 576, tree measured 577); split into five named helper functions, each independently low-complexity, with no behavior or assertion change (the unchanged 127-test file stayed green). A direct `from subprocess_runner import _run_subprocess` import made mypy load that file under two module names in the same run (the bare name from this import, `scripts.validation.subprocess_runner` from `checks_common.py`'s own import of it); fixed by importing `_run_subprocess` from `checks_common` instead, which already re-exports it for exactly this reason.

**Two `origin/main` merges during this round.** First: 18 files (PR #5291's ADR-073 frontmatter backfill and others), no conflicts against this branch's own ADR-tooling work. Second (`origin/main` advanced by two more commits, `cdf688a9f`/`f3fad42a5`, while this round's fixes were in flight): 5 conflicts, each resolved by reading both sides' evidence rather than picking one blindly. `ADR-005`: `date` kept from this branch (matches the debate log's documented 2025-12-18 resolution, `main`'s value was the pre-existing stale `2026-01-17`), `decision-makers` taken from `main` (that commit's own Copilot-reviewed fix, matching the pre-existing `**Deciders**` prose before it was deleted). `ADR-042`: `date` taken from `main` (that commit added real content, a Downstream provenance line, and bumped the date to match per ADR-073's "last updated" contract; this branch's value was unchanged from an earlier, already-stale state). `.claude/skills/memory-gate/SKILL.md` (+ mirror): two complementary bullets from each side kept, neither redundant. `scripts/forgetful/README.md`: `main`'s Python script path taken over this branch's PowerShell one, verified against the actual tracked file (`scripts/review_memory_export_security.py` exists; `scripts/Review-MemoryExportSecurity.ps1` does not).

**Full-suite evidence.** After the complexity/mypy fixes: `uv run pytest tests/ -q --timeout=300` → 28234 passed, 77 skipped, real exit 0 (verified from the log's captured exit line, not the backgrounded task notification, per this session's own standing distrust of that notification). `scripts/validation/pre_pr.py` full run, iterated to green across three passes as each real failure surfaced (merge-tree-ratchet needing the second main merge, the mypy dual-module-name error, the ADR-036 unused-allowance rejection): all validators pass except this file's own rebind (below). `ruff check` and the taste-count ratchet (576, at baseline) both clean on every touched file.

### Reconciling with the concurrent session's independent round-11 work

Both sessions fixed the same Copilot review round from the same starting
point and diverged on two designs. Both were kept, resolved by adopting
whichever session's approach was simpler and already tested, not by session
identity:

- **`check_adr_lifecycle.py`'s status-to-edge check.** This session extended
  `supersession-reciprocal` in place (no new check name), which needed a
  5-helper-function split to clear a complexity ceiling the extension
  pushed past. The concurrent session added a separate `status-edge-
  consistency` check (an 8th check name), a single ~25-line function with no
  complexity issue. Adopted the concurrent session's design: simpler,
  already tested, and it does not grow the same complexity problem this
  session then had to fix separately. This session's reciprocity helpers
  were reverted to their pre-split, 3-loop inline form (the form no longer
  needs splitting once the status-edge logic lives in its own function);
  the mypy `_run_subprocess` import fix and the `--write-baseline` base-ref
  ratchet, both unique to this session, are unaffected and kept. Module
  docstring, the file-size suppression's check count, and this file's own
  test-file suppression all updated from "seven" to "eight" checks.
- **`check_adr_links.py`'s stale-allowance detector.** This session raised
  a `ValueError` on an unused baseline entry (a full-corpus-scan-only hard
  failure). The concurrent session reported it as a regular `Finding` with
  kind `"stale-allowance"`, consistent with how every other defect this
  gate finds is already represented, and already had `BASELINE_KINDS`
  documentation explaining the exclusion. Adopted the concurrent session's
  design; this session's four tests asserting the `ValueError` contract
  were replaced by the concurrent session's equivalent `Finding`-based
  tests (already covering the same ground), with one kept and adjusted
  (`test_main_returns_one_on_a_stale_baseline_entry`, since a `Finding`
  contributes to the normal violation count, exit 1, not the config-error
  exit 2 the old contract used). This session's reference-style-link
  parsing, its own three-direction baseline provenance work (base-ref
  existence check, shape enforcement), and `generate_adr_index.py`'s
  fence-aware extraction have no equivalent in the concurrent session and
  are kept as this session wrote them.
- Both sessions independently fixed `memory-gate/SKILL.md`'s ADR-042
  wording and `pre_pr.py`'s facade-coverage comment, worded almost
  identically; the concurrent session's `pre_pr.py` module-docstring fix
  (this session's own comment fix builds on it, unchanged by the
  concurrent session) was kept since it is the one both sides' comment
  fixes actually depend on for context.

Re-verified after the first reconciliation: `tests/validation/test_check_adr_lifecycle.py`
(130 tests), `tests/validation/test_check_adr_links.py` (142 tests),
`ruff check` and `taste_lints.py` on every touched file, all clean. Merge
commit `de0dcc1460d21d7dff3b0a0cecaae3a4c4d840fa` (Addenda 44 to 47 above).

### Reconciling with the concurrent session's second round (Addendum 48)

The concurrent session pushed 7 more commits (Addendum 48 above) while this session's own ~17-minute pre-push hook suite was still running on the first reconciliation's merge commit, so the second push was also rejected. Merged; two items needed attention beyond a routine `git merge`:

- **ADR-005's `date` field, corrected a second time, in the other direction.** The first reconciliation (this session's earlier merge) kept this session's `2025-12-18`, reasoned from a debate log's account of "the original decision date". Addendum 48's `c7a73be41` corrects it to `2026-01-17`, evidenced directly from the record's own body text ("Superseded by ADR-042 ... (2026-01-17)") and ADR-073's actual schema contract for `date` ("last updated", not "original decision"). That evidence is stronger and more direct than the debate log's account; the first reconciliation's choice was a mistake, and the concurrent session's second pass caught and fixed it. Recorded here rather than silently accepted, since a QA report that omits its own earlier wrong call teaches the next reader the wrong lesson about how these merges were actually resolved.
- **`check_adr_links.py`'s `_has_adr_corpus` guard (from `e80a79e06`) needed combining, not choosing, with this session's `base_ref` parameter.** Both changed `validate_adr_links`'s body: the concurrent session added a corpus-shape guard before scanning: `_scannable_files`, then `_has_adr_corpus`, checked before `find_broken_adr_links` runs. This session's own reconciliation-1 work had already added a `base_ref: str = "auto"` parameter and base-ref-provenance wiring to the same function. Combined rather than picking one: the corpus guard now runs first (fails loud on a corpus-shaped-nothing repo before any base-ref work happens), then `base_allowances_for_run` computes the provenance set exactly as this session's own code already did. Four of this session's own tests broke as a direct consequence: `_repo_with_base`, the shared fixture four base-ref-provenance tests use, wrote only `adr/index.md` (not ADR-shaped), so the new corpus guard rejected all four fixtures as "no ADR records found" before the base-ref logic they exist to test ever ran. Fixed once, at the fixture (added one ADR-shaped file `adr/ADR-001-placeholder.md`), rather than four times at each call site.
- The module docstring carried a second, now-false claim from the concurrent session's own round: a paragraph asserting reference-style links "are not recognized at all" and filing issue #5312 to track it, written in the same review round this session's own `LINK_DEFINITION`/`REFERENCE_LINK`/`SHORTCUT_LINK` fix closed. Removed the false claim, replaced with one sentence noting issue #5312 is moot once this file carries the fix (which it now does).

Re-verified after this second reconciliation: `tests/validation/test_check_adr_links.py` (148 tests, up from 142: the shared fixture fix plus none removed), `tests/validation/test_check_adr_lifecycle.py` (130 tests), `tests/test_adr_063_memory_skill_decomposition.py`, `ruff check` and the whole-tree `taste-count-ratchet` (within the 576 baseline), all clean.

**Rebound to** `a8a5150c7aed038b25644b798d1abdfe7773e318`, the commit this
session had reconciled the second round to before discovering, on the next
push attempt, that the concurrent session had moved on to a third round
(Addendum 52 below covers that reconciliation).

## Addendum 52: a third concurrent-session collision, reconciled against work already covered

Fetching before this session's next push found `origin/claude/adr-evaluation-tooling-6od8rd`
had advanced four commits past `d47763245` (the commit Addendum 51's own
second reconciliation had already merged in) to `3a1c7928b`: the concurrent
session's own Addenda 49 and 50 above, both written independently of this
session and describing a fix this session had never seen. `git merge
origin/... --no-edit` found three conflicts, all in the two QA reports
(`tests/validation/test_check_adr_links.py` auto-merged cleanly, git
resolving the fixture-line insertions as textually identical to what
Addendum 50 already describes).

**Content reconciliation, not code reconciliation.** Unlike the first two
rounds, this collision carried no competing code design: the concurrent
session's Addenda 49 and 50 describe a real fix (two test fixtures missing
the `_has_adr_corpus` corpus sentinel) that both sides converged on
identically once Bugbot Autofix's own weaker version (`d47763245`) had
already landed on both branches. The only conflict was numbering: both
sessions had independently claimed "Addendum 49" for their own new
content. Resolved by keeping the concurrent session's Addenda 49 and 50 as
written (they were already pushed to origin, so already the record of
truth for readers who fetched in between) and renumbering this session's
own colliding content from 31 to 33, with a one-paragraph note at its head
explaining the renumbering rather than silently relabeling it.

**Verification.** `tests/validation/test_check_adr_links.py`: 148 tests
(unchanged from Addendum 51's own count; the concurrent session's fixture
fix was already present via the auto-merge, adding no new test count).
`tests/validation/test_check_adr_lifecycle.py`: 130 tests. `ruff check`
clean on the three touched files. No em or en dashes in the merged prose.

**Rebound to** `333582acef3f29dd074741c833a36cd887689141`, the merge commit that reconciled this third round.

## Addendum 53: ADR-042 date correction, repeating across Addenda 46 and the round-11 reconciliation in Addendum 51, was itself wrong

Addendum 46 ("ADR-042: date conflict. Origin's `2026-08-25` reflects a real, same-day frontmatter addition ... a legitimate last-updated value") and Addendum 51's own "Reconciling" section ("ADR-042: `date` taken from `main` ... bumped the date to match per ADR-073's last updated contract") both kept `2026-08-25`, reasoning from a same-day `supersedes: [ADR-005]` frontmatter addition and later a Downstream cross-reference line. Both were wrong, on the same mistake repeated twice: neither addition is a content edit to ADR-042 itself, and main already settled the correct value before either merge, in `d331cba4f` (merged via PR #5283's `cdf688a9f`, titled "fix(adr): correct ADR-042 and ADR-063 date to last-updated semantics"): ADR-042's frontmatter `date` is `2026-04-13`, matching its own `## Amendment 1` section (a real, deliberate content change, distinct from a passive cross-reference edit), per the debate log's already-deliberated table (`.agents/critique/ADR-073-phase2-backfill-debate-log.md:545`).

Caught on this stacked branch's own merge of the base branch (PR #5209) into this branch: HEAD already carried `d331cba4f`'s fix (`2026-04-13`), origin carried this addendum's repeated `2026-08-25` mistake, and checking the file's own `## Date`/`## Amendment` sections plus main's already-merged history settled it. Fixed by keeping HEAD's value; `.agents/architecture/README.md`'s ADR-042 row corrected to match. Recorded here rather than silently overwriting Addenda 46 and 51's prose, since a QA report that erases its own repeated wrong call teaches the next reader that the mistake never happened, when it happened twice.

## Addendum 54: the stack merge itself, plus `origin/main`, both complete

GitHub reported the stack (this branch on top of PR #5209) as unable to merge, citing conflicts in this file, `session-5209-adr-review-fixes-stacked.md`, `ADR-042-python-migration-strategy.md`, and `.agents/architecture/README.md`. Merging `origin/claude/adr-evaluation-tooling-6od8rd` (PR #5209, at `2d6027f05`) into this branch surfaced exactly those four; the two ADR/README conflicts and the ADR-042 date correction above are covered in Addendum 53. Merge commit `8021a3a79`.

`origin/main` had also advanced 3 commits past this branch's own last merge (to `dbe5c5dcd`, PR #5309: "ruff format is not this repo's enforced formatter"). Merged with no conflicts (`862457b56`); `build/scripts/build_all.py --check` confirmed `.agents/architecture/README.md` needed no regeneration beyond the ADR-042 row already fixed.

**Full-suite evidence.** `uv run pytest tests/ -q --timeout=300` → 28297 passed, 77 skipped, real exit 0 (verified from the log's captured exit line). `scripts/validation/pre_pr.py`: two real failures on the first run (`merge-tree-ratchet`, since `origin/main` hadn't yet been merged; "QA commit is not an ancestor of validation head" on both session logs, since the stack merge hadn't yet been committed), both closed by completing the two merges above and rebinding `qaCommit` here. Second run: all validations pass.

**Rebound to** `862457b56fbfa89292382f164e9c4d0d4d397ca6`.

## Addendum 55: round-12 Copilot findings on PR #5230, rebound again

A round-12 Copilot review on PR #5230, after the stack merge in Addendum 54, found four stale citations and one drifted QA header: `detect_adr_changes.py`'s canonical-source citation (both trees) pointed at `generate_adr_index.py:209-216`, prose rather than the quoted code block, corrected to `224-231`; `test_adr_063_memory_skill_decomposition.py` cited line numbers (`459,470`, `252-253`) that had moved when unrelated changes shifted the file, corrected to `556,574` and `267-270`; `test_check_adr_links.py`'s file-size suppression comment froze an already-stale line count, reworded; and this file's own `Validated at commit` header still named the pre-stack-merge SHA (`997a954bf`) after `qaCommit` had already been rebound to the merge commit in Addendum 54, aligned. None of these touch executable logic: all four are docstring, comment, or QA-metadata text. Session End Validation's staleness check still fires on any code-file touch regardless of whether the change is behavioral, so `qaCommit` rebinds again.

**Rebound to** `b8194bf5928557c8ca3a32154803819bf44d61f0`, the round-12 fix commit (Copilot, PR #5230 round-12 review).

## Addendum 56: Addendum 53 was itself wrong; ADR-042's date is `2026-08-25`, confirmed by direct commit inspection this time

Copilot's round-13 review re-flagged the exact value Addendum 53 had just "corrected", with a specific counter-citation: commit `cdf688a9f` adds real body content to ADR-042 dated 2026-08-25. Rather than trusting either side's prose, this addendum re-derives the answer from the actual git history, since the same value has now been reversed three times in this document (Addendum 41: `2026-01-17` to `2026-04-13`; Addenda 46/51: kept `2026-08-25`; Addendum 53: reverted to `2026-04-13`).

**Direct verification, commands and output:**

```
$ git merge-base --is-ancestor cdf688a9f HEAD && echo YES
YES
$ git show -s --format='%H %aI' cdf688a9f d331cba4f
cdf688a9f614c721f8443f12d1b5350f32913d8f 2026-08-25T08:35:32-07:00
d331cba4f9ea50a32ca362ab0eb82f69b2188bb9 2026-08-25T06:55:31+00:00
```

Converted to UTC: `cdf688a9f` landed at `2026-08-25T15:35:32Z`, roughly 8h40m *after* `d331cba4f` (`2026-08-25T06:55:31Z`, the commit Addendum 41/53 cited as authoritative). `cdf688a9f` is also already an ancestor of this branch's `HEAD`. Its diff on ADR-042 (`git show cdf688a9f -- .agents/architecture/ADR-042-python-migration-strategy.md`) is two hunks: the frontmatter `date: 2026-04-13` to `2026-08-25`, and a new `**Downstream**:` bullet under `## Related Decisions` stating ADR-031 was rejected and ADR-028 was superseded, both "2026-08-25". The bullet is still present in the current file (`grep -n Downstream .agents/architecture/ADR-042-python-migration-strategy.md` returns line 154).

**Why Addendum 53 got this wrong.** It reasoned that `d331cba4f` (mine, this session, earlier that same day) had "already settled the correct value" and that Addenda 46/51's `2026-08-25` was a repeated mistake. But `d331cba4f` came *first*; `cdf688a9f` landed nearly 9 hours later, already on `main`, already an ancestor, adding a real content change the debate log's own "content, not touch" rule (`.agents/critique/ADR-073-phase2-backfill-debate-log.md:101-125`) explicitly covers: a factual claim about another record's status, added to this record's own body. Addendum 53 verified only that `2026-04-13` matched Amendment 1 (true, as of `d331cba4f`) and never checked `git log` for anything landing after it. Addenda 46 and 51 had the reasoning right the first time.

**Fixed.** `.agents/architecture/ADR-042-python-migration-strategy.md` frontmatter restored to `date: 2026-08-25`; `.agents/architecture/README.md` regenerated (`uv run python build/scripts/build_all.py`) to match; `.agents/critique/ADR-073-phase2-backfill-debate-log.md` Batch 30 added, correcting Batch 29 with this same evidence. Not silently overwriting Batch 29 or Addendum 53's prose, for the same reason Addendum 53 gave for not overwriting Addenda 46/51: a report that erases its own repeated wrong call teaches the next reader the mistake never happened, when it happened three times now.

`check_adr_lifecycle.py` corpus check and `build/scripts/build_all.py --check` re-run clean after the fix.

## Addendum 57: commit `9912a6fdf` lands the Addendum 56 fix plus the ADR-063 fence-stripping fix, `qaCommit` rebinds again

Addendum 56 documented the investigation; commit `9912a6fdfa09a8a882f3420dd9ef37ee3398962a` is where the ADR-042 date restore, the debate log's Batch 30, and the ADR-063 title test's fence-stripping fix (a separate round-13 finding, on `tests/test_adr_063_memory_skill_decomposition.py:163`) actually landed. Session End Validation's staleness check fires again on this code/content touch; `qaCommit` and the `Validated at commit` header both rebind to it.

**Rebound to** `9912a6fdfa09a8a882f3420dd9ef37ee3398962a`.

## Addendum 58: PR #5209 merged, base retargeted to `main`, and a real silent-shadowing defect found in the merge

PR #5209 squash-merged into `main` at `2026-08-25T21:33:06Z`; GitHub deleted `claude/adr-evaluation-tooling-6od8rd` and auto-retargeted this branch's PR (#5230) to `main`. GitHub reported the resulting merge as conflicted, listing the same ten files this document has carried through many rounds.

**Why the conflict was real but not a content disagreement.** `git merge-base --is-ancestor 2d6027f05... origin/main` returns false: a squash merge creates a brand-new commit with no parent link to the squashed branch, so git's merge algorithm cannot see that this branch's history already contains everything `main` just gained. But `2d6027f05` (PR #5209's exact pre-squash tip) IS already an ancestor of this branch's `HEAD` (confirmed the same way, `--is-ancestor` true), and `git diff 2d6027f05:<path> origin/main:<path>` returned empty for all ten conflicted files plus the eleventh, `src/copilot-cli/skills/adr-review/scripts/detect_adr_changes.py`. That means `origin/main`'s content for every one of these files is byte-identical to what PR #5209's branch already had, and this branch's history already contains that exact state (from the earlier `8021a3a79` merge) plus its own later rounds of fixes on top. Resolved with `git checkout --ours` for all ten; verified by re-running the full targeted test suite (554 passed) and `check_adr_lifecycle.py`'s corpus check (clean) before committing the merge (`f7405dcae`).

**A real defect the "add/add" markers didn't catch.** `tests/test_markdown_parser.py` auto-merged with NO reported conflict, but the merge silently produced two `class TestBlankNonProseBlockLines:` definitions in the same file: this branch's later, hardened version (the exact-output discrimination probe documented earlier as "A weakened test control" fix) and PR #5209's own earlier, weaker, substring-only version. Python class redefinition means only the second definition in a module actually exists at runtime, so the merge silently reinstated the exact weakness this session had already fixed and pytest kept reporting "554 passed" while quietly exercising the shadowed weak assertions instead. Caught by `ruff`'s `F811` (redefinition of unused name), surfaced by `pre_pr.py`'s ruff-count-ratchet as a new violation (1 > baseline 0) rather than by any test failure. Fixed by deleting the second, older class definition (commit `0716eeb82`); the surviving seven tests under the one remaining class all pass, including the two hardened assertions.

`uv run python scripts/validation/pre_pr.py`: clean after the fix. This branch's diff against its new base (`main`) collapsed to 12 files, all confirmed own-contribution by the same byte-identity-to-`origin/main` test this document has used throughout; the previous "inherited from `origin/main`" category no longer applies, since `main` is now the literal base.

**Rebound to** `0716eeb827d6ff36be0ad5e25b779d7191a9a7ba`.

## Addendum 59: round-15 Copilot review, two real findings, both fixed

A Copilot review on PR #5230's round-15 head (`0674d2333`) flagged two mandatory issues, both real.

**The status-mapping table's own ADR-042 row went stale a second time.** Batch 30 of the debate log (added in the round documented at Addendum 58) established `2026-08-25` as ADR-042's correct date, overturning Batch 29's `2026-04-13`. Batch 30's own text restored the frontmatter and the generated `README.md` row to match, but never touched the debate log's own "Status mapping for all 53 records reviewed" table, whose ADR-042 row (line 545) still read `2026-04-13` even though Batch 29's prose had quoted that exact row as authoritative before Batch 30 overturned it. Fixed: the row now reads `2026-08-25`, and Batch 30 gained a closing paragraph documenting the correction, the same way Batch 29 already closed the loop for the frontmatter and README (commit `dc15a2fd3`).

**A multiline inline HTML comment could still hide a forged status.** `blank_non_prose_block_lines` (`scripts/utils/markdown_parser.py`) blanked whole-line `html_block` tokens (the block-level HTML comment gap already fixed at Addendum 58's own predecessor round) but left `html_inline` content completely untouched. Verified empirically: `_create_parser().parse("prose <!--\n**Status**: Accepted\n-->\n")` produces one `html_inline` child token spanning all three source lines, confirming that a comment opened mid-paragraph (`prose <!--`) is not a block at all, so it can legally cross source lines while the paragraph stays open, since none of the comment's own `-->` or its hidden content is one of the handful of constructs (a blank line, an ATX heading, a list marker) that interrupt a CommonMark paragraph. A `**Status**: Accepted` line inside such a comment renders invisible on GitHub or any CommonMark renderer, while `check_adr_lifecycle.py`'s `_INLINE_STATUS_RE`, run as a raw-text regex over the OLD function's output, still read it off the untouched paragraph line as the record's declared status.

Fixed by adding `_mask_inline_html_comments`, a comment-only sibling of the existing `_mask_inline_contexts` (which also masks backtick code spans for its other caller, `extract_lookup_references`, and could not be reused directly here: reusing it broke `test_decorated_prose_matching_the_enum_passes`, whose fixture, `` `Accepted`. Supersedes nothing. ``, relies on a backtick-decorated status word staying visible prose). `_mask_inline_contexts`'s `str.splitlines()`-based line indexing (which drops the trailing empty element `str.split("\n")` keeps when the input ends in a newline) had to be reconciled with `_blank_block_lines`'s `str.split("\n")`-based, line-count-preserving contract before the two passes could combine; done by restoring that trailing element before indexing by line number.

This flipped `test_keeps_inline_html_comment_on_a_prose_line`, whose premise (only a block-segmented comment needs hiding) was exactly the contract this fixes, per the mirror obligation on contract changes: renamed to `test_blanks_an_inline_html_comment_sharing_a_line_with_prose` and rewritten to assert the comment IS now masked. Added `test_hides_a_multiline_inline_html_comment_status` (the real forgery case, asserting exact transformed text across all three source lines and that `"**Status**"` no longer appears in the output), `test_blank_code_block_lines_does_not_strip_an_inline_html_comment` (control proving the sibling function `blank_code_block_lines` is untouched), and `test_still_shows_status_visible_alongside_a_multiline_comment` (control proving a real status placed after such a comment still survives, so the fix is not merely blanking every line the comment's paragraph touches).

Mutation-proven: `git stash push -- scripts/utils/markdown_parser.py` (reverting only the implementation, keeping the new tests) failed exactly the two discriminating tests (`test_blanks_an_inline_html_comment_sharing_a_line_with_prose`, `test_hides_a_multiline_inline_html_comment_status`) while the two controls and the pre-existing 8 tests in the same class stayed green; `git stash pop` restored the fix and all 10 passed again.

Full suites re-run clean after both fixes: `tests/test_markdown_parser.py` (75 passed), `tests/validation/test_check_adr_lifecycle.py` (205 combined with the parser suite), `tests/validation/test_check_adr_links.py` and `tests/skills/adr-review/` (440 combined across all four files). `check_adr_lifecycle.py`'s corpus check: unchanged, 1 violation across 103 records, at baseline. `pre_pr.py`: all validations passed on both commits.

**Rebound to** `586b1b4680f3a2a887625da28168eec6f16cab9c`.

## Addendum 60: rounds 16 and 17, the round-15 comment mask replaced twice more, each time by a real Copilot finding

Neither round got its own addendum when it landed; this one covers both, since the PASS evidence above still named `_mask_inline_html_comments`, an implementation removed two rounds ago. A round-17 Copilot review caught the staleness directly (`.agents/qa/2026-08-21-adr-corpus-campaign-qa.md:2565` at the time): "No later addendum validates or mutation-tests the implementation being merged". Real, and now fixed by this addendum.

**Round 16, finding 1 (mandatory): the round-15 substring scan confused a backtick-quoted literal for a real comment opener.** `_mask_inline_html_comments` tracked an `in_comment` state by scanning raw text for `<!--`/`-->`, with no awareness of backtick code spans. `` `<!--` `` followed by `**Status**: Proposed` is CommonMark raw text, a `code_inline` token holding the literal characters `<!--`, not a comment; verified empirically that parsing it produces exactly that token plus separate `strong_open`/text/`strong_close` tokens for the status, with no `html_inline` token at all. The scan entered "in comment" state on the backtick-quoted marker anyway and masked the real status that followed until the next `-->` anywhere in the document, a false-negative gap where a genuine `prose-frontmatter-agree` drift could go undetected. Fixed (commit `086bb47b1`) by discarding the substring scan and adding `_html_comment_inline_ranges`, which reads the parser's own `html_inline` child tokens instead: the parser has already resolved comment-vs-code-span precedence by the time tokens exist, so reading its decision sidesteps re-deriving CommonMark's precedence rules by hand. Only tokens whose content opens with `<!--` are masked, so a bare visible tag like `<b>` is left alone. Added `test_a_literal_comment_marker_inside_backticks_is_not_a_comment`. Mutation-proven: reverting to the substring scan failed exactly this test while the ten round-15 tests stayed green.

**Round 16, finding 2 (previously-missed, resurfaced): the ADR-063 title test reimplemented `build_record`'s call sequence instead of driving it.** `test_title_names_the_decomposition_decision` called `parse_frontmatter`, `_strip_fences`, and `_extract_title` individually, so a future change to `build_record` removing, reordering, or adding a step between those three calls would leave this test green, since it never ran `build_record` itself. Fixed (commit `7cddeac5d`) by calling `_index.build_record(ADR_PATH)` directly and asserting on the `AdrRecord.title` it returns.

**Round 17, finding 1 (mandatory): a decoy code span with identical text to a later real comment could steal the match.** `_html_comment_inline_ranges` located each `html_inline` child's exact character offset by searching for its content from a cursor that advanced only past PRIOR `html_inline` children. `` `<!-- x -->` <!-- x --> `` tokenizes as `code_inline("<!-- x -->")`, `text(" ")`, `html_inline("<!-- x -->")`: searching for the `html_inline` child's content from the paragraph's start, without having advanced past the `code_inline` child's identical text, found the FIRST occurrence, inside the backticks, and masked visible code while leaving the real comment (and whatever it might hide) untouched. Verified empirically, matching Copilot's report exactly. Fixed (commit `aac140090`) by advancing the cursor past EVERY child in source order, not only `html_inline` ones, so an earlier decoy of any type is consumed by its own search step before a later real comment's search begins. Added `test_a_decoy_code_span_does_not_steal_the_real_comments_match`. Mutation-proven: reverting the cursor fix alone failed exactly this test while the twelve round-15/16 tests stayed green.

**Round 17, finding 2 (real, documentation-only): `_blank_block_lines`'s docstring claimed to be the shared blanking loop for both `blank_code_block_lines` and `blank_non_prose_block_lines`, which had stopped being true once the latter grew its own inline-comment masking pass ahead of the block-blanking step and inlined that loop separately.** Fixed (commit `aac140090`, same commit as the cursor fix) by extracting the genuinely shared loop into `_blank_matching_token_lines`, called by both functions, rather than narrowing the docstring to describe a duplicated implementation. Behavior-preserving: all 77 tests in `tests/test_markdown_parser.py` passed both before and after the extraction.

**Round 17, finding 3 (this addendum): the QA evidence itself, described above.** Fixed by writing this addendum with fresh evidence for the current implementation, rather than leaving Addendum 59's description of a removed helper standing as the most recent word.

Full suites re-run clean after all four round-16/17 fixes: `tests/test_markdown_parser.py` (77 passed), combined with `tests/validation/test_check_adr_lifecycle.py`, `tests/validation/test_check_adr_links.py`, `tests/skills/adr-review/`, and `tests/test_adr_063_memory_skill_decomposition.py` (469 passed). `check_adr_lifecycle.py`'s corpus check: unchanged, 1 violation across 103 records, at baseline. `pre_pr.py`: all validations passed on every commit in this addendum.

**Rebound to** `aac1400909c75935841732f7aea597ff557ee693`.

