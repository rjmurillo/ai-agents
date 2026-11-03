# REQ-048 Friction v2 Report

Run date: 2026-11-03. This follows the TASK-001 report, `req-048-task-001-calibration-report.md`, where the first signal set failed AC-19.

## Result

The friction nudge passes AC-19 as amended by owner decision D19 (2026-11-03).

| Check | Result | Bar |
|---|---|---|
| Out-of-fold, nested 5-fold CV on tuning (the gate) | 12 of 16, 75.0 percent, Wilson lower bound 50.5 percent | at least 70 percent, lower bound 50 percent, at least 15 nudges |
| Held-out, scored once with the frozen config | 4 of 7, 57.1 percent (CI 25.0 to 84.2) | reported, not gated |
| Pooled out-of-fold plus held-out | 16 of 23, 69.6 percent (CI 49.1 to 84.4) | reported, not gated |

The pooled result sits just under 70 percent. The held-out sample is too small to settle that either way.

## Why AC-19 changed

The tuning split holds 23 true friction sessions. Scaled to the held-out split, that is about 10 more (INFERRED). The original gate needed at least 20 held-out nudges at 70 percent, which means at least 14 true positives there. No signal design can pass that on this corpus.

The owner chose to gate on cross-validated tuning precision instead (D19). The 15-nudge floor was set after the measurement.

## What the signals catch

The judge's `worth_it` reasons on the tuning split named three patterns. The patterns occur in any harness, but the detection below reads Claude Code text (see Cross-harness check):

- **Repeated denials the agent kept working around.** Permission prompts, hook blocks, and harness blocks.
- **Stop-hook loops.** A Stop hook kept blocking the stop, and the agent kept replying.
- **The same failure recurring.** For example ENOSPC on every command, or a CI limit missed three times.

Routine single errors were not friction. A `grep` with no match is the common case, so raw `tool_error` gets weight 0.

## Frozen config

The config is in `req-048-friction-v2-frozen-config.json`, committed at `e2edbdb8c` (2026-11-03) before the held-out check.

| Signal | Weight | Definition |
|---|---|---|
| `permission_denial` | 2 | errored result matching the new `DENIAL_MARKERS` |
| `stop_feedback` | 2 | user records that start with `Stop hook feedback:` |
| `error_streak` | 1 | longest run of consecutive errored results |
| `tool_error`, `failed_retry`, `edit_churn` | 0 | |

The tier 1 threshold is 10.

Every signal comes from Claude Code transcript formats, not from this repository's tools. That matters because the plugin is vendor-installed in other repositories.

## Method

### Corpus and labels

- The corpus, window, and seed 48001 split match the TASK-001 report.
- The rubric is `req-048-task-001-label-rubric.md`. The judge was Claude Sonnet (owner decision D17).
- Every label sits at the Stop where its config would fire. 47 extra (session, Stop) pairs were labeled so each grid config had labels at its own firing Stop.
- `req-048-friction-v2-labels.csv` holds 228 labels: split, session id, Stop, and label only.

### Fit and freeze

- The grid covered integer weights (`tool_error` 0 to 1, `permission_denial` 0 to 3, `stop_feedback` 0 to 3, `error_streak` 0 to 1) and thresholds 6 to 25.
- Each CV fold chose its config on the other four folds, by best Wilson lower bound with at least 14 training nudges. It was then scored on the held-back fold (fold seed 48002).
- The frozen config is the full-tuning best with at least 20 nudges: 15 of 20, 75.0 percent, lower bound 53.1 percent.
- `scripts/metrics/friction_fit.py` reproduces the fold choices, the pooled 12 of 16, and the final config from the committed labels CSV and the replay output. Its search scores with the shipped `FRICTION_WEIGHTS` signal names, and a test pins its weighted sum to `friction_score`.

### Held-out

- The held-out split was scored once, after the freeze.
- An earlier, different config had already been scored on it in TASK-001. That look showed counts only, and no held-out reasons were read.

## Candidates tried and dropped

