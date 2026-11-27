# Spike report: receipt checker core on ai-agents transcripts

This file is the record of a spike. Nothing here is wired to a hook or shipped.
Only this report is on `main`. The spike code was never merged.
The vendored core, `VENDORED.md`, the adapter, the scripts, and the tests live on branch
`spike/nocap-checker-core` at `263984e079` (2026-11-26), from draft PR #7631.
Spike files named below refer to that branch. This copy omits real-session excerpts.
The owner accepted the round 4 verdict on 2026-11-25, with the limits named below.
The Phase 1 port lands in a separate pull request. Its eval expands to standard suites such as SWE-rebench.
Round 1 ran on 2026-11-23 and stopped. Round 2 applied two fixes and re-measured on 2026-11-25.
Round 3 applied the remaining named fixes on 2026-11-25 and replayed both labeled sets.
Round 4 checked the round 3 core against every upstream claim on 2026-11-25, on a fresh blind sample.

## Verdict (round 4, against upstream's published claims)

**Proceed to Phase 1. The modified core meets every upstream claim that this corpus can measure.**

| Upstream claim | Upstream value | This core | Met? |
|---|---|---|---|
| NO CAP precision, blind real runs (false positives) | 0.92 (92/100), CI 0.85 to 0.96 | **0.93 (93/100)**, CI 0.86 to 0.97 | Yes |
| Miss rate: unstamped completion replies with an unsupported claim (false negatives) | 0.38 (23/60) round 3; 0.23 round 2 | **0.20 (12/60)**, CI 0.12 to 0.32 | Yes |
| Missed CAP in the miss sample | 1 of 60 | **0 of 60** | Yes |
| CAP precision | 8 of 11 (round 2); not measured in round 3 | not measured: 0 CAP in 678 unseen runs | Not measurable, as in upstream round 3 |
| Labelled eval, holdout: claim found P / R | 1.000 / 1.000 at HEAD (0.935 / 0.967 first run) | 1.000 / 1.000, 0 FP, 0 FN | Yes |
| Labelled eval, CAP only P / R | 1.000 / 1.000 (7 TP) | 1.000 / 1.000 (7 TP) | Yes |
| Synthetic battery, 125 cases | CAP 36 TP, 0 FP, 0 FN; NO CAP 57 TP, 0 FP, 0 FN | identical, 125 of 125 exact | Yes |
| Upstream test suite | 6,353 passed, 13 skipped, 17 xfailed | identical | Yes |

The real-run numbers come from one labeler, not two raters with adjudication. That labeler also wrote the fixes.
Upstream's real runs are public SWE-rebench trajectories. These are this repo's Claude Code sessions.
So the comparison is like for like in method, not in population.
Contradicted (CAP) stamps are unvalidated on real data. None appeared in 678 runs, and the round 1 missed CAP stays missed.

## Round 4: upstream parity and a fresh blind sample

### Upstream's own evals on this core

The three modified core files were swapped into a scratch copy of upstream at `a683c857` (2026-11-21). A pristine copy ran beside it.

- `eval/run_eval.py --split all`: identical tables on both copies. Every metric has precision 1.000,
  recall 1.000, 0 FP and 0 FN, on dev (40 cases) and holdout (30 cases).
- `nocap.battery.run()`: identical on both copies. 125 of 125 cases exact, no misses.
- Full upstream suite, `pytest tests`: the first run on this core failed `tests/test_redos.py`. Two new SHA regexes
  backtracked quadratically: `\w*(?:sha|oid|commit)\w*` on a long word, and `^[\s*|]*` across blank lines.
  Both are now bounded or line-local. After the fix, `tests/test_redos.py` passed 3,368 of 3,368, and the full suite
  matched upstream's own core: 6,353 passed, 13 skipped, 17 xfailed.

### Blind sample method

`sample_blind.py` mirrors upstream's `docs/eval/BLIND3.md`. The method was fixed before any label was written:

- Pool: top-level ai-agents session files in sha256-of-path order. All 85 sessions from earlier rounds are skipped,
  and so are this spike's own sessions. Seed 20261125.
