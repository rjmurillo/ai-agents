<!-- # taste-lint: ignore file-size, append-only trap index; split entries lose search locality. -->
# Gotchas

<!-- # taste-lint: ignore file-size, a trap catalog has to be readable in one
pass. Splitting it by category would make you open several files to learn what
will bite you, which is the one thing this file exists to prevent. -->

Non-obvious repository behavior that cost real time to learn and cannot be
inferred from reading the code. Each entry states the trap, the symptom you
will actually see, and the fix.

`AGENTS.md` is budget-capped because it is injected into every session. Two
byte gates disagree: `tests/test_workspace_limits.py` allows 3072 per file,
`scripts/validate_workspace_budget.py` allows 3000. **Write to 3000.** The
stricter gate binds, and a file between the two passes one and fails the other
(Refs #3951). These entries live here instead so detail is not paid for on
every turn. `AGENTS.md` points at this file from its Retrieval section, and
`.github/copilot-instructions.md` points at it from its Gotchas section.

`.github/copilot-instructions.md` is injected into every Copilot session too,
at roughly twice that per-file budget, and **no gate measures it**: the
workspace budget covers only `CLAUDE.md`, `AGENTS.md`, and `.claude/CLAUDE.md`,
and `instruction_budget.py` covers only `.github/instructions/*.instructions.md`.
New always-on guidance therefore belongs here, not there (Refs #3991).

## Four portability checkers exist and their names do not tell you the scope

Running three of them is not running the fourth. Two read scripts and two read
Markdown, and the two Markdown checkers are inverses of each other: one counts
prose references and deliberately ignores `.claude/skills/`, the other looks
for executable invocations of exactly that tree. All four live in
`scripts/validation/`, not `build/scripts/`.

| Script | Scans | Catches |
|---|---|---|
| `scripts/validation/check_vendor_portability.py` | skill scripts | code that reads an upstream-only path |
| `scripts/validation/check_skill_portability.py` | skill scripts | drift against the script baseline |
| `scripts/validation/check_skill_md_portability.py` | skill `.md`, `.claude/commands/`, `templates/agents/` | an upstream path cited in **prose** |
| `scripts/validation/check_skill_md_exec_portability.py` | skill `.md` | a bare `.claude/skills/...` script **invocation** |

Symptom: the first two pass, you commit, and the push is rejected by
`pre_pr.py` with `[FAIL] Skill Markdown Portability` naming a reference file
you just added. A new `.md` under `.claude/skills/` that cites a repo path such
as `.agents/analysis/...` starts at baseline 0 and any reference is drift.

Fix: resolve the path through the plugin or skill root, or declare it with an
HTML comment marker on its own line at the end of the file:

```text
<!-- vendor-portability: declared. <what the path is, why the file cites it,
and what a vendored install loses without it>. Issue #2050. -->
```

Both the canonical file and its `src/copilot-cli/` mirror carry the marker,
because the checker scans both trees.
## A bare directory argument to taste-lints is a silent false pass

`taste_lints.py --rules file-size <dir>` with the directory as a **positional**
argument scans **zero** files, prints "0 files scanned, no violations found",
and exits 0. That is a false pass, not a clean result: positional arguments go
into the `files` list, and a directory is not a file.

Directory scanning is supported, but only through the flag:

```
# works: 4 files scanned
uv run --frozen python .claude/skills/taste-lints/scripts/taste_lints.py \
  --rules file-size --directory .claude/skills/context-optimizer/references

# silent no-op: 0 files scanned, exit 0
uv run --frozen python .claude/skills/taste-lints/scripts/taste_lints.py \
  --rules file-size .claude/skills/context-optimizer/references
```

Also available: `--git-staged` and `--diff-scope BASE_BRANCH`. Explicit file
paths remain the safest habit, because the count in the output line is the
only thing that distinguishes a real pass from the no-op, and "no violations
found" reads identically either way.

Authored file size is a **hard error at 501 lines** and a warning from 301 to
500, so a file that silently skipped the check can block a later commit.
## Session logs validate only when present

Commits under `.agents/` do not require a session log. The `session-policy`
hook returns success when no log is staged. If a JSON log is staged, the
retained validator still rejects malformed or incomplete content.

## If you opt into a log, never record `endingCommit` and then amend

`endingCommit` must name a commit that is still reachable:
`scripts/validation/session_scope.py` runs `git merge-base --is-ancestor <sha>
HEAD`. Amending the commit that carried the log rewrites it, so the SHA you
just recorded no longer exists on the branch and the check fails.

Record the SHA of the commit carrying the work, then commit that edit as a
**follow-up commit**. A commit is its own ancestor, so naming current `HEAD`
and committing the change on top passes.

Two traps make this expensive rather than merely annoying:

- A `[PASS]` from `scripts/validate_session_json.py` does not survive an amend.
  The validator reads the SHA against the `HEAD` of the moment. Re-run it after
  any amend, not just after the first write.
- The check runs inside the push hook **after** the Python suite, which
  measured 1116 seconds on one run. A one-line metadata error therefore costs
  roughly twenty minutes to surface.

Symptom, from the push hook rather than from the standalone validator:

```text
endingCommit '<sha>' names a commit that is not an ancestor of HEAD
```

Refs #3618.

## An opted-in session log cannot name the commit that carries it

The follow-up-commit remedy above has a missing first step, and without it the
first commit of a session is unreachable.

`session-policy` runs the **full** `validate_session_json.py` at pre-commit, not
a presence check. `sessionEnd.changesCommitted` is a MUST, so it must be
Complete. Complete requires `endingCommit` to be a non-empty ancestor of `HEAD`
that differs from `startingCommit`. A log staged in the commit it describes
cannot satisfy that, because the SHA does not exist until the commit succeeds.
Every escape either fails or warns:

```text
endingCommit = <the new commit>   impossible, the SHA does not exist yet
endingCommit = HEAD               "startingCommit and endingCommit are the same"
endingCommit = ""                 WARNING (not a failure): validator warns but does not block
changesCommitted.Complete = false "Incomplete MUST: sessionEnd.changesCommitted"
```

Note: `validate_session_json.py` emits a warning (not an error) when
`endingCommit` is empty with `changesCommitted` complete. The schema permits
empty values. This means the empty-endingCommit path is not fully blocked
by tooling today; the workaround in the next paragraph still applies.

Point the log at commits that already exist. Set `endingCommit` to the session's
most recent existing commit and `startingCommit` to that commit's parent, then
advance `endingCommit` in the follow-up commit:

```bash
git rev-parse HEAD^   # -> startingCommit
git rev-parse HEAD    # -> endingCommit
```

Corollary: a session whose **first** commit touches `.agents/` has no existing
commit to name. Land one commit outside `.agents/` first, or the gate cannot be
satisfied at all.

## The same `endingCommit` error also fires when you never amended anything

The tell is that the log it validated is not yours. Do not rely on the
push-hook summary to name the SHA. It may only show the broad Session End
failure line below.

`new_pr.py --base` defaults to the **local** `main` ref, not `origin/main`, and
uses it for both the PR target and the changed-file set. A stale local `main`
makes `git diff main...HEAD` report every session log merged upstream since you
last updated it. The Session End gate then sorts that set by date and session
number and validates only the highest, which is a stranger's log, against your
branch. Its `endingCommit` is legitimately not an ancestor of your HEAD, so the
gate fails your PR for someone else's file, and prints one line with no path:

```text
Session End validation failed
```

Measured 2026-08-02 with local `main` 44 commits behind. The gate selected
`2026-08-02-session-4231-episode-corpus-migration.json` out of 19 candidates;
the branch's own log passed standalone in the same worktree.

Check staleness first, before reading any session log:

```bash
git rev-list --left-right --count main...origin/main   # non-zero right = stale
git fetch origin main:main                             # fast-forward the ref
```

The fetch is refused when `main` is checked out in a worktree. It usually is
not: the primary clone here sits on a detached HEAD, and `git worktree list`
tells you in one line.

Two reasons this is expensive. The message names neither the file it validated
nor the base it used, so the natural next move is to re-validate your own log,
which passes and sends you looking for a gate bug. And the same stale ref makes
`git diff main..HEAD` report thousands of phantom deletions, so the two symptoms
show up together and look like one catastrophic branch problem.
## Run validation with `uv run python`, never bare `python3`

`scripts/validation/checks_spec.py` shells out to child validators with
`sys.executable`. A system interpreter at the entry point therefore propagates
to every child check, and two of them fail with `ModuleNotFoundError:
markdown_it` because the dependency lives in the project venv.

Symptom: `uv run python scripts/validation/pre_pr.py` reports failures that have
nothing to do with your change. Refs #3938.
## Instruction-budget ceilings ratchet to measured size

`scripts/validation/instruction_budget.py` enforces a ceiling that was set from
the corpus as it stood, and it has been raised as the corpus grew. A passing
gate therefore says the corpus did not grow since the last ratchet. It does not
say the corpus is small.

Compare against the goal, not the ceiling. The always-on corpus is roughly 95KB
on a `.py` edit.
## Security suppression comments block commits, merges, and pushes

`git_hook_policy.py` runs the same security suppression policy at pre-commit,
pre-merge-commit, and pre-push. It blocks bare `noqa`, `noqa` lists containing
an `S` rule, file-level Ruff or Flake8 security directives, `nosec`,
`nosemgrep`, `lgtm[`, `codeql[`, and `cwe-suppress`.

Non-security `noqa` codes pass. `type: ignore` is outside this gate; issue
#4039 tracks its separate policy.

A suppression moved within one file consumes an equal removal credit. Pure
renames and rename-with-edit changes between scanned suffixes preserve that
credit. A rename from an unscanned suffix into a scanned suffix scans the full
destination file, because the suppression becomes active at that boundary.

Existing suppressions on `main` remain grandfathered unless the change makes
them newly active. Refs #3940, #4049, #4051, and #4052.
## Large branches get an advisory notice, not a block (ADR-099)

The pre-push `push-ref-policy` hook and `pr-validation.yml` used to hard-fail a
branch carrying more than 20 commits ahead of `origin/main` (40 after a
main-merge), with relief only through a human-only `commit-limit-bypass`
label. ADR-099 removed that block: the local verification step
(`scripts/validation/check_pr_bypass_label.py`, since deleted) shelled out to
`gh api`, and a Claude Code cloud session with no `gh`/API access could never
satisfy it even when the label was already correctly applied, forcing an
expensive stacked-branch-and-PR workaround (issue #5233) to route around a
verification failure that had nothing to do with the PR's merits.

A large branch still gets a `needs-split` label and a WARNING (>=10 commits)
or ALERT (>=15 commits) notice, both from `scripts/validation/pr_commit_count.py`,
but neither blocks a push or a merge. Check mid-session if you want to see it
coming:

```
git rev-list --count HEAD ^origin/main
```

Splitting a large PR is still good practice for reviewability; it is no
longer required by git.
## Never revert a source file with `git checkout` to negative-control a fix

Negative-controlling a fix means reverting the source, confirming the new tests
fail, then restoring. `git checkout <file>` restores the file to HEAD, which
silently discards **every other uncommitted change in it**, not just the one
you meant to undo. On a file carrying two unrelated in-progress fixes, one
control run destroyed both.

Copy the file aside and copy it back:

```
cp scripts/eval/thing.py /tmp/thing.bak
# ... sabotage, run the test, observe the failure ...
cp /tmp/thing.bak scripts/eval/thing.py
```

`git stash push <file>` is safe by comparison (the change is recoverable) but
still moves *all* of the file's changes, so a control run that expects only
one behavior to regress will see several.

Symptom: a control that should fail passes instead, because the sabotage never
applied to the code you thought you were editing. Check `git status` before
concluding the test is weak.
## The mypy and ruff gates are ratchets, not clean-tree checks

`git_hook_policy.py mypy` tolerates the pre-existing error count in a file and
fails only when your change adds to it. Touching a file with pre-existing
errors does not oblige you to fix them, but adding one error to a file that had
eight will fail the push with all nine printed.

Symptom: a wall of errors on lines you did not touch. Count them against the
merge base before assuming the change is yours.
## A branch behind main fails the count ratchets on a number it never touched

The count ratchets (`ruff_count_ratchet.py`, `taste_count_ratchet.py`,
`type_ignore_count_ratchet.py`) compare this tree's recorded baseline against
the baseline at `origin/main`, and the baseline may only fall. A branch that is
behind carries the older, higher value, so the gate blocks even when the branch
added nothing. The message says so itself, and cannot tell you which case you
are in, by design (issue #4066):

```text
ruff count ratchet: BASELINE ABOVE BASE. This tree records 311, origin/main
records 309 (+2). The measured count is 309, which origin/main already allows,
so nothing in this tree added a violation. The baseline may only fall. If this
branch did not edit the baseline, it is behind origin/main: merge or rebase to
pick up the lowered value. If it did raise the baseline, restore 309 and fix
the violations instead of widening the allowance.
```

Line-wrapped here; the real output is one line. The second sentence appears in
that form only when the measured count is at or below the base, which is
exactly the behind-but-innocent case.

This is a different mechanism from the per-file case above. That one is about
errors you added to one file; this one is about a repo-wide number your branch
never touched.

The cost is the wait, not the ordering. These ratchets sit in the same
`parallel: true` pre-push group as `python-tests` (`lefthook.yml`), so they do
not run after the suite, but `git push` does not return until every job in the
group finishes. A measured run put `python-tests` at 946 seconds against 2.6
seconds for `taste-count-ratchet`, so you wait out the suite to be told your
branch is behind.

Rebase before you push, or run the four gates yourself first. They take about
2 seconds:

```bash
for s in taste_count_ratchet type_ignore_count_ratchet; do
  uv run --frozen python scripts/ci/$s.py --base-ref origin/main
done
uv run --frozen --extra dev python scripts/ci/ruff_count_ratchet.py \
  --base-ref origin/main
RUFF_RATCHET_BASE_REF=origin/main \
  uv run --frozen --extra dev python scripts/ci/ruff_ratchet.py
```

A rebase can also orphan the `endingCommit` recorded in your session log.
`session_scope.py` accepts any SHA that `git merge-base --is-ancestor <sha>
HEAD` accepts, so the record breaks only when history rewrites that specific
commit. Amending `HEAD` is safe whenever the recorded commit stays reachable,
which includes `HEAD~1` and anything older. It is unsafe only when the commit
you are rewriting *is* the recorded one; there, add a follow-up commit instead.
## One file crossing 500 lines fails four pre-push jobs with three messages

`taste_lints.py` treats a file over 500 lines as an error and a file over 300
as a warning. Only the error counts. Growing one file from 402 to 691 lines
raised the whole-repo taste count by exactly one, and that single increment
failed four jobs in the same push:

| Job | What it printed |
|---|---|
| `taste-count-ratchet` | `REGRESSION. 585 > baseline 584 (+1)` |
| `merge-tree-ratchet` | `BLOCKED. The merged result breaches a ratchet ceiling.` |
| `pre-pr-validation` | `Error: Validation failed`, after 500-plus lines of unrelated file-size output |
| `python-tests` | `FAILED tests/ci/test_count_ratchet_against_real_git.py::test_the_shipped_baseline_matches_the_tracked_tree` |

The fourth is the trap. It reads as an unrelated test failure buried in 23,058
passes, and it is the one that costs you the 16-minute suite before you see it.
All four clear together once the count returns to baseline.

`merge-tree-ratchet`'s advice is also wrong for this case. It says to merge or
rebase from `origin/main` and re-check, which is right for the behind-but-innocent
case above and useless when the regression is genuinely yours. That job already
computed the merged result, so if it still says `REGRESSION`, merging will not
help. Read the number: `585 > baseline 584` means your tree added one.

Find the offending file directly rather than by bisecting the push:

```bash
uv run --frozen python .claude/skills/taste-lints/scripts/taste_lints.py <changed files>
```

Note the path. The linter is not under `scripts/validation/`; it ships inside
the `taste-lints` skill, which is where the plugin needs it.

The fix is usually a split rather than a suppression. A test file that grew by
appending a second, self-contained group of guards splits cleanly on the
document or subject each group covers, and the halves keep the shared helpers
by import rather than by copy. Confirm with the real gate before pushing again,
which takes seconds against the suite's sixteen minutes:

```bash
git add <the split files>
uv run --frozen python scripts/ci/taste_count_ratchet.py
```

It reads `git ls-files`, so an unstaged new file is invisible to it and the
count looks fine right up until the push.

## A green pytest run is not a green push

The pre-push hook runs roughly twenty jobs and pytest is one of them. A branch
can pass every test and still be rejected by gates pytest never executes.

Measured on one branch after a clean local run of 23,693 passed, 0 failed:

```
✔️ hook-anchoring-e2e   ✔️ plugin-load-e2e   ✔️ python-tests
🥊 type-ignore-count-ratchet   🥊 python-type-check   🥊 merge-tree-ratchet
🥊 workflow-local-run          🥊 pre-pr-validation
error: failed to push some refs
```

The `python-type-check` failure was four trivial mypy errors in that branch's
own new test files, three unguarded `re.match(...).group()` calls and one
unparameterized `CompletedProcess`. No test could have caught them, because a
passing test does not type-check itself.

The cost is asymmetric. A rejected push takes about eleven minutes and
truncates the failing gate's output, so it tells you **less** than running that
gate directly. `python-type-check` above failed in 1.30 seconds.

Verify against the gate set. `lefthook.yml` is the source of truth for how each
job is invoked; do not invent invocations. The two cheapest and most commonly
missed:

```
FILES=$(git diff --name-only origin/main -- '*.py' | tr '\n' ' ')
uv run --frozen python scripts/validation/git_hook_policy.py mypy $FILES
uv run --frozen python scripts/validation/pre_pr.py
```

The mypy gate refuses a bare invocation with `run_mypy called with no file
arguments; refusing (bare mypy is a false green)`. That is correct behavior,
not a broken gate; pass the changed-file list.

When delegating, "run the full suite and confirm green" is insufficient and
will produce a rejected push. Name the gate set.

## A staged file in the shared checkout fakes a red main

Whole-tree ratchets measure the tracked tree, and the tracked tree includes
staged-but-uncommitted files. A `git add` that was never committed is invisible
to `git log`, to `git diff HEAD` without `--cached`, and to a HEAD versus
`origin/main` comparison, yet it moves the measurement.

Measured: `tests/ci/test_count_ratchet_against_real_git.py` failed on a
checkout whose HEAD was byte-identical to `origin/main`:

```
taste_count_baseline.txt: baseline is 583 but the tree measures 587:
4 violation(s) were added. Remove them rather than raising the baseline.
```

`git status --porcelain | grep -v '^??'` returned 68 staged additions left by
another agent. After `git restore --staged .`, the same test returned
`12 passed`. Main was green throughout.

Check the index before believing any whole-tree ratchet failure. Untracked
(`??`) entries are usually harmless; staged entries are not. Clear them with
`git restore --staged .`, which preserves the files. Never `git checkout` them,
they may be someone else's work.

## `core.bare=true` appears in `.git/config` and breaks every worktree

Something during `git push` writes `core.bare = true` into the shared
`.git/config`. A bare repository cannot have work trees, so every git command
needing one fails:

```
fatal: this operation must be run in a work tree
```

Measured twice in one session. It broke the main checkout and three of five
linked worktrees simultaneously, and it surfaced as four unrelated-looking
failures: two portability checks in the pre-PR gate, a lefthook integration
test, and plain `git status` inside a worktree. Three separate wrong diagnoses
were attempted before the shared cause was found, including one issue filed and
retracted.

A serial `pytest tests/` run does **not** reproduce it, so the trigger involves
the parallel pre-push stage rather than the suite alone.

Repair: `git config core.bare false`.

Immunize, so a mid-run flip cannot break you. This repository sets
`extensions.worktreeConfig = true`, which makes `core.bare` worktree-specific,
and worktree config wins over shared config:

```
git config --worktree core.bare false          # in the main checkout
git -C <each linked worktree> config --worktree core.bare false
```

Verified by setting the shared value to `true` afterwards: all six worktrees
kept working.

Consequence worth internalizing: **the pre-push hook can corrupt the repository
it is validating**, so a rejected push is not by itself evidence that the branch
is bad. Check `git config core.bare` before believing a push failure, and
re-verify against a repaired repository before attributing anything to your
change. Tracked in issue #4698.

## When several unrelated checks fail at once, suspect the substrate

The `core.bare` incident above produced four plausible and independent-looking
diagnoses, each of which invited its own investigation. All four were one cause.

A related trap: comparing two runs that differ in more than one variable. A
test that passed in three full-suite runs and failed when run alone looked
order-dependent. Those runs differed in **time**, not ordering, and the config
was corrupted in between. The order-dependence issue was filed and had to be
closed as invalid.

Before attributing several simultaneous failures to several causes, check the
shared substrate: `git config core.bare`, `git status --porcelain` for staged
entries, and `git rev-list --count HEAD..origin/main` for staleness.



## Eval harness

These matter only when running `scripts/eval/`. Full detail lives in
`.claude/skills/context-optimizer/references/rule-audit-procedure.md`.

- Run without an API key using `EVAL_PROVIDER=copilot-cli`. The provider must
  run in an empty working directory, because the Copilot CLI loads `AGENTS.md`,
  `CLAUDE.md`, and `.github/instructions/**` from its cwd and would otherwise
  put the treatment into the control cell.
- Copilot CLI reported token counts are non-monotonic (109k from `/tmp` against
  96k in-repo for the same trivial prompt). They are not a measurement of
  anything. Use `instruction_budget.py`. Refs #3906.
- A single eval run cannot resolve a delta under about 1.0 on a 0-5 scale.
  Measured run-to-run spread on identical inputs was 0.94 on Opus 5 and 1.11 on
  Sol 5.6. Run four times per model and count sign consistency, not means.
## The PR description gate blocks on paths and on dashes

`scripts/validation/pr_description.py --ci` runs as `PR Validation / Validate
PR` in branch protection and blocks merge on two things.

**A file path mentioned but not in the diff.** The validator extracts paths
only from inline code, bold, list items, and Markdown links, so a path in plain
prose is fine but an inline-backtick mention is not. Silence a genuine
reference the way the validator recognizes: a citation cue, a fenced code
block, a GitHub admonition (`> [!NOTE]`), or a contextual H2 such as
`## References`, `## Related Files`, `## See Also`, `## Notes`,
`## Background`, `## Evidence`, `## Out of Scope`, or `## Prior Art`. The full
set is `_CONTEXTUAL_SECTION_NAMES` and `_REFERENCE_SECTION_PREFIXES` in the
validator.

A citation cue is narrower than it looks, and both constraints are
load-bearing. The cue (`see`, `per`, `defined in`, `for example`, and the rest
of `_INLINE_CITATION_PATTERN`) must sit on the same line and immediately
before the path, separated only by whitespace, colons, or an open paren. And
the backtick span must end at the extension: `` `taste_lints.py` `` is
suppressible, `` `taste_lints.py --rules file-size` `` is not, because the
trailing flags push the closing backtick past the extension. Reword so the
path stands alone in its own span.

Do not guess at the shape and push to find out. The extractor imports and runs
offline against a candidate body, which turns a round trip through CI into a
one-second check:

```python
import importlib.util, sys, pathlib
spec = importlib.util.spec_from_file_location("prd", "scripts/validation/pr_description.py")
m = importlib.util.module_from_spec(spec)
sys.modules["prd"] = m  # dataclass resolution needs the module registered
spec.loader.exec_module(m)
print(sorted(m.extract_mentioned_files(pathlib.Path(sys.argv[1]).read_text())))
```

Anything it prints that is not in the diff is a CRITICAL waiting to happen.

**Any em-dash (U+2014) or en-dash (U+2013).** Byte-verify rather than trusting
a visual scan:

```
python3 -c "import sys;d=open(sys.argv[1],'rb').read();print(sum(d.count(c.encode()) for c in ('\u2014','\u2013')))" body.md
```

Editing the body re-triggers the gate on `pull_request: edited`, so no new
commit is needed. Bot reviewers produce false positives on both checks; verify
at byte level before editing.

The validator takes `--pr-number` and fetches the **live** body, so push and
update the PR before running it locally.
## Spec coverage blocks when the PR body has no checked acceptance boxes

`Validate Spec Coverage` fails with this, and the reason names a rule rather
than a missing file, so it reads like an infrastructure fault. Its wrapper
`scripts/quality_gate/spec_external_signal_gate.py` always passes `--json` to
the aggregator, so grep the quoted keys, not a prose line. (Running
`gate_aggregator.py` by hand without `--json` does print prose, which is why
the prose form looks plausible and never appears in CI.)

```text
  "verdict": "NEEDS_REVIEW",
  "reason": "closed-loop:external-signal-inconclusive",
```

The cause is a missing section in **the PR body**, not the issue.
`scripts/external_signals/gate_aggregator.py` requires at least one signal of
kind `external` whose verdict is passing or warning. The only external signal
is `acceptance-criteria`, which
`scripts/quality_gate/spec_external_signal_gate.py` parses out of
`PR_BODY_FILE`. All boxes checked gives PASS, any box unchecked gives FAIL, and
**no section at all gives UNKNOWN**, which empties the external list and
blocks. The other two signals come from the model, and two readings from one
model are one measurement, so the gate is right to refuse them alone.

Two parsing constraints, both in `scripts/external_signals/acceptance_criteria.py`:

- The heading must match `^#{1,6}\s*acceptance(\s+criteria)?\s*$`.
- Items must be `- [x]` task-list checkboxes. **A numbered list does not
  parse**, so copying an issue's `1.` through `5.` criteria verbatim still
  yields UNKNOWN.

Reproduce and fix offline rather than pushing to find out. This runs the real
gate and replaces a CI cycle with one second:

```bash
gh pr view "$PR" --json body --jq .body > body.md
PR_BODY_FILE=body.md TRACE_VERDICT=PASS COMPLETENESS_VERDICT=PARTIAL \
  uv run --frozen python scripts/quality_gate/spec_external_signal_gate.py
```

Exit 0 means PASS or WARN. Editing the body re-triggers the gate, so no new
commit is needed.

**Do not read the PR comment to find out whether this passed.** The
`AI-SPEC-VALIDATION` comment is posted once and never updated, so it keeps
showing the first run's verdict. A red check can display `Final Verdict: PASS`
indefinitely. Read the job log instead, and note that `gh run view
--log-failed` returns only cleanup noise for this job:

```bash
gh run view --job "$JOB_ID" --log | sed 's/\x1b\[[0-9;]*m//g' | grep -P 'VERDICT|"verdict"|"reason"'
```

Refs #4369 for the stale comment defect.
## Never put a literal pipe inside a Markdown table cell

Escape it as `\|` or reword. A bare `|` breaks rendering and trips bot
table-format flags.
## Reference skill scripts by plugin root, not a bare `.claude/` path

Use `"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/..."`. A
bare `.claude/skills/...` path fails under Copilot CLI and trips
`check_skill_md_exec_portability.py`.
## `gh pr view --json reviewThreads` is not a valid field

The field does not exist on that command and the error does not suggest the
alternative. Use `gh api graphql` with a `reviewThreads` query on the pull
request instead.
## Workspace byte-gate

Moved to `.agents/governance/WORKSPACE-BUDGET.md`: per-file ceilings, the
shared total, the silent-disable failure, and where the gate lives.
## Concurrent pushes: use a per-branch lock, not a global one

The race a push lock exists to prevent is a lost ref update: two writers push
to the same remote ref and one overwrites the other. Git takes its lock per ref.
Two pushes to two different branches cannot race for the same lock on the server.

A single global lock wrapping `git push` serializes the entire fleet including
the 7 to 15 minute pre-push hook. Five concurrent pushes to five distinct
branches costs 5 x 15 = 75 minutes instead of 15.

Use the canonical per-branch lock, keyed on the exact branch name. The path is
fixed by `.claude/rules/push-lock.md` and `scripts/validation/check_push_lock_paths.py`
blocks any other spelling:

```bash
BR=$(git branch --show-current)
SLUG=$(printf '%s' "$BR" | tr '/' '-')
mkdir -p "$HOME/src/scratch/locks"
flock "$HOME/src/scratch/locks/push-lock-$SLUG.lock" \
  git push origin HEAD:"$BR"
```

Notes:
- `tr '/' '-'` is required: a branch like `fix/foo` would otherwise create a
  lock file with a `/` in its name, which the shell reads as a directory path.
- `mkdir -p` first. `flock` fails when the parent directory is missing, and a
  failed `flock` in a detached push says nothing.
- Keep the lock outside `/tmp`. A wipe there splits one filename across two
  inodes, and the two holders stop excluding each other (issue #4366).
- The lock prevents the git-object-packing overhead of a concurrent same-branch
  push. It is not a substitute for the pre-push non-fast-forward guard, and a
  force push stays forbidden on a shared branch (issue #4293).
- Two distinct branches never contend for the same lock file, so their pre-push
  hooks run in parallel. Measured throughput: four concurrent pushes to four
  distinct branches finish in approximately one hook duration, not four.

Issue #4283 documents the measured 28-waiter convoy produced by the global lock
and the first-principles analysis of why the race is per-ref.

## A push that fails only on `plugin-load-e2e` is the GitHub rate limit

`plugin-load-e2e` probes Copilot auth. When the shared GitHub GraphQL budget is
exhausted, the probe reports the refusal as an empty or rejected auth token
rather than as a rate limit, so the push fails on a message that names the wrong
cause. Every other gate stays green.

The discriminator is the skip guard. The test **skips** when no token
environment variable is set and **fails** when a token path exists but the probe
call errors. So a hard failure means the token was found and the call was
refused, not that the token is missing.

Confirm before re-diagnosing anything:

```bash
grep -aoE "🥊 [a-z0-9-]+ \([0-9.]+ seconds\)" push.log | sort -u
gh api rate_limit --jq '.resources.graphql.remaining'
```

One failed gate named `plugin-load-e2e` plus a remaining count near zero is the
rate limit. Wait for the reset and retry the identical push; do not change the
branch, the base, or the gate.

This bites hardest with several agents or worktrees running at once, because
they share one user-scoped budget. N concurrent workers exhaust it and then
**all** of them fail this one gate, so the failure rate rises with the very
parallelism it blocks. Before a batch of GitHub calls, check the remaining
budget and do local work while it is under 500. Prefer one batched
`gh issue list --json` or `gh pr list --json` over per-item `gh issue view`
calls: fourteen sequential views triggered the secondary limit where a single
batched list did not. Refs #4504.

## Run the gate itself, never an approximation of it

`ruff check .` walks untracked scratch files and any nested worktree under the
repo root. `ruff_count_ratchet.py` scopes to git-**tracked** files. The two
numbers differ, and the ratchet's own docstring records a local `.` run
inflating to 767 against a real 361.

Symptom: a count that does not match what the gate prints, leading you to
diagnose a regression that the gate does not see, or to miss one it does. A
measured instance: the approximation said 142 while the gate said 140.

Run the gate's own entry point and read its number. This applies to every count
ratchet, not only ruff.

Two related traps:

- `ruff check --select RUF100 --fix` deletes every `noqa` in the repository.
  `--select` replaces the project rule set, so every other rule becomes
  non-enabled and every suppression for it reads as unused. Use `--fixable
  RUF100` instead, which keeps the configured select list intact.
- RUF100 distinguishes `unused:` from `non-enabled:`. A wall of `non-enabled:`
  means the `noqa` names a rule absent from the select list, which points at a
  configuration or version change rather than at new code.
## A script under `scripts/ci/` needs a workflow caller, not just a lefthook job

`tests/ci/test_ci_scripts_are_wired.py` parses `.github/workflows/**` and
`.github/actions/**`, reads the `run:` body of every step that is not literally
`if: false`, and fails for any `scripts/ci/*.py` it cannot find a live call for.
Registering a new guard in `lefthook.yml` and in
`scripts/validation/checks_ratchet.py` satisfies the push gate and the pre-PR
gate, and still fails this test. Local hooks do not cover a push from a clone
where `lefthook install` never ran, a bot push, or a cloud agent.

The test exists because `ruff_count_ratchet.py` and `adr006_run_block_scanner.py`
both shipped with green suites and no caller, and protected nothing for weeks
(issue #3329). A unit test cannot catch a missing call site, so this checks the
call site.

Add the workflow step in the same change that adds the script. A ratchet with a
fixed floor takes no `--base-ref` and needs no `git fetch --depth=1` preamble;
copy the neighbouring step only if your guard actually diffs against a base.
## An autofix is not a gate: pair every repair with a verifier

`memory-token-update` (`lefthook.yml`) rewrites every `.serena/memories/`
token count on pre-commit, and it is correct. It carries
`skip: [merge, "test $SKIP_AUTOFIX = 1"]`, and nothing downstream checked its
result, so a memory edited inside a merge commit reached `main` with the old
count still recorded. Measured on pristine `main`: `skills-git-index` read 287
against an actual 324, a 13% undercount (issue #4441).

Two rules follow, and both are load-bearing:

- **The verifier must reuse the repair's own computation.** If the gate derives
  the expected value independently, the two can disagree, and the contributor is
  trapped: the gate fails, they run the repair, the gate fails again on the
  repaired file. `memory_index_token_ratchet.drifted_lines` calls the repair's
  `update_line` directly for exactly this reason.
- **"Cannot verify" must not exit zero.** The repair degrades to a warning when
  `tiktoken` is missing. The verifier exits 2 instead. A gate that goes green
  because it checked nothing is worse than no gate.
## Grep the handler, not the job name

A lefthook job name, its `git_hook_policy.py` subcommand string, and the Python
function that implements it are three different identifiers. For the memory
token repair they are `memory-token-update`, `memory-tokens`, and
`update_memory_tokens`. Searching one spelling and finding nothing produces a
confident, wrong "this is wired to no gate" conclusion. That mistake cost a full
diagnostic cycle on issue #4441.

Correct probe: `git grep -n "<function_name>"` to find the handler, read the
`(subcommand, handler)` tuple near it, then grep that subcommand string in
`lefthook.yml`.
## "All validations passed" in a push log does not mean the branch reached the remote

The repo's push wrapper runs `scripts/validation/pre_pr.py` first, and that
script signs off with `RESULT: All validations passed` followed by
`Ready to create pull request!`. Only then does it call `git push`, which fires
the lefthook `pre-push` hook and runs the full suite a second time. Those two
lines are therefore the *earliest* success message in the log, not the last one,
and a log that ends on them usually means the push is still running.

Two consequences:

- Grepping the log for lefthook failures (`🥊 <job> (N seconds)`) and finding
  none proves no job has failed **yet**. It does not prove the push finished.
- The only proof a push landed is the remote itself:
  `git ls-remote origin <branch>` against `git rev-parse HEAD`. Check the shas
  match before opening a PR. Opening one against a branch the remote has never
  heard of fails with a confusing 422 that names the base, not the head.

Whether a commit made while a push is in flight lands with it is not
predictable from the outside. The wrapper runs `pre_pr.py` first and only then
calls `git push`, so a commit created during that window can be picked up, and
one created after the transfer starts will not be. Measured both ways. Do not
reason about it: read the sha off the remote and compare.
## Never measure a gate from a detached HEAD

`scripts/detect_scope_explosion.py` returns 0 on a detached `HEAD` for staged
content that returns 1 on a branch. Same commit, same staged files, same tree;
the only variable is whether `HEAD` is attached. It does not report that it
skipped, it reports success (issue #4602).

The direct cost is that `git bisect`, `git worktree add --detach`, a CI checkout
of a SHA, and a rebase in progress all detach, so committing from any of those
states skips the gate with no signal.

The larger cost is to measurement. A probe run detached reports PASS on input the
gate blocks, so the obvious way to test this check yields a false negative. That
is how issue #4544 came to be closed as already-fixed while still reproducing,
and the retraction had to be retracted. When you probe any gate, attach `HEAD`
first with `git checkout -B probe/<name> <sha>` rather than
`git worktree add --detach`, and treat a detached PASS as no result at all.
## The CLI e2e pre-push jobs need a Copilot token, and fail fast without one

`plugin-load-e2e` and `hook-anchoring-e2e` shell out to the real `copilot`
binary. Each has its own `glob:` list in `lefthook.yml`, and the two lists are
different: `hook-anchoring-e2e` watches the hook surface (`.claude/hooks/**`,
`src/copilot-cli/hooks/**`, `.claude/settings.json`, `generate_hooks.py`, and
its own e2e files), while `plugin-load-e2e` watches the plugin surface
(`.claude/skills/**`, `.claude/commands/**`, both `plugin.json` manifests,
`src/copilot-cli/skills/**`, `generate_commands.py`, `generate_skills.py`,
`templates/platforms/copilot-cli.yaml`). Read `lefthook.yml` for the current
lists rather than trusting a union of them; touching one surface arms one job,
not both.

The CLI reads its credential from `COPILOT_GITHUB_TOKEN`, `GH_TOKEN`, or
`GITHUB_TOKEN`. A `gh auth login` alone does not set any of them. With none set,
each invocation exits 1 with an authentication message and the job finishes in
roughly 13 to 17 seconds. A run that actually reaches the CLI takes about 28
seconds or more for two tests.

Both jobs are siblings of `python-tests` inside one `parallel: true` group, so
they race it rather than follow it. That does not make the failure cheap: the
group only returns when its slowest member does, and `python-tests` takes about
18 minutes. A 13-second auth failure still costs the full suite's wall time
before the ref is rejected. Provision the token on the push instead:

```bash
COPILOT_GITHUB_TOKEN="$(gh auth token)" git push origin HEAD:"$(git branch --show-current)"
```

### Merging main arms both jobs even when your branch touches neither surface

This is the part that reads as a contradiction. A branch can arm both e2e jobs
while `git diff origin/main...HEAD` shows nothing in either glob list. The globs
are not matched against the branch's diff versus main. Lefthook expands
`{push_files}` over the **push range**, from the remote tip of the branch to the
new `HEAD`. Merging `origin/main` into a branch puts every one of main's commits
inside that range.

Measured: pushing `test/vacuous-assertion-anti-pattern` right after merging main
covered 367 files across `6eeeb8cac..35d87fd6b`, which hit both glob sets. The
branch's own diff against main touched seven files, none of them gated. So the
rule is: if you merged main, assume every glob-gated job is armed, whatever your
branch changed.

Two traps around diagnosing it:

- A fast finish looks like a flake or a concurrency problem. It is neither. Read
  the assertion message, which names `COPILOT_GITHUB_TOKEN` outright.
  Serializing pushes to fix it is the wrong remedy and contradicts the
  per-branch lock section above.
- Running the two test files directly does not reproduce the failure. The suites
  gate on `RUN_CLI_E2E=1`, which `scripts/validation/git_hook_policy.py` sets for
  the hook. Without it the CLI cases skip and pytest reports the file as passing,
  which proves nothing. Set both variables to reproduce.

A third failure mode reads like the first two and is not. When the service
rejects a token that is actually valid, the test fails with "Copilot auth token
was rejected (expired or revoked); rotate COPILOT_GITHUB_TOKEN". That message
names one cause and the service's own text in the same output contradicts it:
"Your token may still be valid. Check your network connection and try again."
Measured: a push failed both e2e jobs on that message, and the same test passed
in 24.99 seconds a few minutes later with a token from the same `gh auth token`
call. Reproduce before rotating anything:

```bash
RUN_CLI_E2E=1 COPILOT_GITHUB_TOKEN="$(gh auth token)" \
  uv run --frozen python -m pytest \
  tests/e2e/test_plugin_load_smoke.py::test_copilot_plugin_loads_expected_skills -q
```

That is 25 seconds against 18 minutes for a push, and it tells you whether you
have a credential problem or a bad minute.

Measured on that same push: `plugin-load-e2e` failed at 13.03 seconds and
`hook-anchoring-e2e` at 16.73 seconds, while `python-tests` passed in 1071.94
seconds. The same two tests passed in 27.92 seconds under `RUN_CLI_E2E=1` with
`COPILOT_GITHUB_TOKEN` set, and skipped silently with the token set but
`RUN_CLI_E2E` unset. Those four durations are author-reported from the push
console; no log artifact is committed.
## Editing any `.claude/rules/*.md` file changes a number the doctrine asserts

`model-context-doctrine.md` states the shipped plugin tree's always-on size as
a literal byte count, and `tests/validation/test_always_on_corpus_claims.py`
measures the tree and asserts the prose matches. Editing a rule changes that
measurement, so a one-paragraph clarification to an unrelated rule turns the
guard red.

The trap is where it fires. The guard lives in `python-tests`, so it costs the
full suite before the ref is rejected. Nothing in the pre-commit set catches
it, and the edit itself looks unrelated to any figure.

Four rules are narrowly scoped in `.github/instructions` and always-on in the
plugin tree: `governance`, `push-lock`, `secret-redaction`, and `session-logs`.
Editing one of those moves the plugin figure while leaving the
`.github/instructions` figure alone, which is why the two numbers in that
paragraph drift independently.

Check it in under a second before pushing:

```bash
uv run --frozen python -m pytest tests/validation/test_always_on_corpus_claims.py -q
```

When it fails, take the measured value from the assertion message, update the
sentence in `.claude/skills/context-optimizer/references/model-context-doctrine.md`,
and rerun `build/scripts/generate_skills.py` so the `src/copilot-cli/` mirror
matches. Update the vendor-cost figure in the same sentence: it is the plugin
count minus the `.github/instructions` count, and no test checks it.

Two details the failure output does not explain. The at-source total is larger
than the shipped total because `generate_rules.py` strips the `priority:` key on
the way out, so the same rule is smaller in the plugin tree than on disk. And the
two 8KB multipliers move independently: the `.py`-edit multiplier can hold steady
while the always-on one shifts, so re-measure both rather than assuming one
tracks the other.
## An empty `endingCommit` breaks the episode store on the next push

The pre-commit hook extracts an episode from every staged session log. It reads
`files_changed` from the staged diff, but `commits` from the SHAs the log names,
and a first commit has none: the commit being created has no SHA yet, and
`endingCommit` is still `""`. The episode therefore ships with `commits: 0`
beside a non-zero `files_changed`, which is exactly the pair
`validate_metrics_consistency` rejects.

Nothing fails at commit time. The push fails, minutes later, in the full suite:

```text
tests/skills/memory/test_extract_session_episode.py::
  TestValidateModeRejectsUnusableEventIds::test_the_committed_episode_store_is_clean
AssertionError: metrics violations grew to 22 (was 21); new episodes with
commits==0 but metrics.files_changed>0 must be fixed
```

That count is a ratchet, so raising it is not the fix. Record the SHA and let
the extractor derive the number, which is what it is built to do:

```bash
# set "endingCommit" in the session log to the commit you just made, then
uv run --frozen python .claude/skills/memory/scripts/extract_session_episode.py \
  .agents/sessions/<log>.json --preserve
```

`--preserve` recomputes `metrics.commits` from the commit-event stream, so the
value stays derived rather than hand-set. Commit the log and the regenerated
episode together as the follow-up commit the section above already requires.

This trap applies only when a contributor opts into a session log. Governance
and architecture changes do not create logs or episodes by default.
## Two green PRs can merge into a red main, and the count ratchets will not warn

The count ratchets compare one scalar baseline against a count taken over the
whole tree. Neither number is scoped to your diff, so the gate cannot tell
"this branch added a violation" from "this branch lowered the allowance while
somebody else added one." Each PR is measured only against the baseline in
force while it is open.

That leaves a race. On 2026-08-03, PR #4476 lowered the taste baseline from 596
to 595 after removing a violation. PR #4414 grew `.agents/governance/GOTCHAS.md`
past the 500-line ceiling, adding one. Both were green. Both merged. `main`
went red at 596 against a baseline of 595, and neither author did anything
wrong.

This is a different failure from the branch-behind case above. There the branch
is stale and merging main fixes it. Here main itself is broken, so merging main
*imports* the failure. Every branch that syncs afterward fails a gate it never
touched, and the message reads the same in both cases.

Two consequences worth knowing before you spend an hour on it:

Measure main before blaming your branch. A pristine worktree at `origin/main`
answers this in seconds and is the only way to tell the two cases apart:

```bash
git worktree add --detach <path> origin/main
cd <path> && uv run --frozen python scripts/ci/taste_count_ratchet.py
```

And the usual "diff my per-file counts against `origin/main`" recipe returns
nothing when main is the thing that is red, because your branch and main are
both at the higher number. Diff against the commit that last wrote the baseline
file instead:

```bash
git log -1 --format=%h -- scripts/ci/taste_count_baseline.txt
```

Check out that commit in a detached worktree and diff its violation list
against HEAD's. The offender is the one net-new entry.
## Deleting code turns main red on the taste-count baseline

The taste ratchet script passes on `count <= baseline`, so removing a violation
looks free. A separate test does not:
`tests/ci/test_count_ratchet_against_real_git.py::test_the_shipped_baseline_matches_the_tracked_tree`
asserts `count == baseline` exactly, because a baseline above the real count is
dead allowance that lets violations creep back in unnoticed.

The consequence is counter-intuitive and it has already landed on main twice.
Anyone who deletes code, or adds a `taste-lint: ignore` directive, lowers the
count and must lower `scripts/ci/taste_count_baseline.txt` in the same commit.
Nobody expects a deletion to require a lint-baseline edit, and the pre-push
ratchet stays green while it happens, so the failure surfaces only in the full
suite after the merge.

Measured on this repository:

| Commit | Count | Baseline | Exact-match test |
|---|---|---|---|
| `a355a9e27^` | 594 | 595 | red |
| `a355a9e27` (#4428, added an ignore and lowered the baseline) | 593 | 593 | green |
| `ad61b51c4` (#4101, deleted a recovery path) | 592 | 593 | red |

Check before you push with
`uv run --frozen python scripts/ci/taste_count_ratchet.py`. It prints
`OK (count == baseline N)` when the two agree and `OK. N violations <= baseline M`
when they do not, and only the first form passes the test. Raising a baseline to
clear a blocked push is still prohibited; this is the opposite direction.


## Built-in `explore` and `research` subagent types cannot write anything

The harness `task` tool offers agent types named `explore` and `research`.
These are Copilot CLI product configuration, not anything this repository
ships. They are read-only by design: no Bash, no session-state writes, no raw
`gh`, no GitHub issue or pull request API.

Nothing in this repository configures them, which is easy to confirm and worth
confirming, because the names collide with things this repository does own:

```bash
grep -rl '"explore"' --include=*.json --include=*.md --include=*.yaml .
```

Zero hits outside session logs. The repository-owned `/research` command and
the `analyst` agent are separate and do have execution tools. The names match;
the capabilities do not.

The failure mode is quiet. A fleet run assigns these types work that
structurally cannot succeed, and the agents report back plausibly about what
they would have done. Measured this session: sixteen triage agents dispatched
as read-only types were told to record findings and update tracking state.
None could. The work had to be rerouted, and nothing in the transcript said
"permission denied," so the loss looked like agents being unhelpful rather
than agents being unable.

Use these types for reading and reporting only. Anything that must write a
file, run a command, touch session state, or call the GitHub API needs
`general-purpose` or a repository-owned agent. If a dispatched agent's
deliverable is a change rather than an answer, it is the wrong type.

Refs #4692.
## A count ratchet script can report OK on a tree its own test rejects

The four commands above answer "did this branch add violations". They do not
answer "does this tree pass the ratchet's tests", and the two can disagree.

`scripts/ci/taste_count_ratchet.py` passes when `actual <= baseline`. The test
the same ratchet ships,
`tests/ci/test_count_ratchet_against_real_git.py::test_the_shipped_baseline_matches_the_tracked_tree`,
requires `actual == baseline`. Any slack satisfies the script and fails the
test. Measured on a pristine `origin/main` worktree:

```text
$ uv run --frozen python scripts/ci/taste_count_ratchet.py --base-ref origin/main
taste count ratchet: OK. 594 violations <= baseline 595 (-1 slack).

$ uv run --frozen python -m pytest tests/ci/test_count_ratchet_against_real_git.py -q
AssertionError: baseline is 595 but current tree has 594 violations
assert 594 == 595
1 failed, 11 passed
```

Both statements are about the same tree at the same commit. The script exits 0.

The exact-equality is deliberate. From the test's docstring: "A baseline above
the real count is dead allowance: violations could be added up to the gap
without the gate noticing." A ratchet carrying slack is not a ratchet, so the
number has to be true, not merely not-exceeded.

**Symptom.** `git push` fails on `test_the_shipped_baseline_matches_the_tracked_tree`
after the ratchet scripts all printed OK. Nothing in your diff is implicated,
and the failure reproduces on a detached worktree at `origin/main`.

**Why it recurs.** Lowering a violation count and lowering the baseline are two
edits that usually live in different pull requests. Each is green against its
own base, and they meet for the first time on main. That is the merge race in
issue #3755, whose thesis was that
`strict_required_status_checks_policy: false` let a green check describe a tree
that no longer existed. That remedy shipped as `true` on 2026-08-04 but has
since been returned to `false` (measured 2026-08-15). The count ratchets block
a behind branch only when main lowers a relevant baseline; they do not enforce
universal freshness.

What remains is the case neither strict nor the ratchets cover. Ruleset
11104075 still has no `merge_queue` rule and no workflow handles a
`merge_group` event, so admission is serialized only by the one-front landing
protocol (see `docs/landing-workflow.md`), not by testing the combined result
before the merge. The exact-equality assertion above is therefore the gate that
still catches a baseline and a count arriving out of step, and it fires locally
on a tree nobody's diff touched.

**Fix.** Set `scripts/ci/taste_count_baseline.txt` to the count your tree
actually measures, in the same commit that moves the count. Lowering a baseline
to match a genuine improvement is required. Raising one to absorb a regression
is forbidden (`.github/instructions/ci-scripts.instructions.md`, MUST NOT 4);
the sanctioned escape for a file you cannot shrink is a reasoned
`# taste-lint: ignore <rule>` comment inside the first 10 lines.

**Check the test, not the script**, before any push that touches file sizes:

```bash
uv run --frozen python -m pytest tests/ci/test_count_ratchet_against_real_git.py -q
```

Three seconds. Failing on your branch *and* on a pristine `origin/main` worktree
means main is red and it is not yours to fix.
## Merging main clears an inherited red; check that before debugging your diff

A pre-push failure in tests your change never touched is usually a stale base,
not a bug. Merge main first, then re-run just those tests. Measured on a branch
whose diff was four files and none of them Python:

```text
before:  7 failures across test_always_on_corpus_claims.py,
         test_pr_validation_workflow.py, test_mutation_harness_ciperms.py
         (a full pre-push cycle, ~20 minutes, to discover them)

$ git fetch origin main && git merge origin/main --no-edit

after:   113 passed, 0 failed
```

The diff did not change between those two runs. All seven failures were
stale-base artifacts: main had moved two commits ahead, and those commits
changed the measured figures the corpus tests assert against.

Do this before opening a debugger, and do it locally rather than through a
push:

```bash
git fetch origin main && git merge origin/main --no-edit
uv run --frozen python -m pytest <only the failing tests> -q
```

If they still fail, only then is it yours. To tell "my diff" from "main is
red", run the same tests on a detached worktree at `origin/main`:

```bash
git worktree add --detach ../ai-agents-pristine origin/main
```

Failing there too means it is not your branch. This costs seconds; a push cycle
costs about 20 minutes, because `git push` does not return until every job in
the parallel pre-push group finishes.
## A merged commit's file count says nothing about the local commit gate

The repository is squash-merge only (`allow_merge_commit: false`,
`allow_rebase_merge: false`, `allow_squash_merge: true`), and every commit on
main is single-parent. So a commit on main is a squash of a whole pull request,
built by GitHub server-side, and the local pre-commit hooks never ran on it.

This matters when you are reasoning about
`MAX_AUTHORED_FILES_PER_COMMIT = 5` in `scripts/validation/git_hook_policy.py`.
`git log` on main shows commits touching 43 and 71 files, including ones
authored after that gate landed. Those are not evidence the gate is broken,
bypassed, or unsatisfiable. They are squashes.

The gate applies to the commits you make locally, and a mirrored-library change
does fit: split it by concern into 3-file commits, the shared library plus its
two mirrors, then each consumer plus its mirror plus its test.

Before citing repository history as evidence about any pre-commit or pre-push
gate, check the merge strategy. Under squash-merge, main's history records what
GitHub built, not what any hook ever inspected.

## The semgrep check in CI cannot be reproduced by the semgrep CLI

`semgrep-cloud-platform/scan` is the Semgrep Cloud App running a server-side
ruleset. This repository ships no semgrep configuration file, so there is
nothing for a local CLI run to read, and `--config=auto` pulls a different rule
set entirely.

The consequence is that a clean local run says nothing about the red check:

```bash
semgrep --config=auto <files>          # 0 findings
# semgrep-cloud-platform/scan          # 2 blocking findings
```

Both of those findings were real. One sat beside a genuine defect, a URL parse
that derived `github.com/owner` from a remote naming no repository.

`p/security-audit` gets closer than `auto` and did reproduce one of the two,
but it is still a guess at the server's rule set rather than the rule set
itself:

```bash
semgrep --config=p/security-audit --config=p/python <files>
```

A pass from any `--config=` invocation is neither necessary nor sufficient. It
is a different check, so it cannot clear the remote one and its absence does
not condemn it.

There is an exact reproduction, and it is worth knowing before you guess at
rule packs. `semgrep ci`, when logged in, runs the rules configured on Semgrep
App rather than a pack you name:

```bash
SEMGREP_APP_TOKEN=<token> semgrep ci
```

That is the same rule set the CI check uses, so it is the only local command
whose clean result means anything about the red one. Without a token it cannot
work, and no `--config` value substitutes for it.

To learn what actually fired without a token, read the finding: the bot posts each one as a pull request
review comment naming the rule id, the file, and the line. `gh api
repos/OWNER/REPO/pulls/N/comments` returns them. The check run itself carries
no annotations and no output text, so the API path that looks most direct is
the one that tells you nothing.

The scan is not in the branch protection required set, so it does not block a
merge. That makes it easy to wave through, which is the trap: the two findings
here were a taint reaching a `subprocess.CompletedProcess` constructor and a
`compile()` call on file content, and both were worth fixing.

Suppression is not the escape hatch. The `security-suppressions-staged` hook
rejects any suppression comment in staged changes, which is a stronger stance
than the "last resort" language elsewhere in the rules. Fix the code or record
in the diff why the finding is not reachable.

Two different incidents live in this space and the conclusions do not transfer.
The taint and `compile()` findings above were real defects and were fixed in
code. Separately, the `python.lang.compatibility.python36.*` rules fire on this
repository and are false positives, because they assert a Python 3.6 floor
against `requires-python = ">=3.14"`; that one is tracked in #4725. Do not read
"the findings were real" as covering the compatibility rules, or #4725 as
licence to dismiss a taint finding.
