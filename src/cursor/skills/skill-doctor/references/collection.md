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
- `--include-subagents` - include child or sidechain sessions.
- `--min-idle-minutes N` - skip sessions active within the last N minutes (default 15; 0 keeps every session).
- `--timeline-supplement N` - add up to N no-skill sessions spaced across the window, tagged as their own stratum. The sample stays non-probability; the inventory says so.
- `--export-corpus PATH` - also write every collected user and assistant message as full-text JSONL (no truncation, token shapes redacted) for panning-for-gold. It follows the same harness, repository, and time-window selection, and it refuses a path inside this skill's directory. It also reads the corpus-only `t3` and `gemini` sources, with `--t3-home` and `--gemini-home` overrides; see `supported-harnesses.md`. Without the flag, output is unchanged.
- `--audit-manifest` - also write `audit_manifest.json`: declared inputs and caps, source revision, upstream identity evidence, scope, and the content-aware skill catalog. It exits 1 and writes no manifest when the evidence contradicts the declared scope.

## Sampling disclosure

The collector splits the `--max-sessions` cap across harnesses, so one harness cannot take the whole sample. The deterministic rule, also stored as `sampling.rule` in `inventory.json`:

Harnesses with scoreable sessions are ranked by scoreable count (descending), then by harness name (ascending). The --max-sessions cap is dealt one slot at a time to that ranking, round-robin, and a harness never receives more slots than it has scoreable sessions. When the cap is lower than the number of harnesses, only the first harnesses in the ranking receive a slot. A harness with no scoreable session takes no slot.

Inside each harness, sessions that used an installed skill are taken first, newest first, until each skill has --per-skill sessions. Remaining slots go to sessions that used no skill, newest first, up to --no-skill. This is skill-first selection: it favors sessions that exercise skills, so per-harness grades describe that slice, not the harness as a whole. The --per-skill and --no-skill caps apply within each harness, and a quota the caps cannot fill is left unused.

Read `stats.per_harness` and `sampling` in `inventory.json`. Each harness entry holds `scoreable` (candidates), `skill_candidates`, `quota`, `sampled`, and `sampled_with_skills`. Report candidate and sampled counts for every harness separately.
When `sampling.harness_coverage_complete` is false, state in the report that the cap prevented full harness coverage. Name each entry of `sampling.omitted_harnesses` with its `scoreable` count, and quote `sampling.notice`.
Disclose that selection is skill-first within each harness. Harness balance alone does not make the sample representative.

When the run covered exactly one repository (`conversation_scope` is `projects` and `repos` has one entry), you can pass the inventory to `skill-bootstrap` as an initial candidate seed. Bootstrap rejects all-conversations and multi-project inventories.
In a bootstrap child run, return it to the caller instead of starting another run.
Its discovery miner also accepts offline hosted PR, issue, and work-item observations.
Use deterministic inventory counters, not the qualitative grades from Step 2.
Read skill-bootstrap's friction-input reference for its import contract.
Bootstrap owns verification, authoring, and evaluation; a seed grants none of those outcomes.
Keep this handoff separate from the report's failed-conversation scoring.