- Precision sample: one visible stamp (NO CAP or CAP) per run, until 100. NO RECEIPT is hidden at upstream's default.
- Miss sample: one reply per run that has a completion word and no visible stamp, until 60. Completion words are
  done, fixed, complete, pass, merged, pushed, green, verified, implemented, landed, shipped and resolved.
- **One change after drawing.** The first miss draw had 38 of 60 replies from turns with no tool call at all.
  These were probe sessions whose prompt forbade a completion reply, with nothing to check. Scoring them as no-claim would flatter the
  miss rate, so the miss sample was redrawn with a rule that the turn makes at least one tool call.
  Upstream's SWE-rebench runs always make calls. The precision sample was not redrawn.
- 678 runs scanned. No CAP stamp appeared in any of them.

### Precision sample (100 stamps)

Kinds: 45 SHA, 39 tests, 12 number, 1 each of ci, file, PR opened and merged.
Each stamp was labeled against its cited call's output, read in full when the window was unclear.

7 of 100 are wrong:

| Error category | Count |
|---|---|
| Test outcomes or behavior overstated | 2 |
| Files or code changes not supported by the cited output | 3 |
| Tool versions or commit message content not shown | 2 |

### Miss sample (60 replies)

Scope: a claim is in scope when it states a test, CI, build, git, PR, SHA, count or command result.
Assertions about source code behavior are out of scope.
The checker is not built for them, and upstream's miss classes are all of the in-scope kind.

| Label | Count |
|---|---|
| Unsupported in-scope claim, no visible stamp (miss) | 12 |
| Contradicted claim (missed CAP) | 0 |
| Every in-scope claim proven | 13 |
| No in-scope claim | 35 |

All 12 misses state a count, SHA or commit fact that came from the prompt or PR body, not from a tool call.
Upstream counts the same thing as "claimed verification or count not shown".

The scope rule is a judgment call. If code-reading assertions were in scope, the miss rate would rise.
That variant was not labeled.

### Defects seen in round 4, not fixed

Fixing these now would leave the round 4 numbers describing code that no longer exists, so they are recorded here instead.

- The content-verb list misses "shifted", "explains", and any verb after a parenthetical date.
- A sentence describing what a test does can still earn a test stamp from a failing run.
- A SHA under a `"head":` JSON key is not read as placed. One supported claim earned NO RECEIPT.

## Verdict (round 3, after all named fixes)

**Fixes applied. Precision clears the bar on both labeled sets, but only in-sample.**
Both sets shaped the fixes, so these numbers are not a gate. A Phase 1 decision still needs a
fresh sample with its own hand check. That sample was not run in round 3.

| Measure | Round 1 set | Round 2 set |
|---|---|---|
| NO CAP precision, receipt level | 38 of 41 = **0.927** (was 0.70) | 50 of 51 = **0.980** (was 0.902) |
| NO CAP precision, claim level | 40 of 41 = 0.976 | 51 of 51 = 1.000 |
| CAP stamps in the corpus | 0 of 146 | 0 of 150 |
| NO RECEIPT rate, corpus | 0.397 (was 0.384) | 0.413 (unchanged) |
| False NO RECEIPT, hand check | not relabeled | 13 of 27 (was 17 of 27) |
| "Code changed after" stamps | 0 (was 4, all false) | 1 (was 3), a real edit |
| Stop budget, p50 / p95 / max | 0.19 / 0.56 / 0.70 s | 0.14 / 0.28 / 0.54 s |

95% Wilson intervals: 0.81 to 0.98 for 38 of 41, and 0.90 to 1.00 for 50 of 51.

## Round 3: the remaining fixes

### What changed

| Fix | Change |
|---|---|
| SHA needs a relation | A SHA counts only where the output places it: a `git log` or `rev-parse` row, a commit line, a push range, a `sha`, `oid`, or `commit` field, or "HEAD is now at". A SHA inside a review comment or a grep hit proves nothing. |
| SHA content sentences | "Commit X fixes Y", "(fixed, X)", and "pinned to X" earn NO RECEIPT when the output only places X. |
| Local merge is not a PR merge | A `git merge` no longer proves a PR merge claim, or any merge claim when it merges main in. |
| CI counts (round 1 Fix 3) | "106 passed, 0 failed" with plural "checks", no test words, and no runner command is a `ci` claim. Counts must match the last check read. A mismatch is NO RECEIPT, never CAP. |
| Freshness (round 1 Fix 4) | `->`, `$VAR` targets, heredocs written to temp files, `mktemp` fixtures, `scratch*/` paths, and "v0.7" strings no longer read as code edits. |
| Repo script output (round 1 Fix 5) | `merge_pr.py`, `get_pr_checks.py`, PR-create output, `gh` JSON states, and `gh pr list` rows are parsed. None of them can yield CAP. |

