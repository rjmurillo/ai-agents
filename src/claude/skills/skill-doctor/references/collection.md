# Collection reference

Read this from Step 1 of `SKILL.md` before you change a collector default or
write the sampling part of the report.

## Collector flags

- `--harness VALUE` - which local session sources to scan; use the reference's collector IDs.
- `--repo PATH` - include a project and its registered worktrees; repeatable.
- `--no-worktrees` - grade only the listed paths.
- `--all-conversations` - do not filter conversations by project.
- `--include-global-skills` - also grade global skills.
- `--days N` - lookback window (default 14).
- `--max-sessions N` - cap on sampled sessions across all harnesses (default 100).
- `--top-level-quota N` - reserve up to N of those slots for top-level sessions (default 40). Subagent sessions take the slots left open. `0` samples both types as one pool.
- `--per-skill N` - sampled sessions per skill (default 10).
- `--no-skill N` - sampled sessions that used no skill (default 20).
- `--skills-dir PATH` - nonstandard skill locations.
- `--no-include-subagents` - drop child and sidechain sessions. They are included by default and tagged `thread: subagent`.
- `--include-subagents` - the default for separate child records. Passed explicitly, it also folds Copilot's inline child events into the parent session, which pools child work into that top-level grade.
- `--min-idle-minutes N` - skip sessions active within the last N minutes (default 15; 0 keeps every session).
- `--timeline-supplement N` - add up to N no-skill sessions spaced across the window, tagged as their own stratum. The sample stays non-probability; the inventory says so.
- `--export-corpus PATH` - also write every collected user and assistant message as full-text JSONL (no truncation, token shapes redacted) for panning-for-gold. It follows the same harness, repository, and time-window selection, and it refuses a path inside this skill's directory. It also reads the corpus-only `t3` and `gemini` sources, with `--t3-home` and `--gemini-home` overrides; see `supported-harnesses.md`. Without the flag, output is unchanged.
- `--audit-manifest` - also write `audit_manifest.json`: declared inputs and caps, source revision, upstream identity evidence, scope, and the content-aware skill catalog. It exits 1 and writes no manifest when the evidence contradicts the declared scope.

## Sampling disclosure

The collector splits the `--max-sessions` cap across harnesses, so one harness cannot take the whole sample. The deterministic rule, also stored as `sampling.rule` in `inventory.json`:

Harnesses with scoreable sessions are ranked by scoreable count (descending), then by harness name (ascending). The --max-sessions cap is dealt one slot at a time to that ranking, round-robin, and a harness never receives more slots than it has scoreable sessions. When the cap is lower than the number of harnesses, only the first harnesses in the ranking receive a slot. A harness with no scoreable session takes no slot.

Inside each harness, sessions that used an installed skill are taken first, newest first, until each skill has --per-skill sessions. Remaining slots go to sessions that used no skill, newest first, up to --no-skill. This is skill-first selection: it favors sessions that exercise skills, so per-harness grades describe that slice, not the harness as a whole. The --per-skill and --no-skill caps apply within each harness, and a quota the caps cannot fill is left unused.

Top-level sessions are sampled first, by the same rule, into the `--top-level-quota` reservation. Open reserved slots take the remaining top-level sessions, newest first, past the `--per-skill` and `--no-skill` caps. Subagent sessions then fill the rest, and slots they cannot fill return to top-level sessions. Both types count against the same per-harness `--per-skill` and `--no-skill` caps, so only the reserved backfill passes them. When the reservation leaves no slot for a harness, the notice names `--top-level-quota` instead of the `--max-sessions` cap. `sampling.top_level_rule` stores this text; `sampling.top_level_reserved`, `top_level_sampled`, and `subagent_slots` hold the counts.

### Why these defaults

Calibrated on 2026-11-26 against 546 scoreable local sessions (29 top-level, 517 subagent), all scored. A sample counted as stable when it kept the baseline's top-3 root-cause clusters and top suggestion for each session type, and each per-type rubric mean stayed within 0.05.

