# Stalled-investigation strategy comparison

Issue #7350, a narrower successor to #6814 under #5422 and #5768. Two tasks, two
arms, three repetitions each, 12 cells, run on 2026-11-15 by `scripts/eval/eval_handoff_strategy.py`.

## Result

**INCONCLUSIVE under the frozen rule. Retain the incumbent routing.**

Every cell passed in both arms, with no regression, no scope violation, and no
repair turn. The preregistered rule says fewer than 2 stalled tasks cannot
support a routing change, and this run had 1 (`PROTOCOL.md`, rule 4). The
hypothesis is not accepted and not rejected. A routing change is not supported.

The deeper finding is that the stall never happened. In all 12 cells the first
producer attempt passed the visible reproduction and the held-out check. The comparison therefore exercised only the
investigator step before the first attempt, not the handoff after repeated failure
that the issue asks about. Nothing here measures that case.

## Results table

| Arm | Accepted (95% Wilson) | Regressions | Repair turns | Time, all cells | Model cost, all cells | Scope violations |
|---|---|---|---|---|---|---|
| continue analyst | 6 of 6 (0.61 to 1.00) | 0 | 0 | 657 s | $1.0177 | 0 |
| handoff to independent-thinker | 6 of 6 (0.61 to 1.00) | 0 | 0 | 559 s | $0.9698 | 0 |

Time is the sum of launch wall seconds. It ran through the operator's API hub, so
it is not comparable to any run made under a login, and 12 cells cannot separate
two arms on speed. Cost is the stream's `total_cost_usd`.

By task:

| Task | Arm | Accepted | Regressions | Repair turns | Time | Model cost |
|---|---|---|---|---|---|---|
| #7328, stalled task | continue analyst | 3 of 3 | 0 | 0 | 313 s | $0.4770 |
| #7328, stalled task | handoff to independent-thinker | 3 of 3 | 0 | 0 | 317 s | $0.4480 |
| #6169, negative control | continue analyst | 3 of 3 | 0 | 0 | 344 s | $0.5407 |
| #6169, negative control | handoff to independent-thinker | 3 of 3 | 0 | 0 | 242 s | $0.5218 |

Decision output from `--combine` over both batches: outcome `INCONCLUSIVE`,
routing `retain incumbent`, reason "1 stalled task(s); the rule needs at least 2". The negative control
passed: the treatment arm accepted 3 of 3
cells, matched the control arm, and had no scope violation. The handoff did not trigger needless
reframing that cost an accepted result.

## Per-run evidence

Columns: base reproduction exit (nonzero means red), reproduction exit after the
cell, held-out exit, scope violations, repair turns, transient retries, cost, wall
seconds, investigator Bash commands / other tool inputs, producer test runs, and
withheld-marker hits. Human correction minutes and blocking findings are UNKNOWN
(`null` in every cell). Token counts were not recorded.

| Task | Arm | Rep | Batch | Base | Repro | Held-out | Scope | Repairs | Retries | Cost | Wall s | Investigator Bash / other | Producer tests | Hits | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 6169 | continue | 0 | v3 | 1 | 0 | 0 | 0 | 0 | 0 | $0.1643 | 86 | 0 / 3 | 1 | 0 | PASS |
| 6169 | handoff | 0 | v3 | 1 | 0 | 0 | 0 | 0 | 0 | $0.1628 | 72 | 0 / 3 | 1 | 0 | PASS |
| 6169 | continue | 1 | v4-fill | 1 | 0 | 0 | 0 | 0 | 0 | $0.1788 | 138 | 0 / 5 | 2 | 0 | PASS |
| 6169 | handoff | 1 | v4-fill | 1 | 0 | 0 | 0 | 0 | 0 | $0.1916 | 85 | 0 / 3 | 1 | 0 | PASS |
| 6169 | continue | 2 | v4-fill | 1 | 0 | 0 | 0 | 0 | 0 | $0.1975 | 120 | 2 / 3 | 3 | 0 | PASS |
| 6169 | handoff | 2 | v4-fill | 1 | 0 | 0 | 0 | 0 | 0 | $0.1674 | 85 | 0 / 3 | 1 | 0 | PASS |
| 7328 | continue | 0 | v3 | 1 | 0 | 0 | 0 | 0 | 0 | $0.2066 | 114 | 0 / 9 | 2 | 0 | PASS |
| 7328 | handoff | 0 | v3 | 1 | 0 | 0 | 0 | 0 | 0 | $0.1299 | 106 | 3 / 0 | 1 | 0 | PASS |
| 7328 | continue | 1 | v3 | 1 | 0 | 0 | 0 | 0 | 0 | $0.1411 | 102 | 0 / 8 | 1 | 0 | PASS |
| 7328 | handoff | 1 | v3 | 1 | 0 | 0 | 0 | 0 | 0 | $0.1589 | 88 | 0 / 10 | 1 | 0 | PASS |
| 7328 | continue | 2 | v3 | 1 | 0 | 0 | 0 | 0 | 0 | $0.1293 | 97 | 0 / 5 | 1 | 0 | PASS |
| 7328 | handoff | 2 | v3 | 1 | 0 | 0 | 0 | 0 | 0 | $0.1593 | 122 | 0 / 8 | 1 | 0 | PASS |

## What the investigators did

- In the #7328 repeat-0 replies, which I read, both arms named the same root cause:
  callers such as the CI mypy ratchet and the pre-push job pass links straight to
  `run_mypy`, which still refuses them. The issue's own suggested fix (change only
  the file-set builder) was already in the tree, and both arms read past it. I did
  not read the other 10 investigator replies in full.