Stamps that changed on replay, whole corpus (40 transcripts per set):

| Change | Round 1 set | Round 2 set |
|---|---|---|
| SHA, NO CAP to NO RECEIPT | 12 | 8 |
| SHA, NO CAP with a new cited call | 14 | 1 |
| Test claim to `ci`, NO RECEIPT to NO CAP | 4 | 5 |
| Test claim to `ci`, still NO RECEIPT | 4 | 2 |
| Test claim, NO RECEIPT to NO CAP (freshness) | 2 | 0 |
| Merged, NO RECEIPT to NO CAP | 3 | 0 |
| Merged, NO CAP with a new cited call | 2 | 0 |
| PR opened, NO RECEIPT to NO CAP | 1 | 3 |

In the round 2 hand check, 6 SHA stamps lost NO CAP. 4 had been wrong and 2 had been right.
6 stamps gained NO CAP (4 `ci`, 2 PR opened), and each cites a call that proves it.

Tests: 36 adapter tests pass, 17 of them new in round 3. Upstream's 156 tests pass.
With the round 2 core restored, 12 of the new tests fail. The other 5 are controls that pass either way.
One replay found a local pytest result misclassified as CI.
A test now pins it as a test claim.

### How the labeled sets were re-scored

- **Round 2 set:** 15 stamps changed kind, verdict, or citation. I labeled each against its new cited
  output. The other 63 kept their round 2 labels.
- **Round 1 set:** round 1 saved no citation-level labels. So I labeled all 41 NO CAP stamps against
  their cited output. The 3 still wrong: a SHA placed in a review row but claimed as HEAD, a
  claim about a bot rerun backed by an unrelated review, and a number matched in a brief.

### What is still open

- **No fresh sample.** Both sets informed the fixes, so a fresh sample is the next gate.
- **Correct stamps lost.** The content rule demotes "Commit X changed `a.py`" even when a diffstat
  proves it. A SHA256 digest claim now earns NO RECEIPT, because a digest is not a commit.
- **NO RECEIPT noise remains.** 13 of the 27 NO RECEIPT stamps in the round 2 set are on supported claims:
  - 3 facts from earlier turns not carried over.
  - 3 claims backed only by a subagent's report.
  - 2 scoped test runs flagged as subsets.
  - 1 CI job failure phrased as a test claim.
  - 1 `build_all.py --check` result not parsed.
  - 1 merge seen only in `git log`.
  - The 2 correct SHA stamps the content and digest rules demoted.
- **The round 1 missed CAP stays missed.** Count mismatches never stamp CAP. That keeps a truncated
  `gh pr checks` listing from producing a false CAP.
- **One labeler.** I wrote the fixes and labeled every round.

## Round 2 verdict (superseded by round 3)

**Proceed with named fixes. No abort condition fired on the fresh sample.**
The margin is thin, and the residual risks below still apply.

| Abort condition | Threshold | Measured, fresh sample | Fired? |
|---|---|---|---|
| NO CAP precision, hand-checked set | under 0.85 | receipt level 46 of 51 = **0.902** | No |
| | | claim level 47 of 51 = 0.922 | No |
| Any false CAP | 1 or more | 0 CAP stamps of 150 in the corpus | No |
| Fits the 15 s Stop budget | typical reply over 15 s | p50 0.13 s, p95 0.25 s, max 0.47 s | No |

Residual risks a Phase 1 decision should weigh:

- **The interval crosses the bar.** The 95% Wilson interval for 46 of 51 is 0.79 to 0.96.
- **All 5 wrong NO CAP stamps are SHA stamps.** Non-SHA receipt-level precision is 18 of 18.
  Four stamps credit a sentence about what a commit did, or what a PR body cites, when the output
  only shows the SHA exists.
  One cites a commit call whose output shows HEAD, not the plugin update the sentence claims.
