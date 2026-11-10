---
type: metrics
id: release-report-v0.7.0
title: Release report for v0.7.0, control-plane subtraction
epic: EPIC-5456
created: 2026-11-10
status: measured
---

# Release report, v0.7.0

Epic #5456 asked v0.7.0 to prove that `ai-agents` can do less internally and deliver at
least as much externally. This report states what the evidence shows. Two gates are not
met. The epic closes anyway, by owner decision D14 on 2026-11-10 (measure first, then
close). The ledger is `control-plane-dispositions-v0.7.0.md`. The pinned baseline is
`control-plane-baseline-v0.7.0.json` at `53ffe92c2`, and it is unchanged.

## Verdict

The control plane did not get smaller by the epic's own count. Canonical owners rose from
412 to 455 at `5934169149`. Always-loaded instruction tokens fell on every harness. The
smaller configuration matched the full one on 70 runs per arm. Local pre-push latency
has a higher p95 than the one recorded reference, and the cause is not isolated.

Abort-if clause 1 tripped: canonical owners grew during the subtraction release.

## Final gate table

All counts are anchored to a commit. "Redefined" means gate 1 excluding the whole skills
category from both sides, per owner decision D11 on 2026-11-06 (PR #7123, merge `548d2309da`).

| # | Gate | Final state | Numbers and SHAs |
|---|---|---|---|
| 1 | Canonical owners decrease | **Not met** | Original definition: 455 against 412 at `5934169149` (2026-11-10); 455 at `3e9f30aaa1` (2026-11-06). Redefined: 333 against 301 at `5934169149`; 334 against 301 at `3e9f30aaa1`. Abort-if clause 1 tripped. |
| 2 | Always-loaded tokens decrease per harness | Met | At `5934169149`: Claude Code 16,879 to 10,656; Copilot 17,281 to 11,148; Codex 965 to 760. |
| 3 | Local-gate p95 does not regress | **Not met**, literal comparison | Pre-push p95 201.73s (n=20, `5fbdfd238b`) against a recorded worst-observed 124.11s for the python class (n=2, `1251644dd`); 128.21s is the worst across classes (hooks). Detail below. |
| 4 | Nothing lands without removing something | Met as recorded, with a flag | Recorded Met on two named exceptions, `control_plane_baseline.py` and `gate_latency.py` (D32, 2026-10-04). Flag below. |
| 5 | Reduced configuration compared on identical tasks | Data on both harnesses; controls tie | 2026-11-06: Claude 15 of 15 against 15 of 15, Codex 4 of 6 against 4 of 6 (PR #7122, `badc5ffb24`). 2026-11-10: 70 of 70 against 69 of 70 (below). |
| 6 | Smaller configuration non-inferior | **Shown** on this corpus | Pre-registered rule; difference -0.0143, 95 percent interval -0.0766 to +0.0390 against a -0.10 margin (below). |
| 7 | Correction time, cost, wall time per accepted task | Cost and wall time only | Owner dropped the human correction clause on #5768. New batch: USD 0.165 `full`, 0.078 `reduced` per accepted deterministic task, list price. |
| 8 | Deleted mechanisms take their exclusive parts | Met per ledger | Evidenced per row in the ledger; no dead shell recorded except one documented `.diffray/**` ignore line. |
| 9 | Every KEEP has a justification | Checked | Six KEEP rows with the five required fields, plus six validators ruled KEEP on 2026-09-28. |
| 10 | Release report separates deletion, relocation, generation, archival | Met by this file | Sections below. |

## Gate 1: why it is not met

| Owner class | Pinned `53ffe92c2` | `5934169149` | Change |
|---|---|---|---|
| Agents | 31 | 29 | -2 |
| Skills | 111 | 122 | +11 |
| Rules | 30 | 29 | -1 |
| Hook registrations | 7 | 8 | +1 |
| Validators | 99 | 124 | +25 |
| Workflows | 58 | 62 | +4 |
| Lefthook jobs | 76 | 81 | +5 |
| Total, original | 412 | 455 | +43 |
| Total, excluding skills | 301 | 333 | +32 |

Validators account for +25 of the growth. The baseline script counts files, so a generated
symlink counts as an owner. At `5934169149`, 105 of 122 skill entries and 29 of 29 agent
entries are symlinks. The pinned tree had none. The owner rejected the symlink-only reading
on 2026-11-06 because it is not like for like.

## Gate 3: what was measured

Measured 2026-11-10 with `scripts/metrics/gate_latency.py`, n=20 per capture, nearest-rank
p95, on a 48-CPU host shared with other agent sessions. Records are in
`gate-latency-2026-11-10/`.

| Capture | SHA | p50 | p95 | min | max | Recorded reference (worst observed) |
|---|---|---|---|---|---|---|
| pre-push, python class | `5fbdfd238b` | 106.15s | 201.73s | 100.93s | 245.58s | 124.11s python class (`1251644dd`, n=2); 128.21s worst across classes (hooks) |
| pre-commit, python class | `5fbdfd238b` | 5.56s | 5.92s | 5.38s | 6.02s | 7.22s (n=3) |
| pre-commit, markdown class | `5fbdfd238b` | 6.13s | 6.84s | 5.74s | 7.23s | 9.82s (n=3) |
| `workflow-local-run`, full act path | `3abb246c3c` | 78.71s | 84.86s | 75.04s | 90.70s | not measured before |

Reading it:

- Pre-commit holds. Pre-push does not, on the literal comparison. ADR-104's 300s pre-push
  ceiling holds, with a maximum of 245.58s.
- The comparison is not like for like. The reference is a worst of two runs on a 4-CPU
  container, with load unrecorded. It is not a p95.
- Eight of 20 pre-push repetitions took 143.54s to 245.58s. The other 12 took 100.93s to
  107.13s. The one-minute load before a repetition does not separate the groups. Repetition
  0 ran at load 27.29 and took 107.13s. The cause of the tail is not isolated.
- `pre-pr-validation` carries most of the tail: p50 91.66s, p95 186.13s, max 228.31s.
- The same-host n=20 record at `c5fc0f5bec` (2026-10-23, load 3.26) reads p50 134.88s and
  p95 135.76s. The median fell since then and the p95 rose.
- `python-tests` ran p50 55.82s here against 6.74s in that record. A cold testmon cache in
  this fresh worktree is the likely cause. That is inferred, not observed.
- The `workflow-local-run` figure is the job body timed directly on `yaml-lint.yml`, 20
  counted attempts of 30. The sampler's workflows class cannot reach the act stage. Eight
  attempts were excluded because another act process held act's port and the job exited 0
  without running the workflow. The result covers one small workflow only.
- Standalone `act` v0.2.97 is installed in `~/.local/bin`. Its archive sha256 is
  `67b4976a56f33ea7870b798912e738ec44eef38e7578ae7b532f2def1c73a5ad`, which matches the
  release `checksums.txt` fetched over the same channel. The hook calls `gh act` v0.2.89, not
  this binary.

## Gate 4: flag

The ledger records gate 4 as Met on two named exceptions and six KEEP validators. Since the
2026-09-28 re-measurement (`7bc260179`), validators rose from 104 to 124 and workflows from
56 to 62. The ledger holds no KEEP or exception rows for those additions. The owner's
2026-11-06 note kept gate 4's recorded state, so this report does too. An unqualified Met
is not supported by the counts.

## Gates 5 to 7: the 2026-11-10 rerun

Rule, fixed before the first launch (ledger section "Gate 6 pre-registration, 2026-11-10"):
margin 0.10, Newcombe hybrid-score 95 percent interval, at least 50 runs per arm, and a
per-task guard. Success is deterministic acceptance plus the hidden follow-up. A defect run
passes acceptance and then fails follow-up, violates scope, or records a residual defect.

| Arm | Runs | Success | Defect runs | Cost, USD list price | Wall seconds |
|---|---|---|---|---|---|
| `full` | 70 | 70 | 0 | 11.54 | 1,989 |
| `reduced` | 70 | 69 | 0 | 5.42 | 1,701 |

- Success difference -0.0143, interval -0.0766 to +0.0390. The lower bound clears -0.10.
- Defect difference 0, interval -0.0520 to +0.0520. The upper bound clears +0.10.
- Largest per-task gap: 1 run. Guard clear. Harness launches: 140 of the 150 cap. Harness
  failures: 0. No API key. No credential file copied or linked.
- The single `reduced` miss is `duration-hours` repeat 9. The agent asked which spelling to
  support and changed nothing. Counting its recorded `residual_defects` of 1 as a defect
  anyway gives an interval of -0.0390 to +0.0766, still inside the margin.
- Pooled with the 15 runs per arm of 2026-11-06 (secondary): 84 of 85 against 85 of 85,
  interval -0.0637 to +0.0325.
- Success leaves out `durable.objective_satisfied`, the regex checks on the agent's final
  reply. That check fails in 23 of 70 `full` runs and 19 of 70 `reduced` runs:
  `duration-hours` 14 and 13, `docs-title-publish` 9 and 5, `config-loader-resume` 0 and 1.
  `reduced` does no worse on it. Still, Success here means the code passed its checks, not
  that the reply met every response check.

Limits of the Shown verdict. It covers a 5-task fixture corpus, one model (`claude-sonnet-5`),
and Claude Code 2.1.319. The ambient `~/.claude` load applies under both controls, so
`reduced` is not AGENTS-free. The arms differ by one run in 70, so the corpus may not
exercise the controls. Every record is `UNVERIFIED` because `human_correction_minutes` is
null by owner decision, so formal `ACCEPTED_DURABLE` is 0. No live rollback ran. Codex was
not rerun.

## Deletion

Files removed with no copy elsewhere. Counts come from each merge commit's own diff.

| PR | Merge | Files deleted | Bytes deleted | What |
|---|---|---|---|---|
| #5743 | `5cad780a2` | 56 | 26,508,890 | Dead artifacts: slide-deck PNGs, `.diffray/`, TypeScript island, two disabled workflows, others |
| #5744 | `49c47e7db` | 4 | 21,711 | `rjmurillo-bot.yml`, `auto-assign-reviewer.yml`, their script and test |
| #5878 | `c0b729bc3` | 18 (5 added) | 46,891 | Serena memories consolidated; 3,125 lines out, 1,367 in |
| #6053 | `598a5d8b1f` | 10 | 81,995 | v0.3.0 orchestrator and v0.3.1 plan |
| #6905 | `3efa22801a` | 8 (1 added) | 9,740,793 | claude-mem export blob, importer, tests |
| Total | | 96 | 36,400,280 | |

Of those bytes, about 35.5 MB are two data assets, the slide-deck PNGs and the export blob.
Neither was a control-plane owner. Owners removed outright by these PRs: two workflows
(58 to 56 in #5744). #5436 deleted 0 files; the mechanism never existed in this repository.

## Relocation

Bytes moved, not removed. The ledger gives these relocation rows no gate credit.

- #5887 (`efd148e89`) and #5935 (`8ae97876a`) renamed 3,831 and 119 files, 3,950 in all, from
  `.agents/` to `.project-toolkit/`. They also added a validator.
- M4 folded rule text into skills: #5760 (`55ec6212c`), #5770 (`915043165`), #5776
  (`ff906eb67`), #5779 (`9a1694ef0`). The Copilot instruction mirror went from 56,863 to 36,847
  bytes, and always-on rules from five files to three. No sentence was deleted. The text now
  loads only inside the skills that use it. This is where gate 2's credit comes from.
- #5420 and #5421 are relocation under the epic's own definition: a refactor that moves
  complexity does not count as subtraction.

## Generation

Content produced by a build step from a template, so a hand edit is overwritten.

- ADR-109 moved rules, agents, hooks, `settings.json`, and `lib/` packages to generated
  output under `.claude/`.
- Symlinks into a shipped source tree (ADR-119), counted at `5934169149`: 105 of 122 skill
  entries and 29 of 29 agent entries.
- These count as owners in gate 1. The pinned tree at `53ffe92c2` had no such links, which is
  why the symlink-only reading was rejected.

## Archival

Content kept on purpose, not removed.

- Session logs under `.project-toolkit/sessions/` stay as history; creating new ones is
  discontinued.
- About 12.7 MB of protected history stayed in place after #5420's measurement.
- The claude-mem export blob left the tree in #6905 and stays in git history. Restore it
  with `git checkout 97ea576195 -- .claude-mem/memories/direct-backup-2026-01-03-1434-ai-agents.json`.
- ADRs, incident records, and tests that still protect retained behavior were not deleted,
  per the epic's non-goals.

## Not done, not run

- No git tag and no GitHub release exist for v0.7.0. Creating them is a separate owner call
  and the open next step.
- Gate 3 has no paired measurement at `53ffe92c2`. Replaying that SHA is not a measurement
  this repository can take.
- No hook capture exercised the full act path; only the job body was timed, on one workflow.
- Gates 5 to 7 were not rerun on Codex. Human correction time was not measured.
- The validators (104 to 124) and workflows (56 to 62) added since 2026-09-28 were not audited
  for KEEP justifications.
- A second-model review of this report was not run.
