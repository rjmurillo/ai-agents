# Spike report: receipt checker core on ai-agents transcripts

SPIKE ONLY. Do not merge. Nothing here is wired to a hook or shipped.

## Verdict

**Proceed to Phase 1 with four named fixes.** No abort condition fired.

| Abort condition | Threshold | Measured | Fired? |
|---|---|---|---|
| NO CAP precision, hand-checked set | under 0.85 | 38 of 40 = 0.95 (Wilson 95%: 0.835 to 0.986) | No |
| Any false CAP | 1 or more | 0 CAP stamps of 146 in the corpus | No |
| Fits the 15 s Stop budget | typical reply over 15 s | p50 0.13 s, p95 0.40 s, worst case 3.5 s | No |

Two caveats bound this verdict:

- The precision interval's lower bound (0.835) sits just under 0.85. The point estimate passes; n=40 cannot rule out 0.84.
- Zero false CAP is weak evidence, because the corpus produced zero CAP stamps at all.
  The one real contradiction in the hand-checked set was missed, not stamped CAP.
  The CAP path is proven only by synthetic tests here.

## What ran

All numbers below are from adapter commit `50b3045e2d`, run on 2026-11-23.

- Core: six files vendored from `jedbrnth-eng/no-cap` at `a683c857` (Apache-2.0). See `VENDORED.md`.
- Adapter: `adapter.py` maps Claude Code JSONL to the core's `extract` and `judge` calls.
  It carries session history across turns the way upstream `engine.py` does.
- Selection rule (fixed before the measured run): top-level `*.jsonl` under
  `~/.claude/projects/*ai-agents*/`, ordered by sha256 of path, kept if one reply yields a claim.
  Pool 3,907 files. 186 scanned to find 45 eligible. First 5 were the debug holdout. Next 40 were measured.
- The adapter was committed before the measured run. The run was not repeated after any adapter change.

## Corpus numbers (40 transcripts, 73 replies)

| Measure | Value |
|---|---|
| Claims extracted | 200 (67 number, 67 sha, 41 tests, 12 merged, 13 other) |
| Stamps shown | 146 (number claims that miss are dropped silently by design) |
| NO CAP | 90 |
| NO RECEIPT | 56 (rate 0.384) |
| CAP | 0 |
| Tamper hits on real data | 0 |
| Freshness stamps on real data | 5, all false (see Fix 2) |

NO RECEIPT by delegation: direct turns 55 of 144 stamps, delegated turns 1 of 2.
Only 4 of 73 replies came from a turn that called `Agent` or `delegate_task`.
Delegation does not explain the NO RECEIPT rate in this sample.

## Hand check (20 replies, 66 stamps)

Method: the first 20 replies with stamps, in selection order. For each claim I read the raw tool
calls and outputs for that turn and earlier turns, with the stamp hidden, and labeled it
supported, unsupported, contradicted, or not a claim. Then I joined labels to stamps.
I had seen the corpus-level reason counts before labeling, so this was not fully blind.

| Stamp \ Label | Supported | Unsupported | Contradicted | Not a claim |
|---|---|---|---|---|
| NO CAP | 38 | 2 | 0 | 0 |
| NO RECEIPT | 10 | 12 | 1 | 3 |

- NO CAP precision: 38 of 40. Excluding sha and number kinds: 9 of 9.
- The two wrong NO CAP stamps are both `sha` kind (see Fix 3).
- Missed CAP: one reply said "19 pass, 2 skipped". The `gh` check list it read shows 18 pass, 2 skipping.
  The checker stamped NO RECEIPT.
- False NO RECEIPT on supported claims: 10 of 48 supported claims (0.21).

## Tamper and freshness

- Real data: zero suite-tamper hits. Without a positive control, zero means nothing.
- Synthetic positive controls in `tests/test_adapter.py`, run through the adapter, all withhold NO CAP:
  a green run followed by a source edit, a skip marker added before the green run,
  and a `--deselect` of the failing test. 13 of 13 adapter tests pass.
- Real-data freshness stamps were all false. The core treated read-only commands as code edits.

## Runtime against the Stop budget

The Stop group timeout is `"timeout": 15` at `src/claude/hooks/hooks.json:10`.
`time_stop.py` runs one fresh `python3 -I` process per transcript: interpreter start, imports,
full JSONL parse, history rebuild, and judging. Host load average was about 10 on 48 cores.

| Set | n | p50 | p95 | max |
|---|---|---|---|---|
| Measured transcripts (largest 4.4 MB) | 40 | 0.13 s | 0.40 s | 0.52 s |
| Three largest in the whole pool (up to 36 MB) | 3 | 2.47 s | 3.52 s | 3.52 s |

The checker re-judges every turn to rebuild history. A Phase 1 hook can cache history and judge only the last reply.

## Named fixes for Phase 1

1. **CI check counts read as test claims.** "115 checks passed" becomes a `tests` claim.
   The core then says only the agent's own check script ran. This caused 14 corpus stamps and
   6 of the 10 false NO RECEIPT stamps in the hand check. Route check-count sentences to `ci`,
   and teach evidence the repo's `get_pr_checks.py` JSON (`PassedCount`, `FailedCount`).
2. **Freshness sees edits that are not edits.** In `evidence.extract`, `git merge\b` matches
   `git merge-base`. Redirects to shell variables (`> $P`) count as code paths. A read-only Python
   one-liner matches the write pattern. All five real freshness stamps came from these.
   The error is on the safe side, but it would teach users to ignore freshness stamps.
3. **SHA receipts count the agent's own words.** SHA evidence reads command text as well as output.
   A SHA the agent typed into a PR body it was writing earned NO CAP. A SHA receipt also proves only
   that the hash appeared, not the sentence around it ("Bugbot re-ran on X").
   Count only tool output, and label SHA stamps as presence checks.
4. **Repo GitHub skill output is not recognized.** `merge_pr.py` reported `"state":"MERGED"`, and a
   PR list showed `7282 OPEN`. The core still said no `gh` output showed the PR. Merged, pushed, and
   PR-opened claims backed by the repo's own scripts fall to NO RECEIPT. Add parsers for those shapes.

Also seen: 3 of 66 hand-checked stamps came from sentences that are not claims
(a heading, a hypothetical "any PR opened before it merges"). All three got NO RECEIPT.

## Limits of this spike

- One labeler, who also built the adapter. Not a second-model or human-independent check.
- Replay reads the filesystem for some subset decisions. Removed worktrees can change those.
- Upstream's post-judge artifact check (`verify.check_artifacts`) is not vendored and did not run.
- Spike tests live beside the spike, not under `tests/`, so CI does not collect them.
  Phase 1 tests belong under `tests/`.
- Raw per-claim results stay outside the repository because they hold transcript text.