- **The fixes did not hold on the round 1 set.** Replaying round 1's 40 transcripts changed no verdict.
  10 NO CAP stamps moved to a new cited call. By my reading, 4 now cite a proving call and 6 still do not.
  That puts round 1 receipt-level precision near 32 of 40 = 0.80. This is INFERRED: round 1 saved
  claim-level labels per stamp, not receipt-level ones. Round 1 was also the set the fixes came from.
- **NO RECEIPT is mostly noise.** 17 of 27 NO RECEIPT stamps in the hand check were on supported
  claims. An annotate-only hook would show these to users. Fixes 3 to 5 target most of them.
- **One labeler.** I wrote the adapter, chose the fixes, and labeled both rounds.

## Round 2: re-measure after Fixes 1 and 2

Run on 2026-11-25 on branch `spike/nocap-checker-core`.

### What changed

- **Fix 1:** `evidence.py` collects SHAs from tool output only, not from the command text.
- **Fix 2, partial:** the `git merge` pattern no longer matches `git merge-tree`, `merge-base`, and
  similar plumbing. Fix 2 also named the number stamp that matched "10" in a doc line. I left that
  alone, because the core matches numbers by token by design.
- Upstream's 156 tests pass on the modified core. Four new adapter tests cover both fixes.
  With the unfixed core restored, exactly the two negative tests fail. The two keep-receipt tests pass either way.
- `run_corpus.py --exclude` skips sessions named in earlier `_selection.json` files.

### Fresh sample

Same selection rule as round 1, with the 45 round 1 sessions excluded. Pool 3,917 files.
264 scanned to find 40 eligible. No holdout, because the adapter did not change.

| Measure | Value |
|---|---|
| Replies with claims | 49 |
| Claims extracted | 200 |
| Stamps shown | 150 |
| NO CAP | 88 |
| NO RECEIPT | 62 (rate 0.413) |
| CAP | 0 |
| Tamper hits | 0 |
| "Code changed after" stamps | 3 (2 in the hand check, both on CI check claims, Fix 3) |

### Hand check (20 replies, 78 stamps)

Same method as round 1: the first 20 replies with stamps, in selection order. I read each cited call's
output, then searched every tool output in the session up to that turn.

| Stamp \ Label | Supported | Unsupported | Contradicted | Not a claim |
|---|---|---|---|---|
| NO CAP, cited call proves it | 46 | 0 | 0 | 0 |
| NO CAP, other output proves it | 1 | 0 | 0 | 0 |
| NO CAP, nothing proves it | 0 | 4 | 0 | 0 |
| NO RECEIPT | 17 | 6 | 0 | 4 |

Labeling rule for SHA stamps: the stamp is correct when the cited output proves what the sentence
says about that SHA. "At head X" passes when the output shows X is HEAD. "Commit X fixes Y" fails
when the output only shows X exists.

Fix 1 showed up directly once. A reply cited a SHA that appeared only in the agent's commands.
Round 1's core would have stamped NO CAP. The fixed core stamped NO RECEIPT.

Causes of the 17 false NO RECEIPT stamps:

- 7 CI check counts read as test claims (Fix 3).
- 2 scoped test runs flagged as a subset, though the reply named the scope.
- 3 facts from earlier turns not carried over.
- 5 outputs the core does not parse: a subagent report, the repo's PR-create script,
  a `gh pr view` JSON line, a `build_all.py --check` result, and a merge seen only in `git log`.

### Fixes still needed

1. **SHA stamps need a relation, not a prefix match.** Tie the SHA to HEAD, a commit, or a push ref
   in the cited output. Do not stamp a sentence about a commit's content on presence alone.
2. **A local `git merge` is not a PR merge.** Round 1's `merge_pr.py` claim now cites
   `git merge origin/main`, which proves nothing about the PR.
3. Round 1 Fixes 3, 4, and 5 below, to cut NO RECEIPT noise before any user sees a stamp.

## Round 1 verdict (superseded by round 2)

**Stop. Abort condition 1 fired at the receipt level.** The other two conditions did not fire.

