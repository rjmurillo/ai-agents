# Spike report: receipt checker core on ai-agents transcripts

SPIKE ONLY. Do not merge. Nothing here is wired to a hook or shipped.
Branch `spike/nocap-checker-core` is local only. It is not pushed, and no PR exists.

## Verdict

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

All numbers are from branch `spike/nocap-checker-core`, run on 2026-11-23.
The adapter was committed at `50b3045e2d` before the measured run and was not changed afterwards.

- Core: six files vendored from `jedbrnth-eng/no-cap` at `a683c857` (Apache-2.0). See `VENDORED.md`.
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
| Missed CAP | 1 | "19 pass, 2 skipped"; `gh pr checks` (under `head -n 40`, 20 rows) showed 18 pass. Routed as a test claim. |
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
  `git merge-tree` (matches its `git merge\b` pattern), `->$2` inside a quoted Python string (read as a
  redirect), `> $P` to a temp file, and two writes into scratch directories outside the tested repo.
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
5. **Repo GitHub script output is not parsed.** `merge_pr.py` returned `"state":"MERGED"`, and a PR list
   showed `7282 OPEN`. The core still found no `gh` output for the PR.

## Scope and limits

- Files outside the spike directory: `pyproject.toml` gained a ruff `per-file-ignores` entry and a
  format exclude for `vendor/**`. No hook, dispatcher, skill, or other file changed.
- Replay reads the filesystem for some subset decisions. Removed worktrees can change those.
- Upstream's post-judge artifact check (`verify.check_artifacts`) is not vendored and did not run.
- Spike tests live beside the spike, not under `tests/`, so CI does not collect them.
- Raw per-claim results stay outside the repository because they hold transcript text.
