# REQ-048 TASK-001 Calibration Report

Run date: 2026-11-02. Corpus: Richard Murillo's local Claude Code transcripts.

## Result

The AC-19 gate fails. Consumer B's friction nudge should not ship a default.

- Held-out precision is 17.4 percent (4 of 23). The Wilson 95 percent interval is 7.0 to 37.1 percent.
- AC-19 needs at least 70 percent, with a lower bound of at least 50 percent.
- The held-out split has 23 labeled nudges. That passes the 20-nudge minimum, so the gate result is valid.

Consumer A's `failure-repeat` also fails SLI 6. The judge called 0 of 24 first fires looping.

## Method

### Window and split

- The window is 2026-10-04 to 2026-11-02, using each session's first record timestamp.
- The window holds 8,984 top-level sessions and 3,888 MiB.
- 265 sessions fell outside the window, and 3 had no timestamp.
- Seed 48001 splits the sessions into 6,289 tuning and 2,695 held-out.
- The split list is in `req-048-task-001-split.txt`.
- Both splits share one window. The spec accepts that leakage risk.

### Replay

`scripts/metrics/friction_calibration.py` replays each session with the shipped FailureClassifier.

- A Stop is the point before each typed human turn, plus end of file.
- Each Stop gets the four FrictionSignal counts over the prefix so far.
- `edit_churn` uses the consumer B rule: 3 cycles over the whole scan.

### Labels

Owner decision D17 (2026-11-02) replaced owner labeling with a separate judge model.

- The judge was Claude Sonnet. The weights were picked in an Opus session.
- The rubric, `req-048-task-001-label-rubric.md`, was committed at `181433b19` (2026-11-02) before any label.
- Each judge saw a redacted excerpt and the rubric. It saw no score or threshold.
- `unclear` counts as not worth it.
- `req-048-task-001-labels.csv` holds 191 labels: session id, split, and label only.
- Reasons stay outside the repository, because they quote transcripts.

### Relabel at the nudge Stop

The first labels used excerpts that ended at each session's final Stop. Review found this wrong for 46 of the 76 nudged sessions, where the threshold is crossed before the final Stop. For those, the judge had seen events after the nudge.

The 46 were relabeled from excerpts that end at the crossing Stop, as the rubric says. 15 labels changed. The config stayed frozen, with no refit.

| Split | Nudges | Final-Stop labels | Nudge-Stop labels |
|---|---|---|---|
| Tuning | 53 | 16 (30.2 percent) | 20 (37.7 percent, CI 25.9 to 51.2) |
| Held-out | 23 | 7 (30.4 percent) | 4 (17.4 percent, CI 7.0 to 37.1) |

The nudge-Stop labels are the result of record. The labels CSV holds them.

Consumer A excerpts end at the Stop that holds the first fire, not at the fired call itself. So the judge may have seen later calls in that turn.

## Finding: the adapter double counted

The first replay showed 29 `failed_retry` events. All 29 were artifacts.

- Transcripts hold `api-request-blob` records that embed copies of earlier messages.
- Resumed sessions also repeat records.
- The shipped adapter paired each copy again. One session gave 770 events for 599 real calls.
- That broke AC-38, which allows one event per pair.

This branch fixes `scripts/failure_classifier/transcript.py`. The adapter now reads only `assistant` and `user` records, and it pairs a `tool_use` id once. After the fix, `failed_retry` is 0 in every session.

## SLI 2: consumer B precision

The FrictionScore depends on two live signals only.

| Signal | Total | Sessions above 0 |
|---|---|---|
| `tool_error` | 707 | 201 |
| `permission_denial` | 21 | 17 |
| `failed_retry` (AC-03 rule) | 0 | 0 |
| `edit_churn` | 0 | 0 |

Under Q5's broad rule, `failed_retry` would total 72 instead of 0.

The grid tried every `permission_denial` weight from 0 to 5 and thresholds from 1 to 30. On the tuning split, 19 of 144 candidates were `worth_it`, a 13 percent base rate.

| Config (tool_error weight 1) | Tuning nudges | Precision | Wilson lower bound |
|---|---|---|---|
| denial weight 1, threshold 2 | 76 | 25 percent | 17 percent |
| denial weight 1, threshold 3 | 53 | 30 percent | 20 percent |
| denial weight 0, threshold 6 | 23 | 30 percent | 16 percent |
| denial weight 0, threshold 10 | 8 | 38 percent | 14 percent |

No config with at least 5 tuning nudges reached 40 percent.