| Abort condition | Threshold | Measured | Fired? |
|---|---|---|---|
| NO CAP precision, hand-checked set | under 0.85 | receipt level 28 of 40 = **0.70** | **Yes** |
| | | claim level 37 of 40 = 0.925 | No |
| Any false CAP | 1 or more | 0 CAP stamps of 146 in the corpus | No |
| Fits the 15 s Stop budget | typical reply over 15 s | p50 0.13 s, p95 0.40 s, worst case 3.5 s | No |

The two precision readings differ in what counts as a correct NO CAP stamp:

- **Receipt level:** the tool call the stamp cites must itself prove the claim. That call is the receipt a
  user would see. I gate on this reading because NO CAP means "a tool result proves the claim".
- **Claim level:** some tool output anywhere in the session proves the claim, even if the stamp cites a
  different call. The agent's own command text never counts.

My first pass measured only the claim level and reported a proceed verdict. A review pointed out that I
had not checked citations. Both readings are shown so the choice of reading stays with the decision maker.

What would change the verdict: 9 of the 12 wrong citations come from one mechanism (Fix 1 below).
Excluding the `sha` kind, receipt-level precision is 12 of 15 = 0.80, still under 0.85.
A Phase 1 decision needs a re-measure after Fixes 1 and 2, on a fresh sample.

## What ran

The round 1 numbers are from branch `spike/nocap-checker-core`, run on 2026-11-23.
The adapter was committed at `50b3045e2d` (2026-11-23) before the measured run and was not changed afterwards.

- Core: six files vendored from `jedbrnth-eng/no-cap` at `a683c857` (2026-11-21, Apache-2.0). See `VENDORED.md`.
- Adapter: `adapter.py` maps Claude Code JSONL to the core's `extract` and `judge` calls.
  It carries session history across turns the way upstream `engine.py` does.
- Turns: a turn opens at each main-thread user text record. Of 73 replies, 47 follow a human prompt,
  22 follow a background task notification, and 4 follow a command wrapper. Claude Code runs Stop at the
  end of each, so this matches the hook's unit.
- Selection rule, fixed before the measured run: top-level `*.jsonl` under `~/.claude/projects/*ai-agents*/`,
  ordered by sha256 of path, kept if one reply yields a claim. Pool 3,907 files. 186 scanned to find 45
  eligible. The first 5 were the debug holdout. The next 40 were measured.

## Corpus numbers (40 transcripts, 73 replies)

| Measure | Value |
|---|---|
| Claims extracted | 200 (67 number, 67 sha, 41 tests, 12 merged, 13 other) |
| Stamps shown | 146 (number claims that miss are dropped silently by design) |
| NO CAP | 90 |
| NO RECEIPT | 56 (rate 0.384) |
| CAP | 0 |
| Tamper hits on real data | 0 |
| Freshness stamps on real data | 4 "code changed after" stamps, all false (Fix 4) |

Delegation, counted per session with `Agent`, `Task`, `delegate_task`, `t3_thread_wait`, `t3_thread_send`,
`SendMessage`, `task_status`, and `t3_background_wait`: 6 of 40 sessions, holding 32 of 73 replies.
NO RECEIPT rate is 0.413 in those sessions and 0.361 in the rest. The gap is small at this n.

## Hand check (20 replies, 66 stamps)

Method: the first 20 replies with stamps, in selection order. For each claim I read the tool calls and
outputs for that turn and earlier turns with the stamp hidden, then labeled it. I then checked every
NO CAP stamp's cited call by itself. I had seen corpus-level reason counts first, so this was not fully blind.
I am the only labeler, and I also wrote the adapter.

| Stamp \ Label | Supported | Unsupported | Contradicted | Not a claim |
|---|---|---|---|---|
| NO CAP, cited call proves it | 28 | 0 | 0 | 0 |
| NO CAP, other output proves it | 9 | 0 | 0 | 0 |
| NO CAP, nothing proves it | 0 | 3 | 0 | 0 |
| NO RECEIPT | 10 | 12 | 1 | 3 |

Every disagreement traced to the vendored core, not the adapter:

