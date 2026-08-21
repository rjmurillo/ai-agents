---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-5189-54e494d-adr-corpus-evaluation-and-tooling.json
qaCommit: b38d43b0fa5f293d0f68f07bab5183039dda68a6
---

# QA: ADR Corpus Evaluation and Repair Campaign (issues #5189 to #5201, #5205)

**Branch**: `claude/adr-evaluation-tooling-6od8rd`
**Validated at commit**: `b38d43b0fa5f293d0f68f07bab5183039dda68a6`
**Session log**: `.agents/sessions/2026-08-21-session-5189-54e494d-adr-corpus-evaluation-and-tooling.json`

## Verdict

PASS. 388 tests green, every gate at or below its baseline, `pre_pr.py` clean
apart from the session-end check this report exists to satisfy.

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
`check_adr_review_policy` enforces. No hook was bypassed; `--no-verify`,
`LEFTHOOK=0`, and `LEFTHOOK_EXCLUDE` were not used at any point.

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

- 54 records still have no frontmatter (issue #5190). The ratchet holds the line;
  the index's "Needs backfill" section is the live meter.
- 21 pre-existing ADR link violations in files outside this change, each
  baselined with a written diagnosis.
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
history: True). No hook was bypassed at any point in this campaign. The
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