- The role text changed the reply. The word "premise" appears in 3 of 3 handoff
  replies for #7328 and in 0 of 3 continue replies (a word count, not a read of each
  reply). That did not change the outcome.
- Investigators ran Bash in 2 of 12 cells (the other 10 read files only), so
  neither arm reproduced the failure itself before reporting. The producer ran the
  reproduction in every cell.
- The analyst role file declares no shell and GitHub MCP reads. The harness gave both
  investigators the same tools and no MCP servers. The 6 analyst replies run 2,542 to
  3,147 characters, so none is a short refusal. The one I read, #7328 repeat 0, named
  a root cause and did not stop for a missing GitHub tool.

## How the run reached 12 cells

The result rests on four batches. Three produced no usable cells, and each is
published.

| Batch | Protocol | Outcome | Why it is not the result |
|---|---|---|---|
| `runs/2026-11-15-v1-rate-limited/` | `PROTOCOL.md` | 0 cells, $0.00 | A provider `rate_limit_error` on the first launch read as an unmeasured cost, and the spend guard skipped the other 11 cells. Fixed in v2 |
| v2 (no directory) | `PROTOCOL-v2.md` | 0 cells, stopped at 20 minutes | The subscription login stayed rate limited while retry waits cycled. I stopped it. It left no files |
| `runs/2026-11-15-v3/` | `PROTOCOL-v3.md` | 8 of 12 cells, $1.4452 | Four #6169 cells exhausted the retry ladder in a provider rate-limited window |
| `runs/2026-11-15-v4-fill/` | `PROTOCOL-v4.md` | the 4 missing cells, $0.7354 | Part of the result. v3 and v4-fill are combined in `runs/2026-11-15-combined/decision.json` |

The decision rule, the task set, and the repetitions never changed. Each protocol
file was pushed before its launch. v2, v3, and v4 each change one thing, and each
states what was seen before it was written. I read the 8 v3 outcomes before writing
`PROTOCOL-v4.md`; the cells it fills are named by loss reason alone, and no
completed cell was rerun.

Total recorded spend is $2.1806. The cells sum to $1.9875. The other
$0.1931 is spend recorded for the four lost v3 cells (INFERRED
from the batch arithmetic, not read per cell).

## Discrimination proof, before any candidate result

`--dry-run` on the frozen task file passed before the first live launch. For both
tasks the base reproduction exits 1, the shipped fix passes the held-out check
(4 and 53 tests), and the plausible-wrong fix passes the reproduction and fails the
held-out check (2 failed and 1 failed). The nodes are named in `PROTOCOL.md`.

## Provenance

| Field | Value |
|---|---|
| Task file SHA-256 | `bad0f411a3a6681037942b45c760fab949dffa3a3ee50d2a35cfde0cce8ab315` |
| #7328 base, shipped fix | `329d3b5d452345bc8445fe6a18b939e434769873`, `3cf312bc14baa9757634b77e0c1c0c95334b34d1` (PR #7333) |
| #6169 base, shipped fix | `316171ac67064874afe9965547cf5aac89f1ffc9`, `045750319851fe56aa2000da9cadd61b8a983f91` (PR #6343) |
| Runner commits | v3 `a427b61bda937e9fe831270438e8a65fdc00234d`, v4-fill `6172456f36b92c0ae9d59d8ec451606f91947b3f` |
| Role text SHA-256 | analyst `d145186398d5aeb47f02c94973d1684edaf04cf070293e1f96d5532610ccda35`, independent-thinker `0e57fd05d49f1fabd10b57ca3d49613d26db85b6aa7f27799b4bbf56f3cfd40e` |
| Model, effort, harness | `claude-sonnet-5-5` (resolved name checked on every launch), `--effort medium`, Claude Code 2.1.325, `--real-home` |
| Auth | the operator's API hub through `ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY`, names only. Values appear in no file |
| Verifier | the fix commit's own test file with one import edit and two deselected nodes (#7328), one deselected node (#6169) |

Both `report.json` files record `runner_tree_dirty: true`. That flag is an artifact.
The runner computed it after each batch, when the batch's own records and patch files
were untracked. The tree was at the pushed commit when each batch launched: I made no
edit between the push and the launch (INFERRED from my command history, not recorded
by the harness). The runner now takes the state before the first launch, with a test
that fails if the call moves. These two reports keep the old value.

## Limits

- One stalled task and one control. The rule needs 2 stalled tasks, and 12 cells
  cannot support a repository-wide claim.
- The stall did not occur, so repair turns are 0 by outcome, not by design. The case
  the issue asks about, a repeated repair failure, is untested.
- I wrote both reproductions after reading the fix. The dry run shows they do not
  encode the held-out nodes, but an author who knows the fix can steer a test.
- The observed output in the facts block carries a runner timing line that differs
  per cell, so the bytes are identical across arms except that number.
- Both investigators got tools the analyst role does not declare. The role text and
  the framing instruction changed together, so this run cannot say which one moved
  the replies.
- One model, one date, one hub. Hub routing may differ from the first-party endpoint.
- The #5425 corpus was not used: its scenarios are synthetic or adapted from another repository.

## Recommended routing delta

Retain incumbent. No change to `orchestrator.shared.md`, an agent definition, or a
routing template is supported. A future run needs at least 2 real tasks where a
first attempt fails the visible reproduction before it can test the handoff.

## Reproduce

```bash
git fetch origin main   # the base and fix commits must be present
uv run python scripts/eval/eval_handoff_strategy.py --dry-run \
  --workspace-root "$(mktemp -d)" --output-dir /tmp/handoff-dry
# live commands are in PROTOCOL-v3.md and PROTOCOL-v4.md
```