| Candidate | Why dropped |
|---|---|
| `fp_repeat_max`, the max repeat of one fingerprint, with `Exit code N` first lines skipped | Fired in only 1 session at 3 or more |
| `reply_repeat`, near-identical final replies at consecutive Stops | Fired in only 2 sessions |
| raw `tool_error` | No separation: the mean was 6.9 for `worth_it` and 2.4 for `not_worth_it`, but 119 of 121 `not_worth_it` sessions had at least one |

The old fingerprint grouped every `Exit code N` first line together. That inflated failure-repeat to 52 sessions at 3 or more, against 1 under the improved rule. The improved fingerprint is calibration-only here, and consumer A still uses the shipped one.

## Shipped changes

- **`DENIAL_MARKERS`** is now `was denied`, `permission to use`, `user doesn't want to proceed`, `hook error`, `<tool_use_error>blocked`, and `requires approval`. Across the window, 143 errored results move from `tool_error` to `permission_denial`, and the total of 720 errors is unchanged.
- **`FailureSignals.error_streak`** is computed in the classifier's single pass.
- **`stop_feedback_count`** is in the transcript adapter.
- **`FRICTION_WEIGHTS`, `FRICTION_TIER1_DEFAULT`, and `friction_score`** are in the classifier, the one definition AC-43 requires. No hook calls them yet; TASK-003 will.
- **Parity.** The replay now calls the shipped functions. A full rerun matched the frozen features at every Stop: 8,983 sessions, 9,263 Stops, 0 mismatches. The one live session was excluded because it was still growing.

## Volume and next check

- SLI 3 volume under v2: the frozen config nudges 20 of 6,289 tuning sessions (0.32 per 100) and 7 of 2,695 held-out sessions (0.26 per 100).
- Live precision after release. TASK-003 builds the hook, and the post-release check is SLI 2 on new sessions.

## Cross-harness check

Owner request, 2026-11-03: does the frozen config hold on other harnesses' histories?

### Method

- Each harness's 30-day history was converted to the Claude Code record shape. The converters live in `scripts/metrics`: `convert_codex.py`, `convert_copilot.py`, and `convert_droid.py`.
- The converters translate structure only. Error and denial text stay exactly as each harness wrote them. The one rewrite: an explicit stop-hook block in Codex or Copilot gets the `Stop hook feedback:` prefix, so it reaches `stop_feedback`.
- The frozen config ran unchanged, with no refit.

### Result

The config does not carry over.

| Harness | Sessions | Nudges | Top score | Cause |
|---|---|---|---|---|
| Codex | 792 | 0 | 3 | Only 1 session carries a denial, even with the Codex wording added. "Blocked by read-only sandbox" is a sandbox error, not a policy denial. No stop-hook blocks fell in the window. |
| Copilot | 366 | 2 | 153 | Mostly synthetic probe sessions (246 tool calls). With the Copilot wording added, 18 sessions carry a denial. |
| Droid | 20 | 0 | 6 | 149 of 170 recent sessions are subagent sessions. All 591 Stop hook results had exit code 0, so no block was seen; whether Droid records a block at all is INFERRED, not observed. |

### What this means

- These counts include the Copilot and Codex denial wordings added to `DENIAL_MARKERS` after review. Before them, the nudge counts were 0 for Codex and 1 for Copilot.

- Two of the three weighted signals read Claude Code text: `DENIAL_MARKERS` and the `Stop hook feedback:` prefix.
- Copilot marks a denial structurally, with `error.code` set to `denied`.
- Codex records stop-hook blocks, but none fell in this window. Droid records hook runs, and none of its Stop results showed a block.
- No other harness has enough real sessions in this window to reach the 15-nudge floor.

By spec, consumer B ships on Claude Code only. AC-21 excludes Copilot, and REQ-048 does not target Codex or Droid. So the v2 config is valid for consumer B as specified. Taking the friction nudge to another harness needs two things first:

- that harness's adapter must supply denial and stop-block detection from its own structured fields;
- a labeled sample from that harness must pass the same gate.
