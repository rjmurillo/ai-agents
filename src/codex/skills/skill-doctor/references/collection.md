# Collection reference

Read this from Step 1 of `SKILL.md` before you change a collector default or
write the sampling part of the report.

## Collector flags

- `--harness VALUE` - which local session sources to scan; use the reference's collector IDs.
- `--repo PATH` - include a project and its registered worktrees; repeatable.
- `--no-worktrees` - grade only the listed paths.
- `--all-conversations` - do not filter conversations by project.
- `--include-global-skills` - also grade global skills.
- `--days N` - lookback window (default 45).
- `--max-sessions N` - cap on sampled sessions across all harnesses (default 12).
- `--skills-dir PATH` - nonstandard skill locations.
- `--no-include-subagents` - drop child and sidechain sessions. They are included by default and tagged `thread: subagent`.
- `--include-subagents` - the default for separate child records. Passed explicitly, it also folds Copilot's inline child events into the parent session, which pools child work into that top-level grade.
- `--min-idle-minutes N` - skip sessions active within the last N minutes (default 15; 0 keeps every session).
- `--timeline-supplement N` - add up to N no-skill sessions spaced across the window, tagged as their own stratum. The sample stays non-probability; the inventory says so.
- `--audit-manifest` - also write `audit_manifest.json`: declared inputs and caps, source revision, upstream identity evidence, scope, and the content-aware skill catalog. It exits 1 and writes no manifest when the evidence contradicts the declared scope.

## Sampling disclosure

The collector splits the `--max-sessions` cap across harnesses, so one harness cannot take the whole sample. The deterministic rule, also stored as `sampling.rule` in `inventory.json`:

Harnesses with scoreable sessions are ranked by scoreable count (descending), then by harness name (ascending). The --max-sessions cap is dealt one slot at a time to that ranking, round-robin, and a harness never receives more slots than it has scoreable sessions. When the cap is lower than the number of harnesses, only the first harnesses in the ranking receive a slot. A harness with no scoreable session takes no slot.

Inside each harness, sessions that used an installed skill are taken first, newest first, until each skill has --per-skill sessions. Remaining slots go to sessions that used no skill, newest first, up to --no-skill. This is skill-first selection: it favors sessions that exercise skills, so per-harness grades describe that slice, not the harness as a whole. The --per-skill and --no-skill caps apply within each harness, and a quota the caps cannot fill is left unused.

Read `stats.per_harness` and `sampling` in `inventory.json`. Each harness entry holds `scoreable` (candidates), `skill_candidates`, `quota`, `sampled`, and `sampled_with_skills`. Report candidate and sampled counts for every harness separately.
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
In a bootstrap child run, return it to the caller instead of starting another run.
Its discovery miner also accepts offline hosted PR, issue, and work-item observations.
Use deterministic inventory counters, not the qualitative grades from Step 2.
Read skill-bootstrap's friction-input reference for its import contract.
Bootstrap owns verification, authoring, and evaluation; a seed grants none of those outcomes.
Keep this handoff separate from the report's failed-conversation scoring.
