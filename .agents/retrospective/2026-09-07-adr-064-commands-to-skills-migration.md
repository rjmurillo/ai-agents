# Retrospective: building the wrong fix before finding the ADR that forbade it

**Date**: 2026-09-07
**Scope**: PR #5631 (closed unmerged), issue #5632, ADR-064, branch `claude/5632-commands-to-skills`
**Failure mode classification**: #2, Skipping retrieval before building
(`.agents/governance/FAILURE-MODES.md`). Secondary touch on #4, False completion
markers, but as an inherited defect rather than one created here: issue #2139 was
closed `completed` in 2026-06 with one of seven acceptance criteria met, and this
session is the first to notice.

## What happened

The task was to teach `generate_commands.py` to mirror a command's `references/`
directory, so a command could use progressive disclosure the way a skill does and
stop being squeezed by the 200-line ceiling. That work was done properly: five
commits, ten new tests with five failing as a negative control against the
pre-change generator, `pre_pr` green, draft PR #5631 opened.

The owner then asked whether converting commands into skills and deleting the
command code would be simpler. It would. Claude Code has merged the two surfaces
outright, so the whole bridge is redundant. PR #5631 was closed unmerged and
issue #5632 opened for the migration.

Twenty minutes into that migration, a rules dump surfaced
`.agents/architecture/ADR-064-commands-to-skills-migration.md`. It decides
exactly what the owner had just decided, dated 2026-06-01, including the naming
scheme for the namespaced sub-commands and a seven-step implementation sequence.
Its tracking issue #2139 was closed as `completed` by PR #2247, which authored
the ADR and nothing else.

So the session built a feature that an accepted-in-substance decision record had
already scheduled for deletion, then re-derived that decision from first
principles, then found the record.

## Impact

| Area | Severity | Effect |
|---|---|---|
| Wasted implementation | Medium | 646 lines of generator and tests written, reviewed by gates, and discarded |
| Duplicated decision work | Medium | An options analysis and an owner decision that ADR-064 had already recorded |
| Issue hygiene | Low | #5632 opened as new work, then rewritten to defer to ADR-064 and #2139 |
| Migration quality | Positive | The detour surfaced the portability finding below, which the ADR does not mention |

## Root cause, five whys

1. Why was the references-mirroring feature built? Because the goal named it and
   the ceiling looked like the constraint to remove.
2. Why was ADR-064 not found first? Because the search was scoped to the symptom,
   not the surface. `grep` ran for `ceiling`, `command_size`, and
   `references/`, and none of those appear in ADR-064's title or body.
3. Why did the ADR index not surface it? Because it was never consulted.
   `AGENTS.md` names `.agents/architecture/README.md -> ADR-*.md` under
   Retrieval, and `search-before-building.md` names ADRs in Layer 1. Both were
   skipped in favour of a targeted content search.
4. Why did a targeted search feel sufficient? Because the task read as a
   generator change, and generator changes rarely have ADRs. The ADR existed
   because the question is architectural, which is exactly the signal that a
   targeted search cannot see.
5. Why was that not caught before the PR? Because every gate the repository runs
   passed. No gate asks "is there a decision record about the surface you are
   changing".

Root cause: **searching for the symptom rather than the surface.** A grep for the
constraint being removed cannot find a record that decided to remove the whole
thing the constraint lives on. When the change touches a canonical authoring
surface, the ADR index is the first read, not a fallback.

## What went well

- **The owner's redirect landed before merge, not after.** The question "better to
  just convert and delete?" arrived while #5631 was still draft, so the cost was
  five commits rather than a revert of merged machinery.
- **Negative controls did their job on the discarded work too.** Five of ten new
  tests failed against the pre-change generator, which is what made it possible to
  say the feature actually worked before deciding not to want it.
- **The tracer bullet paid for itself immediately.** Converting one 53-line
  command end to end before repeating the recipe 19 times surfaced four gotchas
  and one structural blocker that no amount of planning would have predicted.

## What to improve

- **Read the ADR index when the change touches an authoring surface.** Add the
  check to the front of any task that edits a generator, a plugin root, or a
  canonical source tree. The index is one file; reading it costs less than one
  discarded PR.
- **A closed issue is not evidence the work happened.** #2139 lists seven
  acceptance criteria and was closed by a PR satisfying one. Before treating a
  closed issue as done, check its criteria against the tree, not its state field.
- **Record the portability finding where the next migrator will hit it.** See
  below; it is not in ADR-064 and it is the largest per-file cost.

## Findings worth keeping

### Grandfathering does not travel with a moved file

`check_skill_md_portability.py` is a ratchet keyed by path. Moving
`.claude/commands/<name>.md` to `.claude/skills/<name>/SKILL.md` presents the
gate with a new key holding refs that main's baseline does not know, so a pure
move fails. Declaring the refs with a `vendor-portability` marker does not help
either: `marker_files` ratchets against the base ref the same way.

The standalone run hides this. It reads the branch's own baseline, so a re-key
looks clean locally and fails under `--base-ref origin/main`, which is the form
`pre_pr` uses. PR #5629 documented the same gap on a different file.

Measured at `origin/main`: 36 undeclared refs plus 3 declared across the command
tree, concentrated in `sync` (10), `checkpoint` (6), `retro` (5), `spec` (4).

Consequence: every conversion must make its file portable, not just move it. This
is the migration paying for itself. `retro` went from five hard-coded
agent-artifacts paths to zero and the baseline fell from 343 refs across 104
files to 333 across 102.

### Four skillforge gotchas, each found by hitting it

- `argument-hint` must be one bracket group. `'[a] [b]'` parses as two flow nodes
  in Copilot CLI.
- A backticked trigger phrase must not wrap across lines, or it reads as
  containing a newline and fails the unsafe-character check.
- Every backticked span between `## Triggers` and the next heading counts toward
  a hard cap of five trigger phrases, including one sitting in the second column
  of the trigger table.
- The atomic-commit cap of five authored files makes one command per commit the
  working unit: delete, SKILL.md, scenario, and often a baseline or a validator.

### A validator can hardcode the path it guards

`check_build_gates.py` raised `FileNotFoundError` the moment `build.md` moved. It
had to be re-pointed in the same commit, because a conversion that leaves `pre_pr`
red is not a conversion. Expect one of these per command with a dedicated gate.

### The bridge was dropping security comments

`generate_commands.py` rebuilt frontmatter as a dict, so YAML comments never
reached the mirror. `push-pr` carries four security comments (the CWE-78
sanitisation note, the `python3 -I` rationale, the Edit scoping). None of them
had ever shipped to a Copilot install. `generate_skills.py` copies the file, so
converting the command fixed that as a side effect.

## References

- `.agents/architecture/ADR-064-commands-to-skills-migration.md`. The decision, still `proposed`, `implemented: false`.
- Issue #2139. Closed `completed` with one of seven criteria met.
- Issue #5632. The resumed migration.
- PR #5631. The references-mirroring approach, closed unmerged.
- PR #5629. The growth-capacity thread that started this, and the prior record of the base-ref portability gap.
