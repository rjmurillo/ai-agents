<!-- # taste-lint: ignore file-size, append-only trap index; split entries lose search locality. -->
# Gotchas

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

## A commit touching `.agents/` must carry the session log

`session-policy` rejects any commit that stages a file under `.agents/` unless
the JSON session log is staged in that **same** commit. Splitting the work into
"content commit, then log commit" fails on the first one.

Symptom: a commit touching `.agents/analysis/` or `.agents/architecture/` is
rejected while the identical change under any other path commits fine. See also
"Session log ordering" below, which governs when the log may first be staged.

## Session log ordering

Create the session log **untracked in the worktree before the first commit**,
and stage it only at session end.

`branch-context-policy` reads the worktree and wants the log present.
`session-policy` rejects a *staged* log whose `sessionEnd` is incomplete. A
session log cannot be both staged early and complete early, so following the
protocol literally (create and stage at start) cannot pass both gates.

Symptom: a commit is rejected by one of the two policies no matter which order
you try. Refs #3904.

## Never record `endingCommit` and then amend

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

## The push blocks at 21 commits, and the check runs at push time

The pre-push `push-ref-policy` hook hard-fails at more than 20 commits ahead of
`origin/main`. It runs at push time, so a long branch discovers the ceiling
after the work is committed, not while it accumulates. Check it mid-session:

```
git rev-list --count HEAD ^origin/main
```

Relief is the `commit-limit-bypass` label on the PR, and nothing else. Squashing
is often the wrong repair, because the five-file atomic-commit rule then makes
the collapsed commit a violation of a different rule. Prefer the label when the
branch is one coherent thread, and split into a second PR when it is not.

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
- Three competing schemes were measured live on 2026-08-02 (per-branch `/tmp`,
  4-slot hash `/tmp`, and `$HOME` variant). Only processes that open the exact
  same path are mutually excluded by flock. A mixed fleet provides no exclusion
  at all. Use one canonical form and correct any deviation on sight.

Issue #4283 documents the measured 28-waiter convoy produced by the global lock
and the first-principles analysis of why the race is per-ref.
Issue #4366 documents the three-scheme split and why the wipe hazard requires
moving out of `/tmp`.

## Never move a branch ref that is checked out in a linked worktree

A worktree that checks out branch `feature` has its own index and files. When
you run `git update-ref refs/heads/feature <new-sha>` from outside that
worktree, git moves the branch pointer but does NOT update the worktree index
or files. The result is a split state: `git rev-parse HEAD` returns the new
commit but `git write-tree` returns the old tree, and `git status` presents the
A-to-B diff as staged. Commits, tests, and issue claims based on this state are
attributed to the wrong commit.

This happens in an agent correction queue when a queued correction calls
`git update-ref` (or any command that moves the branch, such as `git commit
--amend` or `git reset`) while another agent's worktree has the same branch
checked out.

Rules:
- Before moving a branch ref, check whether it is checked out in any registered
  worktree: `git worktree list --porcelain | grep -B2 "branch refs/heads/<name>"`.
- If it is checked out, do not move the ref remotely. Instead, coordinate:
  either have the worktree owner move its own HEAD, or remove the worktree first
  and re-add it after the move.
- After any ref move, verify the target worktree is in the expected state:
  `git -C <worktree-path> status --porcelain` should be empty.
- Create safety refs for any commit or tree that could become unreachable before
  moving: `git tag safe/<sha> <sha>`.

Reproduced locally with one modified file: `git update-ref refs/heads/<branch>
<new-sha>` while `<branch>` is checked out in a linked worktree leaves the
worktree with `HEAD == new-sha` and `git write-tree == old-tree`. Issue #4498.