The frozen config is all weights 1 with a tier 1 threshold of 3. It was committed at `f9bbc5871` (2026-11-02) before any held-out label. It has the best Wilson lower bound among configs with at least 20 tuning nudges.

`failed_retry` and `edit_churn` never fired, so the data cannot set their weights.

## SLI 3: volume

The frozen config fires 0.84 nudges per 100 tuning sessions (53 of 6,289), and 0.85 over the whole corpus (76 of 8,984). That is under the limit of 15.

Of the 76 sessions that would nudge, 60 are interactive. The corpus holds 88 interactive sessions in total.

## SLI 4: coverage

All 8,984 sessions finished inside the budget: 64 MiB and 2.0 seconds.

- The largest file is under 64 MiB.
- Scan time was p50 0.0018 seconds and p99 0.015 seconds, measured with 16 workers.

## SLI 5: conversion baseline

3 of the 76 sessions that would nudge later ran `/retrospective` in the same session, which is 3.9 percent. Over the whole corpus, 4 sessions ran it.

The baseline is under 20 percent, so the spec's rule for a higher kill floor does not apply.

Deviation: SLI 5 names the 11 Q5 sessions as its corpus. This report uses the full 30-day window instead, which holds those sessions and more.

## SLI 6: consumer A precision

`check-failures` was replayed with the defaults 3, 3, and 20, called after every event.

- `failure-repeat` first fired 24 times. The judge called 0 looping, 23 not looping, and 1 unclear. Precision is 0 percent, with a Wilson upper bound of 13.8 percent.
- `edit-churn` never fired.

There are at least 20 labeled `failure-repeat` nudges and precision is under 50 percent. Under the SLI 6 kill rule, TASK-008 raises that signal's default.

Deviation: SLI 6 names the Q5 corpus. This report uses the full 30-day window, so the sample is larger than Q5 alone would give.

The SLO cannot be set from this measurement, since the spec puts the floor at 50 percent.

## DENIAL_MARKERS check

The judge labeled 21 marker matches and a sample of 104 unmatched denial-like words.

| Term | Denial | Not denial | Typical line |
|---|---|---|---|
| `rejected` (marker) | 0 | 15 | `Exit code N`, ripgrep errors |
| `was denied` (marker) | 5 | 0 | `Permission for this command was denied` |
| `user doesn't want to proceed` (marker) | 1 | 0 | the user refusal |
| `permission denied` (marker) | no hits | no hits | |
| unmatched `denied` | 30 | 1 | `Permission to use Bash with ... denied` |
| unmatched `blocked` | 57 | 13 | `PreToolUse:Bash hook error`, `<tool_use_error>Blocked: sleep` |
| unmatched `forbidden` | 0 | 2 | `Exit code N` |
| unmatched `refused` | 0 | 1 | `Exit code N` |

So `rejected` matches no real denial in this corpus. The markers also miss three common denial forms.

## AC-40 miss rate

The judge labeled 400 sampled successful shell commands that AC-40 does not call a check. 38 were verification runs (95 percent CI 7 to 13 percent).

Across the window there were 556 recognized checks and 19,065 other successful shell commands.

- About 1,811 verification runs went unrecognized. The interval is 1,335 to 2,435. This is INFERRED by scaling the sample.
- The miss rate is about 77 percent (interval 71 to 81 percent), also INFERRED.

Causes seen in the sample:

- **Check later in a compound command.** The check comes after `&&` or `;`, as in `git log ... && pytest`. AC-40 matches only the start of the command.
- **`uv run` followed by flags.** `uv run --frozen pytest` leaves `--frozen` in front of the head.
- **Missing heads.** `build_all.py --check` and `npm run check` are not on the head list.

## Billed cost

Subagent tokens for this task totaled 1,664,735:

- 167,729 for the replay script.
- 1,384,292 for eleven judge runs, including the two relabel runs.
- 112,714 for the review of this branch.

The parent session's own tokens are not measured here. No dollar figure is given, because the per-token price was not checked.

## Open decisions for the owner

These change REQ-048 or its ADR, so they are the owner's call.

1. **Consumer B.** The friction default does not ship under AC-19. Signals as defined reach about 30 percent precision. Options:
   - redefine the signals;
   - ship TASK-003 with the friction branch off by default;
   - drop the friction branch.
2. **DENIAL_MARKERS.** Remove `rejected`. Add the three missed forms.
3. **AC-40.** Decide whether to match checks after `&&` and `;`, allow `uv run` flags, and add `build_all.py --check` and `npm run check`.
4. **Consumer A.** Raise the `failure-repeat` default under the SLI 6 rule, or reconsider the signal.
