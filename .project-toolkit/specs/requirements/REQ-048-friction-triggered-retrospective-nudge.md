---
type: requirement
id: REQ-048
title: Shared tool-failure classifier with a Stop nudge and an in-turn check
status: draft
priority: P2
category: functional
created: 2026-10-31
related:
  - ADR-084
  - "#5817"
  - "#3372"
  - "#3140"
  - "#7035"
---

# REQ-048: Shared tool-failure classifier with a Stop nudge and an in-turn check

This file is durable. It lands in git history. It holds counts and paths only, no transcript text.

## Step 0 First Principles

Answers come from the owner's choices in decision briefs D1 to D3 on 2026-10-31, plus a measurement run the same day.

### Q1

Richard Murillo (repository owner) requested it on 2026-10-31. He asked to adapt Cursor's `continual-learning` Stop hook so a retrospective runs on friction, like claude-mem. Single requester, so Q1 passes on the evidence path: specific Q3 plus evidenced Q5.

### Q2

Today, three surfaces exist and none sees tool-side friction:

1. `invoke_reflect_nudge.py` (Stop, #5817) scans human turns for correction and preference regexes. It prints an advisory. It never reads tool results.
2. `post-pr-retrospective.yml` runs only when a PR closes.
3. `/retro fill` and `/retrospective` run only when a human types them.

So the owner must notice friction, remember it, and invoke `/retrospective` by hand.

Reframing: automation only. The spec makes an existing advisory see a new signal class. It invents no new capability.

### Q3

The owner is the most blocked. Sessions with heavy tool errors and retries end with no prompt to run a retrospective. The nudge stays silent because no human correction regex matched.

Plugin consumers are not evidenced as blocked. Vendoring is the owner's decision (D3, 2026-10-31). That decision, not consumer demand, is the reason on record (ADR-084 Amendment Record, 2026-10-31). The rule 1 consumer-value statement lives in the hook's `Customer value:` line, written at TASK-006 (AC-18).

### Q4

Extend the existing scanner in `invoke_reflect_nudge.py` with three tool-side friction counts. Emit a retrospective advisory when a threshold is crossed. Ship it on the Claude Code plugin surface after an ADR-084 amendment. Estimate: about 9.5 AI-assisted hours (about 9 human days) for the original wedge, 13.5 hours (13 days) with the 2026-11-01 amendments, plus the ADR review cycle and the AC-19 collection period. The task table holds the breakdown.

### Q5

Measured 2026-10-31 over 30 days of `~/.claude/projects/*ai-agents*/*.jsonl`. The run read 8,305 transcripts and excluded sidechains. It found 550 errored tool results, 79 identical back-to-back tool calls, and 29 denials. 11 sessions had 10 or more errors plus repeated identical calls. That count ignores whether the prior call errored, so it is broader than AC-03's `failed_retry`. Every one had zero `HIGH_PATTERNS` matches and fewer than `MED_THRESHOLD` (2) `MED_PATTERNS` matches. So `has_signal` was false and the nudge stayed silent on all 11. All 11 transcripts are under the 64 MiB cap; the largest is 31.3 MiB. The heuristic is ad hoc. TASK-001 replaces it with a calibrated one.

### Q6

At 10x sessions, the cost per session stays flat. The scan is bounded at 2 seconds and 64 MiB. The output is a single advisory line. The risk at scale is advisory fatigue. AC-09 (tier doubling) and the kill criteria under Observability bound it.

## Amendment 2026-11-01: one classifier, two consumers

Owner direction, relayed from the stuck-detection session and confirmed by the owner in decision D9 on 2026-11-01: "combine the cited sources from the origins of both of your PRs. That's what's novel, not two separate items that a user installs. It's our take on the paper."

Two branches had each defined "a failing call retried". This spec now holds one definition:

- **One FailureClassifier.** A single shared module owns every tool-failure signal: `tool_error`, `permission_denial`, `failed_retry`, and `edit_churn`.
- **Consumer A, in-turn check.** The skill script `stuck_detection.py check-failures` sends caller-supplied events to the classifier and prints a short nudge for the agent. PR #7035 holds a first version at `7f3f4d255`, in `src/claude/skills/stuck-detection/failure_loops.py`. TASK-007 moves it onto the shared module.
- **Consumer B, Stop nudge.** `invoke_reflect_nudge.py` sends transcript events to the classifier and prints the retrospective advisory, as before.
- **Consumer C, cross-session facts.** This is deferred. It needs its own ADR-084 decision.

Consumer A registers no hook. ADR-084 defines a vendored hook by its registration, not its directory (rule 5, `ADR-084-vendored-hook-roi-bar.md:203`), so rule 2a does not bind consumer A. A hook trigger for it would be a per-call event, which must clear rule 6's additional bar and needs its own decision.

The Step 0 answers above are the original wedge and stay verbatim. The deltas are:

- Q4 grows by TASK-007 and TASK-008, and TASK-001 and TASK-002 get larger.
- Q5's note that its repeat count is broader than AC-03 held for the 2026-10-31 rule. The windowed AC-03 can count repeats that are not back-to-back, which Q5 missed, so neither count contains the other. TASK-001 measures both.
- Q5 now covers consumer A as well. The stuck-detection session's own Step 0 found no tool-failure loop in 243 retrospectives. The owner overrode that gate, and the Q5 corpus supplies the missing evidence.

## Prior Art / Constraints

### Direct prior art from memory

- `invoke_auto_retrospective.py` (829 lines) was deleted in `b862e14e9` (2026-07-26, #3372). It wrote skeleton files at Stop and returned `decision: "block"`. That dirtied the tree and kept turns alive (#3140). Chesterton's fence verdict: PRESERVE the deletion. This spec never writes to the repo and never blocks.
- Memory `episode-2026-06-11-session-2377-auto-retro-hook-block-and-fill-continuation-relocate` records the earlier block-and-fill design that #3372 retired.
- `invoke_reflect_nudge.py` (#5817, PRD #5820) already adapts claude-mem's user-side correction regexes (`acr/patterns.py`, `acr/behavior.py` at `356b7c08f64c`, Apache-2.0). It already owns the transcript contract, dedupe markers, scan budget, and fail-open exit. Verdict: MODIFY.
- ADR-084 rule 2 lists "retros" as an internal concern that never ships in a vendored hook. Rule 5 requires a `Customer value:` docstring line. `tests/hooks/test_dispatch_groups_parity.py:212-213` authorizes the nudge as "dogfood-only".
- Memory `episode-2026-08-18-session-5154` retired three tool-use hooks from the vendored surface under ADR-084.
- TokenEconomizer: Li, Xu, Singh et al., arXiv 2610.22732, `github.com/microsoft/TokenEconomizer`, Apache-2.0.
  - It has a failure-loop guard that uses a judge model at confidence 0.7 or higher. The guard redirects at most once and never stops a turn.
  - It learns micro-skills: a fact is stated after 3 sessions confirm it and dropped on contradiction.
  - It prunes tools and counts cost as billed.
  - The authors claim 18.4 to 30.9 percent lower mean cost on 277 SWE-Bench tasks. No replication was found.
  - Its `docs/PLUGIN.md` says a nudge has not been shown to change a looping model's course.
  - This spec takes the loop guard with deterministic counts in place of the judge model. It takes no tool pruning.
- PR #7035, `src/claude/skills/stuck-detection/failure_loops.py` at `7f3f4d255`, provides the fingerprint, progress-key, failure-repeat, and edit-churn definitions. Its /review marker `1c887ef30` binds that commit; that is the peer's report and was not re-run here. AC-29 to AC-31, AC-33, and AC-34 restate its definitions and its fixed review findings. AC-35 restates its input limits. Five things change or extend that code: AC-03, AC-32's cycle end on success, AC-35's untrusted-field marking, AC-36 to AC-38, and AC-39.

### Connected context from prior-art search

<!-- citation-freshness: ignore -- lines 128-136 hold the Stop registration; the checker takes its anchor words from the next bullet -->
- Registration, measured 2026-10-31 at `627296450`: `.claude/settings.json:128-136` registers the nudge directly on Stop.
- `templates/hooks/hooks.json` renders `src/claude/hooks.json`, which registers zero hooks. Its description says every plugin registration routes through `invoke_dispatch_claude.py`, with membership in `plugin-*` groups of `dispatch_groups.json`. No dispatch group in `templates/hooks/dispatch_groups.json` is a Stop group or carries `surface: "plugin"`. This hook would be the only vendored hook.
- Cursor `continual-learning` (MIT): `hooks/continual-learning-stop.ts` gates on 10 completed turns, 120 minutes since last run, and an advanced transcript mtime. It then returns `followup_message`, which maps to a Stop block in Claude Code. This spec takes neither: the tier doubling in AC-09 replaces the time gate, and the block is excluded.
- claude-mem: per DeepWiki, it queues raw PostToolUse output to a worker over HTTP and SQLite. It does not classify friction.
- Stop output contract: `agent-harness-reference/references/official-hook-contracts.md` documents only `decision` and `reason` for Copilot `agentStop` (lines 237-252) and Claude Code Stop (lines 442-454). A Stop `systemMessage` is not in that reference. The existing nudge relies on it (`invoke_reflect_nudge.py:444`) as observed behavior, which AC-17 must confirm in the real CLI. No Copilot `transcript_path` field is documented.

### Entity adjudication (human mode)

Method: every component named by a prior-art result was compared against Q3 and Q4 after normalization. Each was then classed by hand.

| Entity | Class | Note |
|---|---|---|
| `invoke_reflect_nudge.py` | in-scope | The hook this spec extends |
| ADR-084 | in-scope | Needs an amendment for rule 2 |
| `AUTHORIZED_HOOKS` | in-scope | Entry text changes from dogfood-only |
| `templates/hooks/dispatch_groups.json` | in-scope | Gains a `plugin-*` Stop group with `surface: "plugin"` |
| `retrospective` skill | in-scope | The advisory's target; already ships |
| `invoke_auto_retrospective.py` | out-of-scope | Deleted; must stay deleted |
| `post-pr-retrospective.yml` | out-of-scope | PR-close path; unchanged |
| `invoke_context_loader.py` skeleton count | out-of-scope | Reads legacy skeletons only |
| Copilot `hooks.json` | out-of-scope | Deferred; no non-blocking channel documented |

Blast-radius count: 0. H11 does not fire.

### Coverage notes

| Source | Status | Result |
|---|---|---|
| `search_memory.py`, 4 queries | RAN | Hits on all 4; relevant ones cited above |
| Hindsight `search_knowledge_pages`, 1 query | RAN | 0 pages. Absence of evidence, not evidence of absence |
| `chestertons-fence` skill | NOT RUN | Done inline instead: `git log --diff-filter=D` and the `b862e14e9` body |
| DeepWiki `thedotmack/claude-mem`, 1 question | RAN | Hook list and no friction classifier |
| Cursor source: `continual-learning-stop.ts`, `hooks.json`, `SKILL.md`, `agents-memory-updater.md` | RAN | Read in full |
| Transcript corpus measurement | RAN | Q5 figures |
| Held-out split (seeded 30 percent of sessions in the measured window) | NOT RUN | Deferred to TASK-001 |

## Problem statement

Sessions with heavy tool-side friction end with no prompt to run a retrospective. The only Stop advisory reads human turns, and 11 of 11 high-friction sessions in 30 days produced no nudge.

## User stories

1. As the repository owner, when my session hits many tool errors or failed retries, I see one advisory at Stop. It names `/retrospective` and the counts, so I can capture the lesson before I forget it.
2. As a plugin consumer, I get the same advisory in my own repo. No files are written to my tree and no turn is blocked.
3. As a maintainer, I can set or disable the threshold with an environment variable, without editing code.
4. As an agent in a long turn, when the same failure repeats across calls or every edit to one file ends in the same failure, `check-failures` tells me so in counts. I can change course before the turn burns more calls. Measured by SLI 6.

## Ontology

- **FailureEvent**: one normalized tool call.
  - Required fields: `tool` (string) and `ok` (bool).
  - Optional fields: `error`, `input`, `target`, and `check` (bool).
  - `check` marks a verification step: a test, build, lint, or typecheck run. AC-40 sets how it is derived when absent.
  - The transcript adapter and the caller-supplied JSON both produce FailureEvents.
- **Fingerprint**: `<tool>|<normalized first error line>` (AC-29). A failure with no error text has none.
- **ProgressKey**: `(tool, canonical input)`, or none when `input` is absent.
  - Canonical input: AC-38 gives consumer B's form, and AC-39 gives consumer A's.
  - A missing ProgressKey matches no other key, so it neither counts toward `failed_retry` nor resets anything (AC-30).
  - Keyless failures still enter the FailureTally under one keyless entry, so failure-repeat sees them.
- **FailureClassifier**: the one shared module. It turns a FailureEvent sequence into FailureSignals: the four FrictionSignal counts, the FailureTally, the per-target ChurnCycle counts, and the `unfingerprinted` count (AC-37). The `unfingerprinted` count is reported and does not feed the FrictionScore. Consumers A and B both call it, so no consumer holds a second definition.
- **FailureSignal**: one classifier output, as listed above.
- **TranscriptScan**: one bounded pass over a Stop event's transcript. It feeds FailureEvents to the FailureClassifier. Existing aggregate.
- **FrictionSignal**: a named count. Kinds: `tool_error`, `permission_denial`, `failed_retry`, `edit_churn`.
- **FrictionScore**: weighted sum of the four FrictionSignals. TASK-001 fixes the weights.
- **CheckFailures**: consumer A. It applies `--repeat`, `--churn`, and `--window` to the classifier output and reports two signals: failure-repeat (AC-33) and edit-churn (AC-32).
- **FailureNudge**: CheckFailures' text for the agent. It holds counts and allowlisted tool names only (AC-34).
- **FrictionTier**: the highest threshold the score has crossed. Tier 0 means below threshold.
- **RetroNudge**: the advisory text. Holds counts and the skill name only.
- **FrictionMarker**: a new dedupe file, separate from the correction marker. Keyed on (session, FrictionTier) only.
- Rule: a FrictionSignal never counts a sidechain record.
- Rule: a RetroNudge fires at most once per (session, FrictionTier).

## Data model

| Entity | Identity | Invariants | Lifecycle |
|---|---|---|---|
| FrictionSignal | (session_id, kind) | count >= 0; non-sidechain records only | Recomputed every Stop; never stored |
| FrictionScore | session_id | integer >= 0 | Recomputed every Stop |
| FrictionTier | (session_id, tier) | tier n needs score >= threshold * 2^(n-1) | Monotonic within one session |
| FailureTally | (ProgressKey, Fingerprint) | count >= 0 | A success for a key removes only that key's entries |
| ChurnCycle | target path | targets normalized (AC-32) | Opens on a successful edit and closes on the next successful check or fingerprinted check failure (AC-32, AC-37, AC-40) |
| FrictionMarker | sha of (session_id, marker version, "friction", tier) | mode 0o600, dir 0o700, outside any repo, body holds counts only | Exclusive create; same 30-day prune as correction markers |

The correction marker key (`invoke_reflect_nudge.py:293-295,351`) stays unchanged. Correction counts never enter the friction key, so a new correction cannot re-fire a friction tier.

Definitions:

- `tool_error`: a `tool_result` block with `is_error: true` that is not a `permission_denial`.
- `permission_denial`: an errored `tool_result` whose text contains, case-insensitive, any entry of `DENIAL_MARKERS`. Initial set: `permission denied`, `user doesn't want to proceed`, `was denied`, `rejected`. TASK-001 checks it against the corpus.
- `failed_retry`: an errored call whose ProgressKey and Fingerprint match an earlier errored call in the window, with no success for that key between the two calls. Each match after the first counts once. A repeat after a success (polling) does not count, and neither does a retry that fails with a different fingerprint. This amends the 2026-10-31 definition, which counted the repeat of the previous call whatever its outcome.
- `edit_churn`: one target whose ChurnCycles end in the same fingerprint a set number of times (AC-32). For consumer A the number is `--churn`. For consumer B it is 3 over the whole scan, and TASK-001 may change it. Consumer B's FrictionScore counts the number of targets that reach it.
- Transcript adapter: each non-sidechain `tool_use` and its `tool_result` become one FailureEvent:
  - `tool` is the tool name, and `ok` is `not is_error`.
  - `error` is the result text. It is used only to compute the fingerprint and is never emitted.
  - `input` is the canonical JSON input.
  - `target` is the `file_path`, `notebook_path`, or `path` input field when the tool is an edit tool.

## Integrations

| System | Contract | Failure mode | Behavior |
|---|---|---|---|
| Claude Code Stop event | stdin JSON with `session_id`, `transcript_path`, `cwd` | Field missing | Exit 0, no output |
| Transcript JSONL | `tool_result.is_error`, `tool_use_id`, `tool_use` name and input, `isSidechain` | Malformed line | Line skipped and counted |
| Plugin registration | A `plugin-*` Stop group with `surface: "plugin"` in `templates/hooks/dispatch_groups.json`, run by `invoke_dispatch_claude.py` and anchored on `CLAUDE_PLUGIN_ROOT` | Launcher path wrong | Caught pre-ship by AC-16 |
| `retrospective` skill | Named in the advisory text only | Skill absent in consumer | Advisory still prints; human decides |
| `stuck_detection.py check-failures` | JSON array of FailureEvents on a file or stdin (AC-35) | Malformed or oversized input | Exit 2, stderr line, empty stdout |

Idempotency: the same transcript and tier always produce the same marker key, so a replayed Stop event is silent.

## Failure modes

| Scenario | Mode | Early warning | Prevention |
|---|---|---|---|
| Advisory fires every turn once friction rises | Fatigue | Many markers per session | AC-09 tier doubling, separate friction key |
| Denial text drifts with a CLI update | Silent miss | `permission_denial` stays 0 on a corpus with denials | TASK-001 fixture test; re-probe on CLI version change |
| Tool output fakes an error string | Spurious nudge | Nudge with no real failures | `tool_error` reads only the `is_error` flag |
| Polling loop counted as retries | Spurious nudge | High `failed_retry` with low `tool_error` | `failed_retry` needs an errored prior result |
| Scan hits time or byte budget | Missed nudge | AC-14 stderr status line | SLI 4 tracks the share that fits |
| Someone re-adds a block decision | Trapped turns (#3140) | Test failure | AC-06 |
| Subagent Stop fires the parent nudge | #3140 recurrence | Marker for a sidechain | Register on `Stop` only; sidechains excluded |
| Stop `systemMessage` stops rendering in a CLI update | Silent advisory | Real-CLI smoke fails | AC-17 |
| State root sits inside any repository (for example a dotfile-managed `$HOME` repo, even when `cwd` is a nested project repo) | Both nudges silent for that user | AC-24 refusal, stderr status line | Set `XDG_STATE_HOME` or `LOCALAPPDATA` outside the repository. If `/` holds a `.git` entry, every root is refused and only the stderr line signals it |
| An edit's own check passes, then an unrelated check fails | Spurious churn on the edited file | Churn on a file whose test passed | AC-32: only a check event ends the cycle; a successful check ends it (AC-40). Found by Devin's review on PR #7035: the code at `7f3f4d255` clears pending cycles only when the success matches a failed key (`failure_loops.py:186-191`) |
| A passing verification that AC-40 does not recognize leaves a cycle open | Spurious churn on that file | Churn reported where the file's own check passed | The caller sets `check: true` (consumer A). TASK-001 measures the vocabulary's miss rate, and the AC-40 fixtures pin each listed head |
| An incidental success (`ls`, `git status`, a read) ends a cycle early | Missed churn | Churn count lower than the edits suggest | Removed by AC-32 and AC-40: only a check ends a cycle (Q-3 resolution) |
| An incidental failure (a failed `cat`, a `grep` with no match) closes a cycle with its fingerprint | Spurious churn | Churn whose fingerprint is not a check's | Removed by AC-32: only a check failure records an outcome (Q-3 resolution) |
| Consumers A and B drift apart | Two definitions again | AC-36 fails | One module; AC-36 feeds one fixture through both adapters |
| A tool name or error text reaches the agent nudge | Prompt injection (CWE-74) | AC-34 fails | Counts plus an allowlist of tool names only |
| Bare-repository dotfile setup (for example yadm) leaves no `.git` entry | State written inside a repository's work tree | None: the `stat` walk cannot see it | Accepted gap; named in AC-24 |

## Security

Trust boundary: the transcript holds untrusted tool output and repo content. The hook reads it and emits counts only.

| Threat | Mitigation |
|---|---|
| Prompt injection through the advisory (CWE-74) | Output is integers in a fixed template; no transcript text (AC-07) |
| Marker path traversal from `session_id` (CWE-22) | Existing `SESSION_ID_PATTERN` allowlist |
| Marker symlink swap (CWE-59) | Existing exclusive create under an owner-only directory |
| Resource exhaustion from a huge transcript (CWE-400) | Existing byte, line, and time caps |
| TASK-001 transcript snapshots hold secrets at rest (CWE-312) | Owner-only 0o700 directory outside any repository; deleted when the AC-19 gate closes or the owner drops the branch |
| Secret disclosure in output (CWE-532) | No free text emitted; nothing to redact |
| Closing tag in tool output escapes the consumer A nudge wrapper (CWE-74) | AC-34 allowlist; four closing tags were seen before the fix (PR #7035 review, round 1) |
| Oversized or endless consumer A input (CWE-400) | AC-35 bounded read; `stat()` is never trusted, since `/dev/zero` and a FIFO report size 0 |
| Fingerprint and target echoed in consumer A JSON output | Marked untrusted in the output contract (AC-35); never pasted into a prompt |

No network, no model call, no writes inside any repository.

## Observability

- SLI 1, latency: hook wall time p99 under 2.5 s on a 64 MiB fixture in the test suite.
- SLI 2, precision: share of friction nudges a human labels "a retro was worth it" on a held-out corpus. SLO: at least 70 percent. TASK-001 writes the label rubric before any labeling. The owner both labels and produces the conversion count while knowing the thresholds; that reflexivity risk is accepted and stated here.
- SLI 3, volume: friction nudges per 100 sessions on the owner's corpus. Over 15 means the threshold is too low.
- SLI 4, coverage: share of target sessions (score at or above threshold) whose scan finished inside the budget. SLO: at least 95 percent. The TASK-001 calibration script computes it offline by replaying the scan, with its budget, over each corpus. Measured 2026-10-31 for bytes only: 11 of 11 under 64 MiB; time not measured.
- SLI 5, conversion: share of sessions with a friction nudge that run `/retrospective` later in the same session. TASK-001 measures the baseline on the 11 Q5 sessions. If the baseline is at or above 20 percent, the owner sets a higher kill floor before release.
- SLI 6, consumer A precision, reported per signal (failure-repeat and edit-churn): share of `check-failures` nudges a human labels "the agent was looping". Each signal's floor and kill rule apply to its own labeled nudges. TASK-001 measures it on the Q5 corpus for the defaults `--repeat 3`, `--churn 3`, `--window 20`. The SLO is set from that measurement, and it may not be below 50 percent. Kill rule: if SLI 6 precision is under 50 percent on at least 20 labeled `check-failures` nudges, TASK-008 raises the defaults. If precision is still under 50 percent on a fresh sample of at least 20, the owner removes the nudge. Below 20 labeled nudges, no SLO is set and the rule waits. The sample grows in 30-day steps, and the owner decides at 90 days. Consumer A's windows count from the date `check-failures` ships with these defaults, which is the merge of the TASK-007 PR (#7035), not from consumer B's Release. The defaults ship at that merge, before SLI 6 is measured. This is owner decision D12 (2026-11-01). Consumer A runs only when an agent calls it, and it prints counts only, so an early ship costs little.
- SLI 7, consumer A effect: the number of later calls that repeat a nudged fingerprint in the same session, compared with un-nudged loops of the same fingerprint. TASK-008 measures and reports it. It feeds the owner's 90-day decision and is not an automatic kill rule (owner decision D11, 2026-11-01). TokenEconomizer's own docs say a nudge's effect on a looping model is unproven, so this is the claim to test.
- Recorded, not gating: billed cost per session, counted as TokenEconomizer counts it (cache pricing included). TASK-001 records it for nudged and un-nudged sessions so a later decision can use it.
- Release: the date AC-19 clears and the default ships. Each window below counts from that date.
- Kill criteria: 30 days after release, remove the friction branch if the conversion rate (nudged sessions that run `/retrospective` later in the same session, divided by all nudged sessions) is under the kill floor (20 percent, or the higher floor set under SLI 5 and recorded in the TASK-001 report), or if precision on a fresh 30-day labeled sample is under 50 percent. Judged on the owner's own transcripts only, since the hook sends no telemetry. The check needs at least 20 nudged sessions in the window; below that, the window extends in 30-day steps and the owner decides at 90 days. The check runs once; later decay is an accepted gap, open to an owner-requested re-check. Removal, or an owner drop at a 90-day decision point, lapses ADR-084 rule 2a.

## Acceptance criteria

1. **AC-01** When a non-sidechain `tool_result` has `is_error: true` and matches no `DENIAL_MARKERS` entry, the scanner shall count one `tool_error`.
2. **AC-02** When a non-sidechain errored `tool_result` matches a `DENIAL_MARKERS` entry, the scanner shall count one `permission_denial` and no `tool_error`.
3. **AC-03** When an errored FailureEvent has the same ProgressKey and Fingerprint as an earlier errored FailureEvent in the window (for consumer B the whole scan, for consumer A `--window`), and no success for that key lies between them, the classifier shall count one `failed_retry`.
4. **AC-04** When a FailureEvent repeats a ProgressKey after a success for that key, or errors with a different Fingerprint, the classifier shall count no `failed_retry` for it.
5. **AC-05** When any Stop event is processed, the hook shall exit 0.
6. **AC-06** When any Stop event is processed, the hook shall emit no `decision` field.
7. **AC-07** When the FrictionScore reaches the tier 1 threshold and no FrictionMarker exists for tier 1, the hook shall emit one `systemMessage` from a fixed template that names `/retrospective` and the four counts, addresses the user, gives the agent no instruction, and contains no transcript text. The existing correction-branch message shall meet the same template rules (condition c and f, both branches).
8. **AC-08** If a correction nudge and a friction nudge both qualify on one Stop, then the hook shall emit one JSON document whose `systemMessage` carries both.
9. **AC-09** While a FrictionMarker exists for tier n, the hook shall emit no friction nudge until the score reaches tier n+1 (double the tier n threshold).
10. **AC-10** When a new correction arrives between two Stops and the FrictionTier is unchanged, the hook shall emit no second friction nudge.
11. **AC-11** Where `AI_AGENTS_RETRO_NUDGE_THRESHOLD` is a positive integer, the hook shall use it as the tier 1 threshold.
12. **AC-12** Where `AI_AGENTS_RETRO_NUDGE_THRESHOLD` is an off value, meaning the literal `0` or `off` (`off` case-insensitive, surrounding whitespace ignored; `00`, `+0`, and `-0` are not off values), the hook shall exit 0 with no output from either the friction or the correction branch, and shall neither read nor write its state.
13. **AC-13** If `AI_AGENTS_RETRO_NUDGE_THRESHOLD` is negative or not an integer, then the hook shall use the calibrated default and exit 0.
14. **AC-14** If the scan stops on the time or byte budget, then the hook shall emit no friction nudge and shall write one status line naming the budget to stderr.
15. **AC-15** When the hook runs inside a temporary git repository, the hook shall leave `git status --porcelain` empty, leave the `.git/` tree byte-identical to a snapshot taken after a priming `git status` and before the run, and write its marker to a path outside the repository.
16. **AC-16** When the plugin from `src/claude/` is installed and the hook runs from a directory that is not the plugin root, the launcher shall find and run the script. A bare relative path in the same harness shall fail (negative control).
17. **AC-17** When a friction-qualifying Stop runs in the real Claude Code CLI, the `systemMessage` shall reach the user intact through the plugin registration, and the next turn's model context shall not contain the advisory text.
18. **AC-18** When the hook ships in a `surface: "plugin"` dispatch group, the restored ADR-084 rule 5 presence test shall find one `Customer value:` line in its module docstring that names `AI_AGENTS_RETRO_NUDGE_THRESHOLD` and its off values, and the module docstring shall state the firing bound (at most one friction nudge per session per threshold tier).
19. **AC-19** When TASK-001 has chosen weights and the default threshold on the tuning split (a seeded random 70 percent of sessions in the measured 30-day window), the held-out split (the other 30 percent, labeled by Richard Murillo) shall show at least 70 percent precision, with a Wilson 95 percent lower bound of at least 50 percent, before the default ships. The TASK-001 report shall record the window dates, the seed, and the split session list, and shall note that both splits share one window (leakage risk accepted under the owner's decision). The gate is valid only when the held-out split holds at least 20 labeled friction nudges. Weights and the default freeze on the tuning split before any held-out session is labeled. Every session snapshotted after that freeze joins the held-out split only. Below 20 labeled nudges, TASK-001 snapshots new transcripts daily into owner storage, since Claude Code keeps about 30 days locally (oldest local transcript 2026-10-02, measured 2026-10-31), and the default does not ship. If the count is still under 20 at 90 days after TASK-001 starts, the owner decides whether to keep collecting or drop the friction branch. At the Q5 rate the count may take longer than 90 days (INFERRED), so that decision point is a likely path.
20. **AC-20** Where `AI_AGENTS_RETRO_NUDGE_THRESHOLD` is an off value as AC-12 parses it, the hook shall not open the transcript.
21. **AC-21** When the plugin is generated, `src/copilot-cli/hooks/hooks.json` shall carry no entry for the hook, through `copilotExclude: true` on its dispatch group.
22. **AC-22** When a test fixture plants a readable file outside the rule 2a condition e inputs and calls the hook module's `run()` directly with both branches active, the hook shall not open it (observed with a `sys.addaudithook` hook on `open`). It shall read no environment variable outside this list: `AI_AGENTS_RETRO_NUDGE_THRESHOLD`, `XDG_STATE_HOME`, `LOCALAPPDATA`, and the variables `Path.home()` consults (`HOME`; on Windows `USERPROFILE`, `HOMEDRIVE`, `HOMEPATH`). A recording mapping installed as `os.environ` for the run observes this, so `Path.home()` lookups are seen too. The launcher (`invoke_dispatch_claude.py`) may also read `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PROJECT_DIR`; AC-16 covers it.
23. **AC-23** Where `AI_AGENTS_RETRO_NUDGE_THRESHOLD` is unset or a positive integer and a correction-qualifying Stop runs, the hook shall still emit the correction nudge (positive control for AC-12).
24. **AC-24** Where the hook is not off (AC-12 is checked first), if `HOME` is unset on POSIX, or any directory from the resolved state root up to the filesystem root holds a `.git` entry (found with `stat` calls only, before any `mkdir`), then the hook shall create no directory or file, emit no `systemMessage`, write one stderr status line, and exit 0. Fixtures cover a `.git` directory, a `.git` file (linked worktree), a symlinked state root that resolves into a repository, a state root that does not exist yet, and an unset `HOME` on POSIX. Bare-repository setups with no `.git` entry are an accepted gap.
25. **AC-25** When the plugin is generated, the hook's dispatch group shall register on `Stop` only, and on no event whose output enters model context.
26. **AC-26** When the hook's dispatch group runs on `Stop` and the hook emits a `systemMessage`, the plugin launcher shall pass it through as a `systemMessage` document, not as plain Stop stdout (`claude_hook_dispatch.py` treats `Stop` as a plain-context event today).
27. **AC-27** If the plugin launcher fails on any path for this group, then it shall exit 0 and write one stderr status line. The paths are: manifest load (`invoke_dispatch_claude.py:202-210`), oversized stdin (`:186-193`, `:226-227`), an execution exception (`:229-236`), and a non-zero exit from the hook. Each returns the launcher's block exit code today, and the group's mode must not turn any of them into a block.
28. **AC-28** When the hook's dispatch group runs a Stop through the launcher with both branches active, a `sys.addaudithook` probe on `open` shall see no file outside this list: the plugin's own installed files, the Python interpreter and its libraries (paths under `sys.base_prefix` or `sys.prefix`), the transcript, the hook's state, and the two consumer-repo plugin manifests the self-hosting check reads, `.claude/.claude-plugin/plugin.json` and `src/claude/.claude-plugin/plugin.json` (`invoke_dispatch_claude.py:112-115`, `:142-143`).
29. **AC-29** When a FailureEvent has error text, the classifier shall build its Fingerprint in six steps:
    1. Take the tool name, lowercased and trimmed.
    2. Take the first non-blank error line, trimmed and lowercased.
    3. Replace each hex run with `H`. A hex run is `0x` plus 7 or more hex digits, or a bare run of 7 or more holding a digit and a letter, so a word such as "defaced" stays.
    4. Replace each remaining digit run with `N`.
    5. Collapse whitespace and cap the line at 200 characters.
    6. Join the two parts as `<tool>|<line>`.
    A FailureEvent with no error text shall get no Fingerprint.
30. **AC-30** When a FailureEvent succeeds and its ProgressKey matches FailureTally entries, the classifier shall remove only that key's entries, in both the repeat and churn tallies. A FailureEvent with no ProgressKey shall reset nothing. Fixtures cover a successful `ls` between test runs and a fixed `make build` beside an `npm test` loop with the same first line.
31. **AC-31** When an edit tool fails with error text, the classifier shall count it toward `failed_retry` and in the FailureTally that failure-repeat reads. Example: `old_string not found` three times.
32. **AC-32** The classifier shall track `edit_churn` with ChurnCycles:
    - **Opening.** A successful edit with a target opens a pending cycle for that target. Targets are normalized: backslashes become forward slashes, then `posixpath.normpath`, capped at 512 characters.
    - **Closing on failure.** The first fingerprinted failure of a check (AC-40) closes every pending cycle and records its fingerprint as the cycle's outcome. A non-check failure, such as a failed `cat` or a `grep` with no match, leaves pending cycles open.
    - **Closing on success.** A successful check (AC-40) ends every pending cycle with no outcome, whether or not its key failed earlier and whether or not it has a ProgressKey. Any other successful non-edit event, such as `ls`, `git status`, or a file read, leaves pending cycles open. AC-30's tally reset still needs a matching key. Fixtures:
      - Devin's case reports no churn on `a.py`: edit `a.py`, pass `pytest tests/a.py`, fail `pytest tests/b.py`, three times.
      - A keyless successful check ends the cycle.
      - Edit `a.py`, run `ls` and `git status` successfully, then fail `pytest tests/a.py` the same way three times. That reports churn on `a.py`.
      - Edit `a.py`, fail `cat missing.txt`, then pass `pytest tests/a.py`. That cycle records no outcome.
    - **Firing.** `edit_churn` fires when one target has a set number of cycles that share a fingerprint: `--churn` (default 3) within the last `--window` events for consumer A, and 3 over the whole scan for consumer B.
    - **Exceptions.** A failed edit closes no cycle. A successful edit without a target opens none. A successful edit leaves other targets' pending cycles in place.
    - **Edit tools.** edit, write, multiedit, str_replace, create, apply_patch, and notebookedit.
33. **AC-33** When the errored FailureTally entries for one Fingerprint, summed across keys, reach `--repeat` (default 3) within the last `--window` FailureEvents (default 20), CheckFailures shall report failure-repeat.
34. **AC-34** When CheckFailures reports a signal, its nudge shall contain only these things:
    - signal names;
    - integer counts;
    - a tool name, only if it is on the allowlist: the edit tools plus bash, shell, powershell, read, view, grep, glob, webfetch, and task. Any other name prints as "tool".
    It shall list at most 5 signals, edit-churn first, then "and N more". It shall contain no error text, input, or path.
35. **AC-35** If CheckFailures gets any of the inputs below, then it shall exit 2, write one `stuck-detection:` stderr line, and print nothing on stdout:
    - invalid JSON or invalid UTF-8;
    - nesting deep enough to raise RecursionError;
    - an event of the wrong shape;
    - more than 10,000 events, or more than 8 MiB measured by a bounded read, never by `stat()`;
    - an unreadable file, a TTY, or a closed stdin;
    - a threshold or window below 2.
    On valid input it shall exit 0 with JSON. That JSON marks `fingerprint` and `target` as untrusted.
36. **AC-36** When one fixture of 20 or fewer events runs through the transcript adapter (consumer B) and through CheckFailures input (consumer A), the classifier shall return the same FailureTally and the same per-target ChurnCycle counts for both. The fixture events carry no `check` field, so both consumers apply the derived AC-40 rule.
37. **AC-37** When an errored FailureEvent has no error text, the classifier shall count it as a `tool_error` and in an `unfingerprinted` count, and shall leave it out of every fingerprinted signal.
38. **AC-38** When a transcript holds a non-sidechain `tool_use` and its `tool_result`, the transcript adapter shall emit exactly one FailureEvent for the pair, with the fields listed under Definitions. Its canonical input is the tool input serialized as JSON with:
    - sorted keys;
    - `,` and `:` as separators, with no other whitespace;
    - non-ASCII characters escaped as `\uXXXX`.
    When a JSON object repeats a key, the last value wins.
39. **AC-39** When CheckFailures reads an event whose `input` is a string that parses as RFC 8259 JSON (so `NaN` and `Infinity` do not count), it shall canonicalize the parsed value the way AC-38 does: sorted keys, compact separators, `\uXXXX` escapes, and the last value winning on a repeated key. It shall use any other `input` string as given, after trimming. A non-string `input` is a wrong event shape (AC-35, exit 2). The AC-36 parity fixture therefore compares equal keys for equal inputs. Fixtures cover keys out of order, extra whitespace, non-ASCII text, a repeated key, and a non-JSON command string.
40. **AC-40** A non-edit FailureEvent is a check under these rules:
    - **Caller-marked.** Its `check` field is `true`. A `check: false` makes it not a check. A non-bool `check` is a wrong event shape (AC-35). On an edit event, `check` is ignored.
    - **Derived when unmarked.** With no `check` field, the event is a check when both of these hold:
      - its tool is a shell tool: bash, shell, or powershell;
      - its command, after leading wrappers are stripped, starts with a check head.
    - **Wrappers.** `cd <dir> &&`, `VAR=value` assignments, `uv run`, `npx`, `python -m`, `python3 -m`, and `timeout <n>`.
    - **Test heads.** pytest, py.test, unittest, tox, nox, jest, vitest, and mocha.
    - **Build heads.** make, mvn, and gradle; `npm`, `yarn`, or `pnpm` followed by `test`, `build`, `lint`, or `typecheck` (optionally after `run`); `cargo test`, `cargo build`, `cargo check`, and `cargo clippy`; `go test`, `go build`, and `go vet`; `dotnet test` and `dotnet build`.
    - **Lint and typecheck heads.** tsc, eslint, ruff, mypy, pyright, shellcheck, and markdownlint or any `markdownlint`-prefixed command, such as `markdownlint-cli2`.
    - **Matching.** Heads and wrappers match case-insensitively. A head must be followed by whitespace or the end of the command.
    - **Script and hook heads.** `python` or `python3` running a script whose file name starts with `test_`, `check_`, or `validate_`, or is `pre_pr.py`. Also `lefthook run` and `pre-commit run`.
    - **Everything else.** Any other event is not a check: a read tool, a non-shell tool, or a shell command with no check head.
    - **Both consumers.** The transcript adapter applies the derived rule, because transcripts carry no `check` field. CheckFailures uses the caller's field and falls back to the derived rule.
    - **Fixtures.** One per listed head, one per wrapper, and these non-checks: `ls`, `git status`, `cat`, `echo pytest`, and `python3 scripts/foo.py`.

## Out of scope

- Writing retrospective files, skeletons, or memory from the hook.
- Any Stop `decision: "block"`, and any `followup_message` equivalent.
- A time-based cadence gate like Cursor's 120-minute rule.
- Headless `claude -p` runs at SessionEnd.
- Copilot CLI registration.
- PostToolUse or PostToolUseFailure hooks (ADR-084 rule 6).
- User interrupts as a signal. They counted 0 in the Q5 corpus.
- Changing `post-pr-retrospective.yml` or the `/retro` skill.
- A judge model in either consumer (TokenEconomizer uses one; this spec uses deterministic counts).
- Tool pruning. It can deny `Skill` and `Agent`, which routing depends on, and ADR-084 rule 6 applies.
- A hook trigger for consumer A. It would be a per-call event, which must clear ADR-084 rule 6's additional bar and needs its own decision.

## Deferred

| Item | Owner | Reason |
|---|---|---|
| Copilot `agentStop` port | Richard Murillo | Documented output is block-only, with no `transcript_path`. Revisit when Copilot documents an advisory field. |
| LLM-assisted friction classification | Richard Murillo | Deterministic counts first. Revisit only if SLI 2 misses. |
| Consumer C: cross-session facts | Richard Murillo | A failed call followed by a working variant becomes a fact candidate. It is promoted after 3 confirming sessions, dropped on contradiction, and routed through `reflect` for human approval. Needs its own ADR-084 decision. |

## Open questions

| Question | Owner |
|---|---|
| Q-1 (resolved 2026-10-31): both. Rule 2 narrows to "retro enforcement" and rule 2a adds the named exception. The ADR-084 Amendment Record gives the reasons. | ADR-084 review panel |
| Q-2 (resolved 2026-10-31): yes. The ADR-084 rule 5 correction records zero vendored hooks at `9254b9945`. | ADR-084 review panel |
| Q-3 (resolved 2026-11-01): only a check event, success or failure, ends a ChurnCycle (AC-32, AC-40). Evidence is under "Q-3 evidence" below. | Richard Murillo |

### Q-3 evidence

Measured 2026-11-01 over the same corpus location as Q5, `~/.claude/projects/*ai-agents*/*.jsonl`:

- 8,491 transcripts, 3,578 MiB. 5,476 of them hold no tool calls.
- 29,060 non-sidechain tool events.

The replay's check rule is AC-40 exactly: its head list, its wrappers, and the shell tools bash, shell, and powershell. The success counts below use a wide window: from a successful edit up to the next fingerprinted non-edit failure, with no success ending it. That window can hold several checks, so the 244 checks below are more than the 139 cycles rule D ends. Of the non-edit successes inside those windows, 244 are checks and 8,578 (97 percent) are not:

| Success kind | Count |
|---|---|
| Other bash commands | 6,756 |
| Read and search tools | 1,017 |
| Other tools, including non-check `shell` and `powershell` calls | 805 |
| Checks | 244 |

The four cycle-end rules give these results:

| Rule | edit_churn fires | Cycles closed by a failure (of which a check failed) | Cycles ended by a success |
|---|---|---|---|
| A: any non-edit event closes or ends (AC-32 as of `8dd4f43d5`) | 1 | 15 (2) | 650 |
| B: only a check success ends; any failure closes | 2, in 2 sessions | 124 (2) | 119 |
| C: only a success on a failed key ends (`failure_loops.py` at `7f3f4d255`) | 5, in 3 sessions | 154 (4) | 0 |
| D: only a check event ends or closes (adopted) | 0 | 2 (2) | 139 |

What the numbers show:

- Under rule B, 122 of 124 failure closes come from non-check failures, so its extra outcomes are noise.
- Rule C keeps Devin's false positive, and also attaches non-check failures as outcomes.
- Rule D attaches only check results to an edit, which is what edit-churn means. It fires 0 times here, because only 2 cycles ever reached a check failure.
- In this corpus, edit-churn is close to absent. TASK-001 measures its precision and may weight it 0 in consumer B's FrictionScore. Consumer A keeps it, judged by SLI 6's per-signal edit-churn floor once it has 20 labeled edit-churn nudges. Until then it ships under D12 and is reviewed at the 90-day decision.

The replay script lives outside the repository. TASK-001's calibration script supersedes it.

Prior art, read by a research subagent on 2026-11-01 (raw files on each project's default branch):

- **TokenEconomizer**
  - `tokeneconomizer/loopguard/state.py:17-19` counts test runs by a command regex.
  - `tokeneconomizer/microskills/observe.py` holds runner, task, and build vocabularies. It strips wrappers first, at lines 112 to 124.
  - It excludes read tools from failure detection.
- **Aider** (`aider/coders/base_coder.py:318-321`, `:1599-1625`) uses caller-declared `--test-cmd` and `--lint-cmd`, judged by exit code.
- **OpenHands and SWE-agent.** OpenHands' `stuck_detector.py` detects exact repetition only. SWE-agent has no loop detector and lints inside its edit tool. Neither has a check concept.

No source ends an edit cycle on any non-edit event. AC-40 combines a caller-marked field, as Aider has, with a vocabulary fallback, as TokenEconomizer has.

## CVA summary

- Common: one FailureClassifier, one Fingerprint, and one ProgressKey rule, so every consumer agrees.
- Common: an output of counts only.
- Varies: the event source (a transcript or the caller's JSON), the audience (the user at Stop or the agent in-turn), thresholds, and message text.
- Relationship: consumers A and B are thin adapters over the classifier. Human-correction signals stay in the Stop hook.

## Buy-vs-build decision

- Classification: context (developer-experience support work).
- Alternatives:
  - claude-mem (Apache-2.0) needs a worker daemon, SQLite, and SDK calls. It has no friction classifier. Rejected.
  - Cursor continual-learning (MIT) triggers with a block and writes `AGENTS.md`. Both conflict with #3372. Rejected.
  - TokenEconomizer (Apache-2.0) has a judge-model loop guard and tool pruning. Its judge adds a model call, and pruning conflicts with ADR-084 rule 6. Adapted: deterministic counts only.
  - Extend `invoke_reflect_nudge.py`. It reuses the transcript contract, caps, tests, and authorization.
- Recommendation: build, as an in-place extension.

## Complexity classification

- Engineering tier: 4. It changes a vendored-surface decision and needs an ADR amendment.
- Cynefin domain: Complicated. Calibration over labeled corpora is a known analysis.
- Methodology: ADR amendment first, then test-first implementation, then the calibration gate.

## ADR cross-reference

Requires ADR-084 rule 2a (proposed 2026-10-31 on branch `docs/adr-084-retro-nudge-amendment`, debate log `ADR-084-debate-log-2.md`). Rule 2a conditions map as follows: a to AC-05 and AC-06; b to AC-15 and AC-24; c to AC-07; d to AC-25; launcher path for a, e, and f to AC-26 to AC-28; e to AC-22; f to AC-07 and AC-17; g to AC-09, AC-11 to AC-13, AC-18, AC-20, and AC-23. The amendment blocks AC-16 to AC-18, AC-21, and AC-25 to AC-28 only. AC-01 to AC-15, AC-19, AC-20, AC-22 to AC-24, AC-29 to AC-32, AC-36 to AC-38, and AC-40 can land dogfood-first under the existing authorization. Consumer A (AC-33 to AC-35 and AC-39) ships in the plugin when #7035 merges, because `src/claude/skills/` is plugin source. It sits outside rule 2a, because it registers no hook. ADR-084 defines a vendored hook by its registration (`ADR-084-vendored-hook-roi-bar.md:203`).

## Tasks (sequenced)

| ID | Task | ACs | Depends on | Estimate (human / AI) |
|---|---|---|---|---|
| TASK-001 | Calibration script; seeded 70/30 session split of the measured window; owner labels the sample; check `DENIAL_MARKERS`; measure both `failed_retry` definitions (the AC-03 rule and Q5's broader repeat count); measure SLI 6 for the consumer A defaults (3, 3, 20) and set its SLO; record billed cost; pick weights and default; report SLI 4; measure the SLI 5 baseline and build the same-session follow check for the kill criterion; write the SLI 2 label rubric before any labeling; measure the AC-40 vocabulary's miss rate on passing verification runs | AC-19 | none | 3.5 days / 4 h |
| TASK-002 | Shared FailureClassifier and transcript adapter, with fixture tests. Its location follows the generated-lib rules in `.claude/AGENTS.md`. AC-01 to AC-04 fix the counters, so calibration is not needed first. Includes the AC-32 fixtures for Devin's cycle-end case and the AC-40 check vocabulary with its fixtures | AC-01 to AC-04, AC-29 to AC-32, AC-37, AC-38, AC-40 | none | 2 days / 2 h |
| TASK-003 | Friction marker, merged output, env config, budget status | AC-07 to AC-14, AC-20, AC-23 | TASK-002 | 1 day / 1 h |
| TASK-004 | Exit, no-block, clean-tree, and input-limit tests; reorder `_safe_marker_dir` so the state-root walk runs before any `mkdir` | AC-05, AC-06, AC-15, AC-22, AC-24 | TASK-003 | 0.5 day / 30 min |
| TASK-005 | ADR-084 amendment with debate log | Q-1, Q-2 | none | 2 days / 2 h plus review |
| TASK-007 | Move `check-failures` (PR #7035) onto the shared FailureClassifier and delete its private definitions. Keep the PR #7035 regression tests | AC-33 to AC-36, AC-39 | TASK-002 | 1 day / 1 h |
| TASK-008 | Post-ship consumer A review: label `check-failures` nudges from the #7035 merge on, measure SLI 6 and SLI 7, retune the defaults, and bring the 90-day decision to the owner | SLI 6, SLI 7 (no AC) | TASK-007 | 1 day / 1 h |
| TASK-006 | `plugin-*` Stop dispatch group with `copilotExclude`, `Customer value:` line, restore both rule 5 tests, runtime-contract test, real-CLI smoke, ADR-071 runtime contract, ADR-085 Decision 7 field governance with each of its nine items mapped to this use (item 3: a new authorizing issue; item 4: ADR-084 rule 2a; item 5: Copilot users get no nudge; item 7: the reintroduction trigger is Copilot documenting an advisory field and `transcript_path`, replacing the #5013 gates; item 8: the exclusion is conditional, so the cleanup obligation applies only if it becomes permanent; items 1, 2, 6, and 9 as written), the `dispatch_groups.json` `description` wording for a non-security exclusion, `tool-use-hook-bar.md` wording, ledger text; launcher changes for a Stop advisory group (systemMessage pass-through, fail-open manifest load) | AC-16 to AC-18, AC-21, AC-25 to AC-28 | TASK-004, TASK-005 | 2 days / 2 h |

TASK-002 and TASK-007 may ship in one PR (#7035), so AC-36 is tested where the classifier lands. Total: 13 human days, 13.5 AI-assisted hours, plus ADR review. Calendar time is set by the AC-19 collection period, which may pass the 90-day decision point.