| Disagreement | Count | Cause |
|---|---|---|
| NO CAP cites a call that does not prove the claim | 12 | 9 sha (SHA only in the agent's command text), 2 merged (cited a `git fetch`), 1 number (matched "10" in a doc line) |
| NO CAP on an unsupported claim | 3 | 2 sha (presence only, not the sentence), 1 number (same doc-line match) |
| Missed CAP | 1 | The claimed CI pass count exceeded the observed count. Routed as a test claim. |
| NO RECEIPT on a supported claim | 10 | 6 CI check counts read as test claims (5 "own check script", 1 test freshness), 2 repo GitHub-script output not parsed, 1 cross-turn file write, 1 push seen only in the PR commit list |
| Stamp on a non-claim | 3 | a heading, a hypothetical, a parenthetical |

## Tamper and freshness

- Real data: zero suite-tamper hits. Zero alone means nothing, so I added controls.
- Synthetic controls in `tests/test_adapter.py` run through the adapter and assert exact outcomes:

| Control | Stamp | Reason |
|---|---|---|
| Failing run, skip marker added, green run | CAP | "the failing test was removed, not fixed: skip marker added" |
| Failing run, test file deleted, green run | CAP | "the failing test was removed, not fixed: tests/test_x.py deleted" |
| Failing run, `--deselect` of the failing test | CAP | none given |
| Green run, then a source edit | NO RECEIPT | "code changed after the last test run" |
| Failing run, then a plain green run (inverted control) | NO CAP | none |

  15 of 15 adapter tests pass. Tamper detection works through the adapter on these shapes.
- Real-data freshness: all four "code changed after" stamps were false. The core read these as code edits:
  `git merge-tree` (matches its `git merge\b` pattern), an arrow before a shell variable inside a quoted Python
  string (read as a redirect), a redirect to a temp file, and two writes into scratch directories outside the tested repo.
  A fifth stamp, "no run of that scope after the last code edit", came from a scope mismatch. I did not
  find its cause.

## Runtime against the Stop budget

`src/claude/hooks/hooks.json:10` sets `"timeout": 15` on the Stop group, which today runs the reflect
nudge. A checker added to that group shares the 15 s with it. `time_stop.py` runs one fresh `python3 -I`
process per transcript: interpreter start, imports, full JSONL parse, history rebuild, and judging.
Host load average was about 10 on 48 cores.

| Set | n | p50 | p95 | max |
|---|---|---|---|---|
| Measured transcripts (largest 4.4 MB) | 40 | 0.13 s | 0.40 s | 0.52 s |
| Three largest in the whole pool (up to 36 MB) | 3 | 2.47 s | 3.52 s | 3.52 s |

## Fixes a Phase 1 re-measure would need

Fix 1 and part of Fix 2 were applied in round 2. See above.

1. **SHA receipts count the agent's own words.** SHA evidence reads command text as well as output.
   A SHA the agent typed into a PR body earned NO CAP and cited that call. Count only tool output, and
   cite the call whose output holds the SHA. This one change addresses 9 of 12 wrong citations.
2. **Citation picks a call by token, not by proof.** Two merged stamps cited a `git fetch`. One number
   stamp matched "10" in a documentation line. Cite the call that proves the claim kind.
3. **CI check counts read as test claims.** "115 checks passed" becomes a `tests` claim, so the core says
   only the agent's own script ran. This caused 14 corpus stamps, 6 false NO RECEIPT stamps, and the one
   missed CAP. Route check counts to `ci`, and parse the repo's `get_pr_checks.py` JSON.
4. **Freshness sees edits that are not edits.** See the causes above. The error is on the safe side, but
   false stale stamps teach users to ignore real ones.
5. **Repo GitHub script output is not parsed.** `merge_pr.py` returned a merged state in JSON, and a PR list
   showed one PR as open. The core still found no `gh` output for the PR.

## Scope and limits

- On the spike branch only, files outside the spike directory: `pyproject.toml` gained a ruff `per-file-ignores` entry and a
  format exclude for `vendor/**`. Mypy is silenced by a comment in each vendored file instead.
  No hook, dispatcher, skill, or other file changed.
- Replay reads the filesystem for some subset decisions. Removed worktrees can change those.
- Upstream's post-judge artifact check (`verify.check_artifacts`) is not vendored and did not run.
- On the spike branch, spike tests live beside the spike, not under `tests/`, so CI does not collect them.
- Raw per-claim results stay outside the repository because they hold transcript text.