- The shipped sampler ran at caps from 60 to 150 with 40 slots reserved for top-level sessions. It ran on two pools: all sessions, and all but the calibration run's own scorers.
- From 85 up, both pools kept the top-level top-3 clusters and both top suggestions. Every rubric mean stayed within 0.05. At 60, mean drift reached 0.10. 85 was the first cap that passed on both pools, and 100 adds margin. At 100, mean drift was 0.03.
- The subagent top-3 did not hold at any cap but one. Its third cluster was a 4 to 3 tie and moved with the sample. Treat the subagent top-3 as unstable at the default.
- The old default of 12 failed the means and the top-3 checks. It kept one suggestion on one pool. Mean drift reached 0.17.
- Top-level sessions are few and weak (24 of 29 failed a rubric), so they need their own reservation. Without it, subagent sessions took most of the cap.
- The 40-slot reservation is inferred, not measured. The pool held only 29 top-level sessions. Their score spread puts one standard error at 0.05 near 47 sessions.
- `--days 14` is inferred, not measured. Local history covered 4 days. The sampler is newest first, so the cap binds before the window for active users. The 14 days assume a light user needs about two weeks to fill the top-level reservation. This was not measured.
- Subagent rankings mostly track how widely one parent fanned out. In calibration, 36 of 37 tags in the top subagent cluster came from one parent session. Read the subagent ranking with that in mind.

 Each harness entry holds `scoreable` (candidates), `skill_candidates`, `quota`, `sampled`, and `sampled_with_skills`. Report candidate and sampled counts for every harness separately.
When `sampling.harness_coverage_complete` is false, state in the report that the cap prevented full harness coverage. Name each entry of `sampling.omitted_harnesses` with its `scoreable` count, and quote `sampling.notice`.
Disclose that selection is skill-first within each harness. Harness balance alone does not make the sample representative.

### Top-level and subagent sessions

Each session in `inventory.json` carries `thread`: `top_level` or `subagent`.
Claude Code, Codex, Warp, Hermes, and Droid store child sessions as their own records.
The collector includes them by default.
Copilot keeps child events inside the parent file.
The collector leaves them out unless you pass `--include-subagents`.
Pi, Grok, ZCode, and Muse record no child concept.

Read `stats.per_thread` for `scoreable` and `sampled` counts per type.
Each harness entry also holds `scoreable_subagent` and `sampled_subagent`.
Report the two types apart. Subagent sessions usually outnumber top-level ones, so a pooled grade hides weak top-level work.
When `sampling.top_level_notice` is set, the sample holds no top-level session. Quote it in the report.

Scope is decided per session, from that session's own cwd. The parent is never consulted.
A child whose cwd is in scope is kept even when its parent ran elsewhere.
A child whose cwd is out of scope is dropped even when its parent is in scope.
A child in a registered linked worktree of `--repo` is in scope.

Worktrees are often short lived, so many sessions ran in a directory that no longer exists.
Such a session stays in scope when it recorded a branch this repository still has.
Its nearest existing folder must also be a checkout of this repository, or the parent folder of one.
So a shared branch name in an unrelated folder never admits a session.
Claude Code records `gitBranch`. Codex records `git.branch`.
The default branch (`main`, `master`, or the remote `HEAD` target) never admits a session.
A path now inside a checkout of another repository is not admitted.
`--no-worktrees` turns this rule off.
`scope_resolution.removed_checkout_sessions` counts the scoreable sessions admitted this way. Each one carries `meta.scope_via: removed_checkout_branch`.
`scope_resolution.removed_checkout_branch_rule` says whether the rule ran. Reftable repositories report it unavailable.
Warp, Hermes, Droid, and Copilot record no branch. Their sessions in a removed worktree stay out unless you pass that path with `--repo`.
A session whose branch was deleted also stays out.

When the run covered exactly one repository (`conversation_scope` is `projects` and `repos` has one entry), you can pass the inventory to `skill-bootstrap` as an initial candidate seed. Bootstrap rejects all-conversations and multi-project inventories.
Bootstrap also rejects the whole inventory when any session's cwd is outside the `--repo` path. Sessions from linked worktrees, live or removed, fail that check. For a seed, collect with `--no-worktrees`.
In a bootstrap child run, return it to the caller instead of starting another run.
Its discovery miner also accepts offline hosted PR, issue, and work-item observations.
Use deterministic inventory counters, not the qualitative grades from Step 2.
Read skill-bootstrap's friction-input reference for its import contract.
Bootstrap owns verification, authoring, and evaluation; a seed grants none of those outcomes.
Keep this handoff separate from the report's failed-conversation scoring.
